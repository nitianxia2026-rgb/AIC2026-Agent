#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 6 · 校验：出价单调性 + 全部基准表 sanity check。有 FAIL 时退出码为 1。

用法：在 scripts/ 目录下执行  python3 verify_monotonic.py
产出：outputs/05-校验报告.md
"""

import csv
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GRADIENTS = ["1.0", "1.5", "2.0", "2.5", "3.0"]
# 合理量级范围（合成口径）
RANGES = {
    "点击率CTR": (0.0005, 0.15),
    "千次展示成本CPM": (1.0, 300.0),
    "点击成本CPC": (0.2, 50.0),
    "转化率CVR": (0.0005, 0.30),
}


def read_csv(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fnum(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


def main():
    results = []   # (文件, 检查项, 状态, 说明)

    # ---- 1. 出价曲线单调性 ----
    path4 = os.path.join("outputs", "04-出价梯度曲线-合成.csv")
    data = read_csv(path4)
    if data is None:
        results.append(("04-出价梯度曲线", "文件存在", "FAIL", "先运行 synthesize_curve.py"))
    else:
        by_group = {}
        for r in data:
            by_group.setdefault(r["分组"], {})[r["出价倍数"]] = r
        fails = []
        for g, gd in by_group.items():
            seq = [gd.get(k) for k in GRADIENTS]
            if any(s is None for s in seq):
                fails.append(f"{g}：梯度缺行")
                continue
            imp = [fnum(s["预估曝光倍数"]) for s in seq]
            cost = [fnum(s["预估成本倍数"]) for s in seq]
            conv = [fnum(s["预估转化倍数"]) for s in seq]
            for i in range(1, len(imp)):
                if not (imp[i] > imp[i-1]):
                    fails.append(f"{g}：曝光在 {GRADIENTS[i-1]}→{GRADIENTS[i]} 非递增")
                if not (cost[i] > cost[i-1]):
                    fails.append(f"{g}：成本在 {GRADIENTS[i-1]}→{GRADIENTS[i]} 非递增")
            if any(conv[i] is None or imp[i] is None or abs(conv[i] - imp[i]) > 1e-6 for i in range(len(conv))):
                fails.append(f"{g}：转化倍数与曝光倍数不一致")
        status = "PASS" if not fails else "FAIL"
        detail = f"{len(by_group)} 组 × 5 档梯度全部检查" if not fails else "；".join(fails[:5])
        results.append(("04-出价梯度曲线", "曝光/成本/转化 单调递增；转化=曝光", status, detail))

    # ---- 2. 曝光端合成基准 sanity ----
    path3 = os.path.join("outputs", "03-基准表-曝光端-合成.csv")
    data = read_csv(path3)
    if data is None:
        results.append(("03-曝光端基准", "文件存在", "FAIL", "先运行 synthesize_curve.py"))
    else:
        fails = []
        for r in data:
            p25, p50, p75 = fnum(r["P25"]), fnum(r["P50"]), fnum(r["P75"])
            name = r["指标"]
            if None in (p25, p50, p75) or not (p25 <= p50 <= p75):
                fails.append(f"{r['行业']}×{r['广告类型']}×{r['素材类型']} {name}：分位数乱序")
            elif name in RANGES and not (RANGES[name][0] <= p50 <= RANGES[name][1]):
                fails.append(f"{r['行业']}×{r['广告类型']}×{r['素材类型']} {name}：P50={p50} 超出合理量级")
        status = "PASS" if not fails else "FAIL"
        results.append(("03-曝光端基准", f"{len(data)-1} 行：分位数有序 + 量级合理", status,
                        "全部通过" if not fails else "；".join(fails[:5])))

    # ---- 3. 转化端真实基准 sanity ----
    path2 = os.path.join("outputs", "02-基准表-转化端.csv")
    data = read_csv(path2)
    if data is None:
        results.append(("02-转化端基准", "文件存在", "FAIL", "先运行 build_benchmark.py"))
    else:
        fails, warns = [], []
        for r in data:
            p25, p50, p75 = fnum(r["P25"]), fnum(r["P50"]), fnum(r["P75"])
            if None in (p25, p50, p75) or not (p25 <= p50 <= p75):
                fails.append(f"{r['分组']} {r['指标']}：分位数乱序")
                continue
            if r["指标"] in ("订单转化率", "平均注册率"):
                if p75 is not None and (p75 < 0 or p75 > 1):
                    fails.append(f"{r['分组']} {r['指标']}：P75={p75} 不是合法比率（应在 0–1）")
                elif p50 == 0:
                    warns.append(f"{r['分组']} {r['指标']}：P50=0（过半样本为零——真实数据允许，"
                                 f"但该组该指标区分度弱；口径说明须注明，回答时引用 P75 而非 P50）")
        status = "PASS" if not fails else "FAIL"
        if fails:
            detail = "；".join(fails[:5])
        elif warns:
            detail = "PASS（带提示）：；".join(warns[:4])
        else:
            detail = "全部通过"
        results.append(("02-转化端基准", f"{len(data)-1} 行：分位数有序 + 率值合法（0 允许，超界才 FAIL）", status, detail))

    # ---- 报告 ----
    md = ["# 校验报告（自动生成）", ""]
    all_pass = True
    for f_, item, status, detail in results:
        if status != "PASS":
            all_pass = False
        md.append(f"## {f_} —— **{status}**")
        md.append(f"- 检查项：{item}")
        md.append(f"- 说明：{detail}")
        md.append("")
    md.append("## 结论")
    md.append("- " + ("**全部 PASS**：基准库数值可以进入文档化（步骤 7）。" if all_pass
                      else "**存在 FAIL**：把本报告发给队长/Claude 修复脚本后重跑，不要手工改数。"))
    os.makedirs("outputs", exist_ok=True)
    out = os.path.join("outputs", "05-校验报告.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    for f_, item, status, detail in results:
        print(f"[{status}] {f_}：{detail}")
    print(f"→ {out}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
