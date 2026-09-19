#!/usr/bin/env python3
"""投手智囊出价仿真 MVP。

读取 KB-02 合成锚点，枚举相对当前出价的候选档，在保守/基准/乐观
三种情景下模拟预算约束后的曝光、点击、转化与花费，并生成测试带。
本工具只做合成场景仿真，不代表平台实时竞价或最优出价。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

SEED = 42
PARAM_VERSION = "bid-sim-v1.2"
MULTIPLIERS = (0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5)
INDUSTRIES = ("餐饮美食", "教育培训", "电商零售", "本地服务", "家居建材")
AD_CONFIG = {
    "信息流广告": {"billing": "CPM", "material": "图文", "alpha": 1.55, "beta": 1.00},
    "开屏广告": {"billing": "CPM", "material": "图文", "alpha": 1.35, "beta": 1.10},
    "搜索广告": {"billing": "CPC", "material": "不限", "alpha": 1.75, "beta": 0.95},
}
BUDGETS = (("低", 200.0, 0.30), ("中", 600.0, 0.60), ("高", 1500.0, 0.85))
OBJECTIVES = ("曝光", "点击", "留资", "下单")
CASES = {
    "保守": {"cost": "P75", "ctr": "P25", "cvr": "P25"},
    "基准": {"cost": "P50", "ctr": "P50", "cvr": "P50"},
    "乐观": {"cost": "P25", "ctr": "P75", "cvr": "P75"},
}

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "outputs" / "03-基准表-曝光端-合成.csv"
DEFAULT_SCENARIOS = ROOT / "outputs" / "06-出价仿真场景-合成.csv"
DEFAULT_BANDS = ROOT / "outputs" / "07-出价建议测试带.csv"


def f(value: str | float | int) -> float:
    return float(value)


def load_benchmarks(path: Path) -> dict[tuple[str, str, str], dict[str, dict[str, float]]]:
    table: dict[tuple[str, str, str], dict[str, dict[str, float]]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["行业"], row["广告类型"], row["素材类型"])
            metric = row["指标"]
            table.setdefault(key, {})[metric] = {
                "P25": f(row["P25"]), "P50": f(row["P50"]), "P75": f(row["P75"])
            }
    return table


def auction_share(relative_bid: float, alpha: float, beta: float) -> float:
    """合成竞争份额；relative_bid=用户出价/同组P50成本锚点。"""
    q = max(relative_bid, 0.05)
    return q**alpha / (q**alpha + beta)


def response(candidate_ratio: float, current_ratio: float, alpha: float, beta: float) -> float:
    """候选价相对当前价的交付变化，而非只看固定倍率。"""
    return auction_share(candidate_ratio, alpha, beta) / auction_share(current_ratio, alpha, beta)


def validate_request(request: dict) -> list[str]:
    required = (
        "industry", "ad_type", "objective", "daily_budget", "current_bid", "spend_ratio"
    )
    missing = [name for name in required if request.get(name) in (None, "")]
    if missing:
        return ["MISSING_" + name.upper() for name in missing]
    if request["industry"] not in INDUSTRIES:
        return ["UNSUPPORTED_INDUSTRY"]
    if request["ad_type"] not in AD_CONFIG:
        return ["UNSUPPORTED_AD_TYPE"]
    expected = AD_CONFIG[request["ad_type"]]["billing"]
    if request.get("billing_type", expected) != expected:
        return ["BILLING_TYPE_MISMATCH"]
    if request["objective"] not in OBJECTIVES:
        return ["UNSUPPORTED_OBJECTIVE"]
    try:
        daily_budget = f(request["daily_budget"])
        current_bid = f(request["current_bid"])
        spend_ratio = f(request["spend_ratio"])
    except (TypeError, ValueError):
        return ["INVALID_NUMERIC_INPUT"]
    if not all(math.isfinite(value) for value in (daily_budget, current_bid, spend_ratio)):
        return ["INVALID_NUMERIC_INPUT"]
    if daily_budget <= 0 or current_bid <= 0:
        return ["NON_POSITIVE_INPUT"]
    if not 0 <= spend_ratio <= 1:
        return ["SPEND_RATIO_OUT_OF_RANGE"]
    if request.get("audit_status") == "未通过":
        return ["AUDIT_NOT_READY"]
    if request["objective"] in ("留资", "下单") and "tracking_ready" not in request:
        return ["MISSING_TRACKING_READY"]
    if request["objective"] in ("留资", "下单") and request["tracking_ready"] is not True:
        return ["TRACKING_NOT_READY"]
    return []


def candidate_multipliers(daily_budget: float, spend_ratio: float) -> tuple[float, ...]:
    values = list(MULTIPLIERS)
    if daily_budget < 300 or spend_ratio >= 0.85:
        values = [k for k in values if k <= 1.2]
    if spend_ratio <= 0.05:
        values = [k for k in values if k <= 1.0]
    return tuple(values)


def simulate_request(request: dict, benchmarks: dict) -> list[dict]:
    errors = validate_request(request)
    if errors:
        return [{"status": "refused", "reason_code": "|".join(errors)}]

    industry, ad_type = request["industry"], request["ad_type"]
    config = AD_CONFIG[ad_type]
    material = request.get("material") or config["material"]
    key = (industry, ad_type, material)
    metrics = benchmarks.get(key)
    if not metrics:
        return [{"status": "refused", "reason_code": "BENCHMARK_NOT_FOUND"}]

    cost_metric = "千次展示成本CPM" if config["billing"] == "CPM" else "点击成本CPC"
    if not {"点击率CTR", "转化率CVR", cost_metric}.issubset(metrics):
        return [{"status": "refused", "reason_code": "METRIC_NOT_FOUND"}]

    budget = f(request["daily_budget"])
    current_bid = f(request["current_bid"])
    spend_ratio = f(request["spend_ratio"])
    objective = request["objective"]
    baseline_cost = metrics[cost_metric]["P50"]
    current_bid_to_anchor = current_bid / baseline_cost
    baseline_capacity = (
        budget / baseline_cost * 1000 if config["billing"] == "CPM" else budget / baseline_cost
    ) * (0.65 + 0.45 * min(1.0, spend_ratio))

    rows: list[dict] = []
    for k in candidate_multipliers(budget, spend_ratio):
        candidate_bid = current_bid * k
        candidate_bid_to_anchor = candidate_bid / baseline_cost
        rel = response(candidate_bid_to_anchor, current_bid_to_anchor, config["alpha"], config["beta"])
        for case_name, case in CASES.items():
            ctr = metrics["点击率CTR"][case["ctr"]]
            cvr = metrics["转化率CVR"][case["cvr"]]
            base_cost = metrics[cost_metric][case["cost"]]
            # 当前价相对同组成本锚点的位置会影响候选单位成本；指数<1表示成本次线性变化。
            estimated_cost = base_cost * (candidate_bid_to_anchor ** 0.72)

            if config["billing"] == "CPM":
                traffic_impressions = baseline_capacity * rel
                affordable_impressions = budget / estimated_cost * 1000
                impressions = min(traffic_impressions, affordable_impressions)
                clicks = impressions * ctr
                spend = min(budget, impressions * estimated_cost / 1000)
            else:
                traffic_clicks = baseline_capacity * rel
                affordable_clicks = budget / estimated_cost
                clicks = min(traffic_clicks, affordable_clicks)
                impressions = clicks / ctr if ctr else 0.0
                spend = min(budget, clicks * estimated_cost)

            conversions = clicks * cvr
            cpa = spend / conversions if conversions else None
            exhaustion = spend / budget
            primary = impressions if objective == "曝光" else clicks if objective == "点击" else conversions
            rows.append({
                "scenario_id": request["scenario_id"], "status": "ok", "synthetic_flag": "true",
                "seed": SEED, "parameter_version": PARAM_VERSION,
                "industry": industry, "ad_type": ad_type, "material": material,
                "billing_type": config["billing"], "objective": objective,
                "budget_band": request.get("budget_band", "用户输入"), "daily_budget": round(budget, 4),
                "current_bid": round(current_bid, 4), "spend_ratio": round(spend_ratio, 4),
                "case": case_name, "candidate_multiplier": k,
                "candidate_bid": round(candidate_bid, 4),
                "current_bid_to_anchor": round(current_bid_to_anchor, 6),
                "candidate_bid_to_anchor": round(candidate_bid_to_anchor, 6),
                "alpha": config["alpha"], "beta": config["beta"],
                "relative_delivery": round(rel, 6), "estimated_unit_cost": round(estimated_cost, 6),
                "simulated_impressions": round(impressions, 4), "simulated_clicks": round(clicks, 4),
                "simulated_conversions": round(conversions, 4), "simulated_spend": round(spend, 4),
                "simulated_cpa": "" if cpa is None else round(cpa, 4),
                "budget_exhaustion_risk": "高" if exhaustion >= 0.95 else "中" if exhaustion >= 0.75 else "低",
                "primary_value": round(primary, 4), "generated_at": request.get("generated_at", "fixed-batch")
            })
    return rows


def recommendation(rows: list[dict]) -> dict:
    if not rows or rows[0].get("status") != "ok":
        return {"status": "refused", "reason_code": rows[0].get("reason_code", "NO_RESULT")}
    by_k: dict[float, list[dict]] = {}
    for row in rows:
        by_k.setdefault(f(row["candidate_multiplier"]), []).append(row)
    baseline = sum(f(r["primary_value"]) for r in by_k.get(1.0, [])) / max(1, len(by_k.get(1.0, [])))
    ranked = []
    for k, group in by_k.items():
        mean_primary = sum(f(r["primary_value"]) for r in group) / len(group)
        mean_spend = sum(f(r["simulated_spend"]) for r in group) / len(group)
        spread = (max(f(r["primary_value"]) for r in group) - min(f(r["primary_value"]) for r in group)) / max(mean_primary, 1e-9)
        gain = mean_primary / max(baseline, 1e-9)
        cost_ratio = mean_spend / f(group[0]["daily_budget"])
        score = gain - 0.22 * max(0.0, k - 1.0) - 0.20 * max(0.0, cost_ratio - 0.9) - 0.12 * spread
        ranked.append((score, k, mean_primary, cost_ratio))
    ranked.sort(reverse=True)
    _, best_k, _, cost_ratio = ranked[0]
    ks = sorted(by_k)
    idx = ks.index(best_k)
    low, high = ks[max(0, idx - 1)], ks[min(len(ks) - 1, idx + 1)]
    reason = "BALANCED_GAIN_COST"
    if best_k < 1.0:
        reason = "CONTROL_COST_FIRST"
    elif best_k > 1.0:
        reason = "TEST_INCREMENT_WITH_CAP"
    return {
        "scenario_id": rows[0]["scenario_id"], "status": "ok", "synthetic_flag": "true",
        "parameter_version": PARAM_VERSION, "industry": rows[0]["industry"], "ad_type": rows[0]["ad_type"],
        "billing_type": rows[0]["billing_type"], "objective": rows[0]["objective"],
        "daily_budget": rows[0]["daily_budget"], "current_bid": rows[0]["current_bid"],
        "current_bid_to_anchor": rows[0]["current_bid_to_anchor"],
        "spend_ratio": rows[0]["spend_ratio"], "test_band_low": low, "first_test_multiplier": best_k,
        "test_band_high": high, "first_test_bid": round(f(rows[0]["current_bid"]) * best_k, 4),
        "reason_code": reason, "observe": "消耗速度、目标指标、单位成本",
        "stop_condition": "预算消耗加快但目标指标未改善，或单位成本连续恶化时停止",
        "budget_risk": "高" if cost_ratio >= 0.95 else "中" if cost_ratio >= 0.75 else "低",
        "disclaimer": "合成仿真，用于首轮测试，不代表平台最优出价"
    }


def batch_requests() -> list[dict]:
    requests = []
    now = "2026-09-16T00:00:00+08:00"
    for industry in INDUSTRIES:
        for ad_type, config in AD_CONFIG.items():
            for band, budget, spend_ratio in BUDGETS:
                for objective in OBJECTIVES:
                    sid = hashlib.sha256(f"{industry}|{ad_type}|{band}|{objective}".encode()).hexdigest()[:12]
                    requests.append({
                        "scenario_id": sid, "industry": industry, "ad_type": ad_type,
                        "billing_type": config["billing"], "objective": objective,
                        "daily_budget": budget, "current_bid": 20.0 if config["billing"] == "CPM" else 2.5,
                        "budget_band": band, "spend_ratio": spend_ratio, "tracking_ready": True,
                        "audit_status": "通过", "generated_at": now
                    })
    return requests


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--bands", type=Path, default=DEFAULT_BANDS)
    parser.add_argument("--request-json", help="可选：运行单个JSON请求并打印结果")
    args = parser.parse_args()
    benchmarks = load_benchmarks(args.input)
    if args.request_json:
        request = json.loads(args.request_json)
        request.setdefault("scenario_id", "interactive")
        rows = simulate_request(request, benchmarks)
        print(json.dumps({"rows": rows, "recommendation": recommendation(rows)}, ensure_ascii=False, indent=2))
        return
    scenario_rows, bands = [], []
    for request in batch_requests():
        rows = simulate_request(request, benchmarks)
        scenario_rows.extend(rows)
        bands.append(recommendation(rows))
    write_csv(args.scenarios, scenario_rows)
    write_csv(args.bands, bands)
    print(f"generated scenarios={len(scenario_rows)} bands={len(bands)} version={PARAM_VERSION}")


if __name__ == "__main__":
    main()
