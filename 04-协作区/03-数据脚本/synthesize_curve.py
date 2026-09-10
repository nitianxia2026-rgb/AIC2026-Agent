#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 5 · 合成曝光端基准 + 出价梯度曲线。

真实数据（飞桨）没有曝光/点击/花费字段，曝光端基准由本脚本按行业常识合成：
  CTR / CPM / CPC 的量级锚点 → 每格 30 个伪样本加噪声 → P25/P50/P75；
  CVR 优先引用真实基准表（02）的 P50，没有则用合成默认。
出价曲线：share(r) = r²/(r²+1)（单调递增、边际递减），r = 出价/基准出价。

⚠️ 全部输出为【合成基准】，答辩与对用户口径都要声明，不冒充真实大盘。

用法：在 scripts/ 目录下执行  python3 synthesize_curve.py
产出：outputs/03-基准表-曝光端-合成.csv、outputs/04-出价梯度曲线-合成.csv、
      outputs/03-曝光端基准与曲线-draft.md
"""

import csv
import math
import os
import random
import sys

# ============ 合成假设（量级锚点，均可按需要调整） ============
SEED = 42
NOISE = 0.18          # 对数正态噪声强度
N_SAMPLES = 30        # 每格伪样本数
GRADIENTS = [1.0, 1.5, 2.0, 2.5, 3.0]   # 出价梯度倍数

# 行业 → (CTR 倍率, 成本倍率)
INDUSTRIES = {
    "餐饮美食": (1.05, 0.95),
    "教育培训": (1.10, 1.15),
    "电商零售": (1.20, 1.25),
    "本地服务": (1.00, 1.00),
    "家居建材": (0.85, 0.90),
}
# 广告类型 → (基础CTR, 基础CPM元, 基础CPC元, 素材维度适用)
AD_TYPES = {
    "信息流广告": (0.015, 18.0, None, True),
    "开屏广告":   (0.010, 35.0, None, True),
    "搜索广告":   (0.030, None, 2.50, False),
}
# 素材类型 → (CTR 倍率, 成本倍率)
MATERIALS = {"视频": (1.15, 1.05), "图文": (1.00, 1.00), "横幅": (0.70, 0.90)}
DEFAULT_CVR = 0.02     # 真实基准缺 CVR 时的默认值（合成声明）
# ================================================================

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ALIASES_CVR = {"广告类型": ["广告类型", "广告形式"], "素材类型": ["素材类型", "创意类型"]}


def percentile(sorted_vals, p):
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return sorted_vals[0]
    k = (n - 1) * p
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def lognormal_samples(base, n, rng, noise=NOISE):
    return sorted(base * math.exp(rng.gauss(0, noise)) for _ in range(n))


def load_cvr_anchor():
    """从真实/兜底基准表读 (广告类型 × 素材类型) → 订单转化率 P50，作 CVR 锚。
    只收 0.5%–15% 量级的锚：飞桨渠道级历史观测 CVR 常在万分位（P50≈0），
    那是"历史渠道的水平"，不是中小企业客户可达的漏斗转化率，直接引用会让演示失真。
    另外真实表分组口径（横幅/banner/jpg…）与合成表（信息流/搜索/视频…）对不上，
    所以真实数据下通常是空锚 + 诚实标注，而不是硬凑。"""
    path = os.path.join("outputs", "02-基准表-转化端.csv")
    anchor, source = {}, "合成默认 2%"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    if row.get("指标") == "订单转化率" and row.get("分组") != "全部数据（总基准）":
                        try:
                            p50 = float(row["P50"])
                        except (ValueError, KeyError, TypeError):
                            continue
                        if not (0.005 <= p50 <= 0.15):
                            continue   # 量级不适合做漏斗锚点，宁用合成默认并声明
                        parts = [p.strip() for p in row["分组"].split("×")]
                        if len(parts) == 3:
                            key = (parts[1], parts[2])
                            anchor[key] = p50
            if anchor:
                source = f"真实基准表 02 的订单转化率 P50（引用 {len(anchor)} 组）"
            else:
                source = "合成默认 2%（02 表存在，但口径不匹配/量级不适合，未引用）"
        except Exception as e:
            print(f"  [警告] 读取 {path} 失败（{e}），CVR 用合成默认")
    return anchor, source


def main():
    rng = random.Random(SEED)
    cvr_anchor, cvr_source = load_cvr_anchor()

    cells = []   # (行业, 广告类型, 素材类型, base_ctr, base_cost_name, base_cost, cvr)
    for ind, (ctr_m, cost_m) in INDUSTRIES.items():
        for adt, (b_ctr, b_cpm, b_cpc, has_material) in AD_TYPES.items():
            mats = MATERIALS.keys() if has_material else ["不限"]
            for mat in mats:
                m_ctr, m_cost = (MATERIALS.get(mat, (1.0, 1.0)) if has_material else (1.0, 1.0))
                base_ctr = b_ctr * ctr_m * m_ctr
                if b_cpm is not None:
                    cost_name, base_cost = "千次展示成本CPM", b_cpm * cost_m * m_cost
                else:
                    cost_name, base_cost = "点击成本CPC", b_cpc * cost_m * m_cost
                cvr = cvr_anchor.get((adt, mat), DEFAULT_CVR)
                cells.append((ind, adt, mat, base_ctr, cost_name, base_cost, cvr))

    # ---- 曝光端基准表（长表）----
    rows = [["行业", "广告类型", "素材类型", "指标", "P25", "P50", "P75", "样本说明"]]
    for ind, adt, mat, b_ctr, cost_name, b_cost, cvr in cells:
        s_ctr = lognormal_samples(b_ctr, N_SAMPLES, rng)
        s_cost = lognormal_samples(b_cost, N_SAMPLES, rng)
        s_cvr = lognormal_samples(cvr, N_SAMPLES, rng, noise=NOISE * 0.7)
        for name, s in (("点击率CTR", s_ctr), (cost_name, s_cost), ("转化率CVR", s_cvr)):
            rows.append([ind, adt, mat, name,
                         f"{percentile(s,0.25):.4g}", f"{percentile(s,0.5):.4g}",
                         f"{percentile(s,0.75):.4g}", f"合成{N_SAMPLES} 伪样本"])

    os.makedirs("outputs", exist_ok=True)
    bench_path = os.path.join("outputs", "03-基准表-曝光端-合成.csv")
    with open(bench_path, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)

    # ---- 出价梯度曲线 ----
    curve = [["分组", "出价倍数", "预估曝光倍数", "预估成本倍数", "预估转化倍数"]]
    for ind, adt, mat, *_ in cells:
        g = f"{ind} × {adt} × {mat}"
        for r in GRADIENTS:
            share = r * r / (r * r + 1)          # 获胜份额：单调递增、边际递减
            rel_imp = share / 0.5                 # 以基准价(份额50%)为 1.0
            curve.append([g, f"{r:.1f}", f"{rel_imp:.3f}", f"{r*rel_imp:.3f}", f"{rel_imp:.3f}"])
    curve_path = os.path.join("outputs", "04-出价梯度曲线-合成.csv")
    with open(curve_path, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(curve)

    # ---- draft md ----
    md = []
    ap = md.append
    ap("# 曝光端基准与出价曲线（draft · 合成基准）")
    ap("")
    ap("## 口径说明（人工补全后定稿）")
    ap("1. 指标定义：CTR = 点击÷曝光；CPM = 千次展示成本；CPC = 单次点击成本；CVR = 转化÷点击。")
    ap("2. 数据来源：**合成基准**——量级锚点按国内市场常识设定（见下表），每格 30 个伪样本加对数正态噪声取分位数；"
       f"CVR 锚定来源：{cvr_source}。不冒充真实大盘，答辩与对用户口径均须声明。")
    ap("3. 分组维度：行业 × 广告类型 × 素材类型（搜索广告无素材维度，记'不限'）。")
    ap("4. 分位数怎么读：P25–P75 = 建议区间；P50 = 典型水平。")
    ap("5. 使用限制：合成数据仅用于'量级感与区间话术'，配合公式与计算器实算使用；禁精确预测表述。"
       "本表与真实转化端基准（02 表）口径不同——02 是飞桨历史渠道观测值，本表是行业常识锚点，"
       "两表各管各的，回答时各引各的表，不可互相换算。")
    ap("")
    ap("## 合成假设表（可复核）")
    ap("")
    ap("| 因素 | 取值 |")
    ap("|---|---|")
    ap("| 基础 CTR | 信息流 1.5% / 开屏 1.0% / 搜索 3.0% |")
    ap("| 基础成本 | 信息流 CPM 18 元 / 开屏 CPM 35 元 / 搜索 CPC 2.5 元 |")
    ap("| 素材倍率(CTR,成本) | 视频 (1.15, 1.05) / 图文 (1.0, 1.0) / 横幅 (0.7, 0.9) |")
    ap("| 行业倍率(CTR,成本) | " + "；".join(f"{k} ({a}, {b})" for k, (a, b) in INDUSTRIES.items()) + " |")
    ap("| 噪声 | 对数正态 σ=0.18；CVR σ=0.126；种子 42（可复现） |")
    ap("| 出价曲线 | share(r)=r²/(r²+1)，r=出价/基准出价，基准价处份额 50% |")
    ap("")
    ap("## 出价梯度曲线（所有组同形，相对倍数）")
    ap("")
    ap("| 出价倍数 | 曝光倍数 | 成本倍数 | 转化倍数 |")
    ap("|---|---|---|---|")
    for r in GRADIENTS:
        share = r * r / (r * r + 1)
        rel = share / 0.5
        ap(f"| {r:.1f}× | {rel:.2f} | {r*rel:.2f} | {rel:.2f} |")
    ap("")
    ap("读法：出价提到基准价 2 倍 → 预估曝光 ≈1.6 倍，但成本 ≈3.2 倍——**提价买量的边际成本上升很快**，"
       "这就是节点5要求做单调性自检的原因。注意：固定日预算时，实际曝光增幅会小于表中的曝光倍数（预算会先耗尽）。")
    ap("")
    ap("## 演算示例（信息流 × 图文 × 本地服务，日预算 500 元）")
    ap("")
    ap("- 查基准表：CPM≈18 元，CTR≈1.5%，CVR≈2%")
    ap("- 正向：500÷18×1000 ≈ 2.78 万曝光 → ×1.5% ≈ 417 点击 → ×2% ≈ 8 个转化")
    ap("- 逆向：目标 20 个留资 → 20÷2% = 1000 点击 → 1000÷1.5% ≈ 6.67 万曝光 → ×18÷1000 ≈ 1200 元/天")
    ap("- 结论示例话术：'500 元/天大约带来 X–Y 个转化（建议区间），要稳到 20 个建议预算提到 1200 元左右或下调目标'")
    ap("")
    md_path = os.path.join("outputs", "03-曝光端基准与曲线-draft.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    print(f"[完成] 合成基准 {len(cells)} 格 → {bench_path}")
    print(f"       出价曲线 {len(cells)*len(GRADIENTS)} 行 → {curve_path}")
    print(f"       口径草稿 → {md_path}")
    print(f"  CVR 锚定来源：{cvr_source}")
    print("  下一步：运行 verify_monotonic.py 做全部校验")


if __name__ == "__main__":
    main()
