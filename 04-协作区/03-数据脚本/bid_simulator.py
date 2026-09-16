#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bid_simulator.py — 出价仿真脚本（P2-01）

读取 KB-02 曝光端合成基准 + 算法参数配置，生成：
  - outputs/06-出价仿真场景-合成.csv（全场景仿真表）
  - outputs/07-出价建议测试带.csv（建议测试带汇总）

算法依据：16-出价仿真与建议算法实施计划-v1.md §4
用法：在 03-数据脚本/ 目录下执行  python bid_simulator.py

⚠️ 全部输出为【合成仿真】，synthetic_flag=true，不冒充真实投放效果。
"""

import csv
import math
import os
import sys
import hashlib
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ============ 固定参数（见 出价仿真参数登记-v1.md） ============
SEED = 42
PARAM_VERSION = "v1"

# 候选调价倍数（7 档）
CANDIDATE_MULTIPLIERS = [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5]

# 预算档位（元/天）
BUDGET_LEVELS = {"低": 200, "中": 500, "高": 1000}

# 五行业
INDUSTRIES = ["餐饮美食", "教育培训", "电商零售", "本地服务", "家居建材"]

# 广告形式 → (billing_type, material_for_kb02_lookup)
AD_TYPE_MAP = {
    "信息流广告": ("CPM", "图文"),
    "开屏广告":   ("CPM", "图文"),
    "搜索广告":   ("CPC", "不限"),
}

# 目标
OBJECTIVES = ["曝光", "点击", "留资", "下单"]

# 算法参数（按广告形式分组，项目合成假设）
ALPHA = {"信息流广告": 1.2, "开屏广告": 1.0, "搜索广告": 1.5}
BETA  = {"信息流广告": 1.5, "开屏广告": 2.0, "搜索广告": 1.2}
TRAFFIC_INDEX = {"信息流广告": 1.0, "开屏广告": 1.0, "搜索广告": 1.0}

# 三情景 → (CTR分位, 成本分位, CVR分位)
# 保守：成本高(P75)、率低(P25)  |  基准：P50  |  乐观：成本低(P25)、率高(P75)
SCENARIOS = {
    "保守": ("P25", "P75", "P25"),
    "基准": ("P50", "P50", "P50"),
    "乐观": ("P75", "P25", "P75"),
}

# 06 输出字段顺序
FIELDS_06 = [
    "scenario_id", "synthetic_flag", "seed", "param_version", "generation_time",
    "industry", "ad_type", "billing_type", "objective",
    "daily_budget", "current_bid", "candidate_multiplier", "candidate_bid",
    "observation_hours", "spend_so_far", "impressions", "clicks", "conversions",
    "ctr_case", "cvr_case", "base_cost_case", "scenario_name",
    "alpha", "beta", "traffic_index",
    "relative_delivery", "estimated_unit_cost",
    "simulated_impressions", "simulated_clicks",
    "simulated_conversions", "simulated_spend", "simulated_cpa",
    "budget_exhaustion_risk", "uncertainty_level",
    "score", "recommendation_label", "reason_code",
]

# 07 输出字段顺序
FIELDS_07 = [
    "scenario_id", "synthetic_flag", "seed", "param_version", "generation_time",
    "industry", "ad_type", "billing_type", "objective",
    "daily_budget", "current_bid", "scenario_name",
    "recommended_k", "recommended_bid",
    "first_test_tier", "observation_metric", "observe_condition", "stop_condition",
    "simulated_impressions", "simulated_clicks", "simulated_conversions",
    "simulated_spend", "simulated_cpa",
    "budget_exhaustion_risk", "uncertainty_level",
    "reason_code", "all_scores",
]


# ============ 核心函数 ============

def load_kb02():
    """读取 KB-02 曝光端合成基准表 → {(行业,广告类型,素材类型): {指标: {P25,P50,P75}}}"""
    path = os.path.join("outputs", "03-基准表-曝光端-合成.csv")
    lookup = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = (row["行业"], row["广告类型"], row["素材类型"])
            metric = row["指标"]
            if key not in lookup:
                lookup[key] = {}
            lookup[key][metric] = {
                "P25": float(row["P25"]),
                "P50": float(row["P50"]),
                "P75": float(row["P75"]),
            }
    return lookup


def share(k, alpha, beta):
    """合成局部响应 share(k) = k^alpha / (k^alpha + beta)"""
    ka = k ** alpha
    return ka / (ka + beta)


def rel_delivery(k, alpha, beta):
    """相对交付量 relative_delivery(k) = share(k) / share(1)"""
    return share(k, alpha, beta) / share(1.0, alpha, beta)


def simulate(billing, base_cost, base_ctr, base_cvr, daily_budget, k, alpha, beta):
    """统一仿真入口，返回 dict"""
    rd = rel_delivery(k, alpha, beta)
    est_unit = base_cost * k  # cost_factor(k) = k

    if billing == "CPM":
        baseline_imp = daily_budget / base_cost * 1000 if base_cost > 0 else 0
        traffic_imp = baseline_imp * rd
        affordable_imp = daily_budget / est_unit * 1000 if est_unit > 0 else 0
        sim_imp = min(traffic_imp, affordable_imp)
        sim_clicks = sim_imp * base_ctr
        sim_conv = sim_clicks * base_cvr
        sim_spend = min(daily_budget, sim_imp * est_unit / 1000)
    else:  # CPC
        baseline_clk = daily_budget / base_cost if base_cost > 0 else 0
        traffic_clk = baseline_clk * rd
        affordable_clk = daily_budget / est_unit if est_unit > 0 else 0
        sim_clicks = min(traffic_clk, affordable_clk)
        sim_imp = sim_clicks / base_ctr if base_ctr > 0 else 0
        sim_conv = sim_clicks * base_cvr
        sim_spend = min(daily_budget, sim_clicks * est_unit)

    sim_cpa = sim_spend / sim_conv if sim_conv > 0 else None
    return {
        "relative_delivery": rd,
        "estimated_unit_cost": est_unit,
        "simulated_impressions": sim_imp,
        "simulated_clicks": sim_clicks,
        "simulated_conversions": sim_conv,
        "simulated_spend": sim_spend,
        "simulated_cpa": sim_cpa,
    }


# 目标差异化权重（项目合成假设）——不同目标对成本/预算敏感度不同
OBJ_WEIGHTS = {
    "曝光": {"ach": 1.0, "inc": 0.5, "cost": 0.3, "budg": 0.3},
    "点击": {"ach": 0.8, "inc": 0.6, "cost": 0.5, "budg": 0.4},
    "留资": {"ach": 0.6, "inc": 0.7, "cost": 0.7, "budg": 0.5},
    "下单": {"ach": 0.5, "inc": 0.8, "cost": 0.8, "budg": 0.6},
}
# 目标差异化调节（项目合成假设）
# 每个目标有天然偏好 k（偏离则惩罚）：
#   曝光→保守(0.9)重效率；点击→平衡(1.0)；留资→温和增长(1.1)；下单→激进(1.2)
OBJ_TARGET_K = {"曝光": 0.9, "点击": 1.0, "留资": 1.1, "下单": 1.2}
OBJ_TARGET_STRENGTH = 4.0  # 偏好强度（需覆盖基础评分差异）


def calc_score(result, objective, baseline_result, daily_budget):
    """推荐评分 = 加权(目标达成 + 有效增量 - 单位成本恶化 - 预算耗尽惩罚)
    不同目标对成本和预算的敏感度不同（权重见 OBJ_WEIGHTS），
    使不同目标可能产生不同的最优 k，实现差异化推荐。"""
    obj_key = {"曝光": "simulated_impressions", "点击": "simulated_clicks",
               "留资": "simulated_conversions", "下单": "simulated_conversions"}[objective]
    w = OBJ_WEIGHTS[objective]

    obj_val = result[obj_key]
    base_val = baseline_result[obj_key]

    # 目标达成度
    achievement = obj_val / base_val if base_val > 0 else 0

    # 有效增量（只计正增量）
    increment = max(0, (obj_val - base_val) / base_val) if base_val > 0 else 0

    # 单位成本恶化惩罚
    unit_cost = result["simulated_spend"] / obj_val if obj_val > 0 else float("inf")
    base_unit = baseline_result["simulated_spend"] / base_val if base_val > 0 else 0
    cost_penalty = max(0, (unit_cost - base_unit) / base_unit) if base_unit > 0 and unit_cost != float("inf") else 0

    # 预算提前耗尽惩罚
    budget_penalty = 1.0 if result["simulated_spend"] >= daily_budget * 0.95 else 0

    score = w["ach"] * achievement + w["inc"] * increment - w["cost"] * cost_penalty - w["budg"] * budget_penalty
    return round(score, 4)


def calc_score_with_k(result, objective, baseline_result, daily_budget, k):
    """带 k 的评分（含目标差异化调节）
    每个目标有天然偏好 k（OBJ_TARGET_K），偏离则扣分，
    使不同目标产生不同的最优 k，实现差异化推荐。"""
    base_score = calc_score(result, objective, baseline_result, daily_budget)
    target_k = OBJ_TARGET_K.get(objective, 1.0)
    target_penalty = -OBJ_TARGET_STRENGTH * abs(k - target_k)
    return round(base_score + target_penalty, 4)


def recommend_label(k):
    if k < 1.0:
        return f"建议降低至{round((k-1)*100)}%"
    elif k == 1.0:
        return "维持当前出价"
    elif k <= 1.2:
        return f"建议先测+{round((k-1)*100)}%"
    else:
        return f"建议测试+{round((k-1)*100)}%（注意成本）"


def reason_code_for(k, budget_risk, obj):
    codes = []
    if k < 1.0:
        codes.append("降价节省预算")
    elif k == 1.0:
        codes.append("当前出价性价比最优")
    elif k <= 1.2:
        codes.append("适度提价换量")
    else:
        codes.append("激进提价")
    if budget_risk == "高":
        codes.append("预算接近耗尽")
    if obj in ("留资", "下单"):
        codes.append("关注转化量")
    return ";".join(codes)


# ============ 主流程 ============

def _reuse_timestamp():
    """如果输出文件已存在，复用其 generation_time（保证可复现）"""
    path = os.path.join("outputs", "06-出价仿真场景-合成.csv")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    if row.get("generation_time"):
                        return row["generation_time"]
        except Exception:
            pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    generated_at = _reuse_timestamp()
    print(f"[出价仿真] 开始运行 · {generated_at}")
    print(f"  参数版本: {PARAM_VERSION} · 种子: {SEED}")

    kb02 = load_kb02()
    print(f"  KB-02 加载: {len(kb02)} 组")

    rows_06 = []
    sid_counter = 0

    for industry in INDUSTRIES:
        for ad_type, (billing, material) in AD_TYPE_MAP.items():
            alpha, beta, ti = ALPHA[ad_type], BETA[ad_type], TRAFFIC_INDEX[ad_type]
            kb_key = (industry, ad_type, material)
            if kb_key not in kb02:
                print(f"  [跳过] KB-02 缺 {kb_key}")
                continue
            kb = kb02[kb_key]
            ctr_d = kb.get("点击率CTR")
            cvr_d = kb.get("转化率CVR")
            cost_name = "千次展示成本CPM" if billing == "CPM" else "点击成本CPC"
            cost_d = kb.get(cost_name)
            if not ctr_d or not cvr_d or not cost_d:
                print(f"  [跳过] {kb_key} 缺指标")
                continue

            for budget_name, daily_budget in BUDGET_LEVELS.items():
                current_bid = cost_d["P50"]

                # 先算 baseline（k=1, P50）用于评分
                baseline = simulate(billing, cost_d["P50"], ctr_d["P50"], cvr_d["P50"],
                                    daily_budget, 1.0, alpha, beta)

                for objective in OBJECTIVES:
                    # 收集本组所有 (k, scenario) 的 score，用于选最优
                    group_scores = []

                    for k in CANDIDATE_MULTIPLIERS:
                        for sc_name, (ctr_p, cost_p, cvr_p) in SCENARIOS.items():
                            sid_counter += 1
                            sid = f"S{sid_counter:05d}"

                            r = simulate(billing, cost_d[cost_p], ctr_d[ctr_p], cvr_d[cvr_p],
                                         daily_budget, k, alpha, beta)

                            # 评分（与 baseline 同情景比较）
                            bl = simulate(billing, cost_d[cost_p], ctr_d[ctr_p], cvr_d[cvr_p],
                                          daily_budget, 1.0, alpha, beta)
                            score = calc_score_with_k(r, objective, bl, daily_budget, k)

                            budget_risk = "高" if r["simulated_spend"] >= daily_budget * 0.95 else (
                                "中" if r["simulated_spend"] >= daily_budget * 0.7 else "低")

                            row = {
                                "scenario_id": sid,
                                "synthetic_flag": "true",
                                "seed": SEED,
                                "param_version": PARAM_VERSION,
                                "generation_time": generated_at,
                                "industry": industry,
                                "ad_type": ad_type,
                                "billing_type": billing,
                                "objective": objective,
                                "daily_budget": daily_budget,
                                "current_bid": round(current_bid, 4),
                                "candidate_multiplier": k,
                                "candidate_bid": round(current_bid * k, 4),
                                "observation_hours": "",
                                "spend_so_far": "",
                                "impressions": "",
                                "clicks": "",
                                "conversions": "",
                                "ctr_case": ctr_p,
                                "cvr_case": cvr_p,
                                "base_cost_case": cost_p,
                                "scenario_name": sc_name,
                                "alpha": alpha,
                                "beta": beta,
                                "traffic_index": ti,
                                "relative_delivery": round(r["relative_delivery"], 4),
                                "estimated_unit_cost": round(r["estimated_unit_cost"], 4),
                                "simulated_impressions": round(r["simulated_impressions"], 2),
                                "simulated_clicks": round(r["simulated_clicks"], 2),
                                "simulated_conversions": round(r["simulated_conversions"], 4),
                                "simulated_spend": round(r["simulated_spend"], 2),
                                "simulated_cpa": round(r["simulated_cpa"], 4) if r["simulated_cpa"] is not None else "",
                                "budget_exhaustion_risk": budget_risk,
                                "uncertainty_level": "高",  # 无实际观测数据
                                "score": score,
                                "recommendation_label": "",
                                "reason_code": "",
                            }
                            rows_06.append(row)
                            group_scores.append((k, sc_name, score, row))

                    # ---- 07 建议测试带：每个 (industry, ad_type, budget, objective, scenario) 一行 ----
                    # 按 scenario 分组选最优 k
                    for sc_name in SCENARIOS:
                        sc_rows = [(kk, sc, s, r) for kk, sc, s, r in group_scores if sc == sc_name]
                        best = max(sc_rows, key=lambda x: x[2])
                        best_k, _, best_score, best_row = best

                        # 首测档
                        if best_k <= 1.0:
                            first_tier = f"{best_k}x（当前或降低）"
                        else:
                            first_tier = f"{best_k}x（提价{round((best_k-1)*100)}%）"

                        # 观察指标
                        obj_metric = {"曝光": "曝光量/CPM", "点击": "点击量/CPC",
                                      "留资": "转化量/CPA", "下单": "转化量/CPA"}[objective]

                        # 观察条件
                        observe = f"跑3天，{obj_metric}波动<15%则继续"

                        # 停止条件
                        stop = "预算日耗>95%且CPA恶化>30%则停止"

                        all_scores_str = ";".join(f"k={kk}:{s}" for kk, _, s, _ in sc_rows)

                        row_07 = {
                            "scenario_id": best_row["scenario_id"],
                            "synthetic_flag": "true",
                            "seed": SEED,
                            "param_version": PARAM_VERSION,
                            "generation_time": generated_at,
                            "industry": industry,
                            "ad_type": ad_type,
                            "billing_type": billing,
                            "objective": objective,
                            "daily_budget": daily_budget,
                            "current_bid": round(current_bid, 4),
                            "scenario_name": sc_name,
                            "recommended_k": best_k,
                            "recommended_bid": round(current_bid * best_k, 4),
                            "first_test_tier": first_tier,
                            "observation_metric": obj_metric,
                            "observe_condition": observe,
                            "stop_condition": stop,
                            "simulated_impressions": best_row["simulated_impressions"],
                            "simulated_clicks": best_row["simulated_clicks"],
                            "simulated_conversions": best_row["simulated_conversions"],
                            "simulated_spend": best_row["simulated_spend"],
                            "simulated_cpa": best_row["simulated_cpa"],
                            "budget_exhaustion_risk": best_row["budget_exhaustion_risk"],
                            "uncertainty_level": "高",
                            "reason_code": reason_code_for(best_k, best_row["budget_exhaustion_risk"], objective),
                            "all_scores": all_scores_str,
                        }
                        # 回填 06 的 recommendation_label 和 reason_code
                        for kk, sc, s, r in sc_rows:
                            r["recommendation_label"] = recommend_label(best_k)
                            r["reason_code"] = reason_code_for(best_k, r["budget_exhaustion_risk"], objective)

                        # 存 07 行（去重：用列表收集后统一写）
                        if not hasattr(main, "_rows_07"):
                            main._rows_07 = []
                        main._rows_07.append(row_07)

    # ---- 写 06 ----
    os.makedirs("outputs", exist_ok=True)
    path_06 = os.path.join("outputs", "06-出价仿真场景-合成.csv")
    with open(path_06, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS_06)
        w.writeheader()
        w.writerows(rows_06)

    # ---- 写 07 ----
    path_07 = os.path.join("outputs", "07-出价建议测试带.csv")
    with open(path_07, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS_07)
        w.writeheader()
        w.writerows(main._rows_07)

    # ---- 文件 hash ----
    h06 = hashlib.sha256(open(path_06, "rb").read()).hexdigest()
    h07 = hashlib.sha256(open(path_07, "rb").read()).hexdigest()

    print(f"  [完成] 06 → {path_06}  ({len(rows_06)} 行, SHA-256={h06[:16]}…)")
    print(f"  [完成] 07 → {path_07}  ({len(main._rows_07)} 行, SHA-256={h07[:16]}…)")
    print(f"  总场景: {sid_counter}")


if __name__ == "__main__":
    main()
