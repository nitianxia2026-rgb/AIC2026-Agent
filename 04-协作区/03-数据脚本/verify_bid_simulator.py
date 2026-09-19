#!/usr/bin/env python3
"""校验投手智囊出价仿真器并生成报告。"""

from __future__ import annotations

import csv
import hashlib
import math
import platform
import subprocess
import sys
from pathlib import Path

import bid_simulator as sim

ROOT = Path(__file__).resolve().parent
SCENARIOS = ROOT / "outputs" / "06-出价仿真场景-合成.csv"
BANDS = ROOT / "outputs" / "07-出价建议测试带.csv"
REPORT = ROOT / "outputs" / "08-出价仿真校验报告.md"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    subprocess.run([sys.executable, str(ROOT / "bid_simulator.py")], check=True, cwd=ROOT)
    first_hashes = (digest(SCENARIOS), digest(BANDS))
    subprocess.run([sys.executable, str(ROOT / "bid_simulator.py")], check=True, cwd=ROOT)
    second_hashes = (digest(SCENARIOS), digest(BANDS))
    rows, bands = read(SCENARIOS), read(BANDS)

    checks = []
    def check(name: str, ok: bool, evidence: str) -> None:
        checks.append((name, ok, evidence))

    check("固定输入可复现", first_hashes == second_hashes, f"06/07 SHA-256重复运行一致={first_hashes == second_hashes}")
    check("花费不超过预算", all(float(r["simulated_spend"]) <= float(r["daily_budget"]) + 1e-8 for r in rows), "全量行检查")
    numeric = ("simulated_impressions", "simulated_clicks", "simulated_conversions", "simulated_spend")
    check("所有业务量非负", all(float(r[k]) >= 0 for r in rows for k in numeric), "全量数值字段检查")
    check("三情景齐全", all({r["case"] for r in rows if r["scenario_id"] == sid} == set(sim.CASES) for sid in {r["scenario_id"] for r in rows}), "每场景每档含三情景")
    check("CPM/CPC分流", all((r["ad_type"] == "搜索广告") == (r["billing_type"] == "CPC") for r in rows), "搜索=CPC，其余=CPM")
    benchmarks = sim.load_benchmarks(sim.DEFAULT_INPUT)
    missing = sim.simulate_request({"scenario_id": "missing"}, benchmarks)[0]
    missing_spend = sim.simulate_request({"scenario_id":"missing-spend","industry":"餐饮美食","ad_type":"信息流广告","billing_type":"CPM","objective":"点击","daily_budget":300,"current_bid":20}, benchmarks)[0]
    missing_tracking = sim.simulate_request({"scenario_id":"missing-tracking","industry":"餐饮美食","ad_type":"信息流广告","billing_type":"CPM","objective":"留资","daily_budget":300,"current_bid":20,"spend_ratio":0.6}, benchmarks)[0]
    mismatch = sim.simulate_request({"scenario_id":"bad","industry":"餐饮美食","ad_type":"搜索广告","billing_type":"CPM","objective":"点击","daily_budget":300,"current_bid":2,"spend_ratio":0.6}, benchmarks)[0]
    unsupported_conversion_bid = sim.simulate_request({"scenario_id":"bad-ocpm","industry":"餐饮美食","ad_type":"信息流广告","billing_type":"oCPM","objective":"留资","daily_budget":300,"current_bid":20,"spend_ratio":0.6,"tracking_ready":True}, benchmarks)[0]
    bad_ratio = sim.simulate_request({"scenario_id":"bad-ratio","industry":"餐饮美食","ad_type":"信息流广告","billing_type":"CPM","objective":"点击","daily_budget":300,"current_bid":20,"spend_ratio":1.2}, benchmarks)[0]
    check("缺参拒绝", missing["status"] == "refused" and "MISSING" in missing["reason_code"], missing["reason_code"])
    check("消耗比例缺失拒绝", missing_spend["status"] == "refused" and missing_spend["reason_code"] == "MISSING_SPEND_RATIO", missing_spend["reason_code"])
    check("留资回传状态缺失拒绝", missing_tracking["status"] == "refused" and missing_tracking["reason_code"] == "MISSING_TRACKING_READY", missing_tracking["reason_code"])
    check("计费口径冲突拒绝", mismatch["status"] == "refused" and mismatch["reason_code"] == "BILLING_TYPE_MISMATCH", mismatch["reason_code"])
    check("oCPM/CPA不得套用CPM/CPC锚点", unsupported_conversion_bid["status"] == "refused" and unsupported_conversion_bid["reason_code"] == "BILLING_TYPE_MISMATCH", unsupported_conversion_bid["reason_code"])
    check("消耗比例越界拒绝", bad_ratio["status"] == "refused" and bad_ratio["reason_code"] == "SPEND_RATIO_OUT_OF_RANGE", bad_ratio["reason_code"])
    check("合成标识与参数版本齐全", all(r["synthetic_flag"] == "true" and r["parameter_version"] for r in rows + bands), "06/07全行检查")
    distinct = {(r["objective"], r["first_test_multiplier"], r["budget_risk"], r["reason_code"]) for r in bands}
    check("建议具有差异化", len(distinct) >= 6, f"不同建议组合={len(distinct)}")

    bid_sensitivity = []
    for bid in (5.0, 17.75, 40.0):
        req = {"scenario_id":f"bid-{bid}","industry":"餐饮美食","ad_type":"信息流广告","billing_type":"CPM","objective":"留资","daily_budget":500,"current_bid":bid,"spend_ratio":0.6,"tracking_ready":True}
        rec = sim.recommendation(sim.simulate_request(req, benchmarks))
        bid_sensitivity.append((bid, rec["first_test_multiplier"], rec["budget_risk"]))
    sensitivity_ok = bid_sensitivity[0][1] > bid_sensitivity[1][1] > bid_sensitivity[2][1]
    check("当前出价相对锚点会影响建议", sensitivity_ok, str(bid_sensitivity))

    cpm_req = {"scenario_id":"manual-cpm","industry":"餐饮美食","ad_type":"信息流广告","billing_type":"CPM","objective":"点击","daily_budget":300,"current_bid":20,"spend_ratio":0.6}
    cpc_req = {"scenario_id":"manual-cpc","industry":"餐饮美食","ad_type":"搜索广告","billing_type":"CPC","objective":"留资","daily_budget":300,"current_bid":2.5,"spend_ratio":0.6,"tracking_ready":True}
    cpm_row = next(r for r in sim.simulate_request(cpm_req, benchmarks) if r["case"] == "基准" and r["candidate_multiplier"] == 1.0)
    cpc_row = next(r for r in sim.simulate_request(cpc_req, benchmarks) if r["case"] == "基准" and r["candidate_multiplier"] == 1.0)
    cpm_cost = benchmarks[("餐饮美食","信息流广告","图文")]["千次展示成本CPM"]["P50"]
    cpc_cost = benchmarks[("餐饮美食","搜索广告","不限")]["点击成本CPC"]["P50"]
    ctr = benchmarks[("餐饮美食","信息流广告","图文")]["点击率CTR"]["P50"]
    cvr = benchmarks[("餐饮美食","搜索广告","不限")]["转化率CVR"]["P50"]
    cap_factor = 0.65 + 0.45 * 0.6
    cpm_candidate_ratio = 20 / cpm_cost
    cpm_estimated_cost = cpm_cost * (cpm_candidate_ratio ** 0.72)
    cpm_manual_imp = min(300 / cpm_cost * 1000 * cap_factor, 300 / cpm_estimated_cost * 1000)
    cpm_manual_click = cpm_manual_imp * ctr
    cpc_candidate_ratio = 2.5 / cpc_cost
    cpc_estimated_cost = cpc_cost * (cpc_candidate_ratio ** 0.72)
    cpc_manual_click = min(300 / cpc_cost * cap_factor, 300 / cpc_estimated_cost)
    cpc_manual_conv = cpc_manual_click * cvr
    check("CPM人工手算一致", math.isclose(cpm_manual_click, float(cpm_row["simulated_clicks"]), rel_tol=1e-5), f"手算点击={cpm_manual_click:.4f}, 脚本={cpm_row['simulated_clicks']}")
    check("CPC人工手算一致", math.isclose(cpc_manual_conv, float(cpc_row["simulated_conversions"]), rel_tol=1e-5), f"手算转化={cpc_manual_conv:.4f}, 脚本={cpc_row['simulated_conversions']}")

    passed = all(ok for _, ok, _ in checks)
    lines = [
        "# 出价仿真校验报告", "", "## 1. 环境与版本", "",
        f"- Python：{platform.python_version()}", f"- 参数版本：{sim.PARAM_VERSION}",
        "- 声明：合成仿真，用于首轮测试，不代表平台最优出价。", "",
        "## 2. 输入文件、行数、SHA-256", "",
        f"- `03-基准表-曝光端-合成.csv`：SHA-256 `{digest(sim.DEFAULT_INPUT)}`",
        f"- `06-出价仿真场景-合成.csv`：{len(rows)}行，SHA-256 `{digest(SCENARIOS)}`",
        f"- `07-出价建议测试带.csv`：{len(bands)}行，SHA-256 `{digest(BANDS)}`", "",
        "## 3. 自动校验", "", "| 检查 | 结果 | 证据 |", "|---|---|---|",
    ]
    lines += [f"| {name} | {'PASS' if ok else 'FAIL'} | {evidence} |" for name, ok, evidence in checks]
    lines += [
        "", "## 4. 两个场景人工手算对照", "",
        f"- CPM：当前价/锚点={cpm_candidate_ratio:.4f}，估算CPM={cpm_estimated_cost:.4f}；`min(300÷{cpm_cost}×1000×{cap_factor:.2f}, 300÷{cpm_estimated_cost:.4f}×1000)×{ctr}` = {cpm_manual_click:.4f} 点击；脚本 {cpm_row['simulated_clicks']}。",
        f"- CPC：当前价/锚点={cpc_candidate_ratio:.4f}，估算CPC={cpc_estimated_cost:.4f}；`min(300÷{cpc_cost}×{cap_factor:.2f}, 300÷{cpc_estimated_cost:.4f})×{cvr}` = {cpc_manual_conv:.4f} 转化；脚本 {cpc_row['simulated_conversions']}。",
        "", "## 5. 差异化测试矩阵", "",
        f"- 覆盖5行业×3广告形式×3预算档×4目标，共{len(bands)}个建议场景。",
        f"- 建议组合数量：{len(distinct)}。低预算/高消耗会移除高加价档；不同目标按曝光、点击或转化评分。",
        "", "## 6. 已知限制与合成声明", "",
        "- 参数来自KB-02合成锚点和项目假设，不是平台实时竞价数据。",
        "- 当前出价先转换为相对同组P50成本锚点的位置，再模拟相邻调价；锚点是合成口径，不是市场真实底价。",
        "- 推荐的是相对当前出价的首轮测试带，不是市场基准价或最优出价。",
        f"- {sim.PARAM_VERSION}只接受与KB-02成本锚点同单位的CPM/CPC出价；oCPM目标成本或CPA出价须另建同单位锚点，当前版本拒绝混算。",
        "- 未接入真实账户API，不自动操作广告计划。",
        "", "## 7. 结论", "",
        f"- 总体：{'PASS，可生成KB-04保底材料' if passed else 'FAIL，不得接入助手'}",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"checks={len(checks)} passed={sum(ok for _, ok, _ in checks)} report={REPORT}")
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
