"""成本计算器 —— 单用户成本、累计预算控制、ROI 与净收益计算、干预效果模拟"""

from typing import Optional

from config import settings


# ========== 单用户成本 ==========

def calc_single_cost(strategy_type: str) -> float:
    """根据策略类型返回单用户干预成本"""
    cost_map = {
        "low_activity": settings.COSTS["push"],
        "interest_shift": settings.COSTS["vip"],
        "content_fatigue": settings.COSTS["vip"],
        "social_isolation": settings.COSTS["manual"],
        "function_issue": settings.COSTS["manual"],
    }
    return cost_map.get(strategy_type, settings.COSTS["push"])


# ========== 累计成本 ==========

def calc_total_cost(candidates: list[dict]) -> float:
    """计算已入选用户的总干预成本"""
    return sum(c.get("cost", 0) for c in candidates)


# ========== 预算控制 ==========

def is_within_budget(current_cost: float, additional_cost: float, budget_limit: float = None) -> bool:
    """检查追加成本后是否仍在预算内"""
    if budget_limit is None:
        budget_limit = settings.BUDGET_LIMIT
    return (current_cost + additional_cost) <= budget_limit


def budget_remaining(total_cost: float, budget_limit: float = None) -> float:
    """返回剩余预算"""
    if budget_limit is None:
        budget_limit = settings.BUDGET_LIMIT
    return max(0.0, budget_limit - total_cost)


# ========== ROI 与净收益 ==========

def calc_expected_ltv(user: dict) -> float:
    """根据用户价值层级估算单用户预期挽回 LTV"""
    value_tier = user.get("value_tier", "low")
    return settings.VALUE_LTV.get(value_tier, 0)


def calc_total_ltv(candidates: list[dict], retention_rate: float = None) -> float:
    """计算入选用户的总预期挽回 LTV

    total_ltv = sum(每个用户 LTV) × retention_rate
    """
    if retention_rate is None:
        retention_rate = settings.RETENTION_BASELINE["ai_personalized"]
    total = sum(calc_expected_ltv(c) for c in candidates)
    return total * retention_rate


def calc_roi(total_ltv: float, total_cost: float) -> float:
    """ROI = (总挽回 LTV - 总成本) / 总成本"""
    if total_cost == 0:
        return 0.0
    return (total_ltv - total_cost) / total_cost


def calc_net_revenue(total_ltv: float, total_cost: float) -> float:
    """净收益 = 总挽回 LTV - 总成本"""
    return total_ltv - total_cost


# ========== 干预效果模拟（7 日四组对比）==========

def simulate_intervention_effect(
    candidates: list[dict],
    target_users: int = None,
) -> dict:
    """模拟四种干预策略的 7 日效果对比

    四组对照：
    - no_intervention: 不干预
    - generic_coupon: 通用发券
    - rule_based: 规则干预
    - ai_personalized: AI 个性化

    Returns:
        {strategy: {retained_users, saved_users, total_cost, total_ltv, net_revenue, roi}}
    """
    if target_users is None:
        target_users = len(candidates)
    if target_users == 0:
        return _empty_simulation_result()

    baseline = settings.RETENTION_BASELINE
    results = {}

    for strategy, retention_rate in baseline.items():
        retained = int(target_users * retention_rate)
        saved = retained  # 简化：留存即挽回
        # 成本估算
        if strategy == "no_intervention":
            total_cost = 0.0
        elif strategy == "generic_coupon":
            total_cost = target_users * settings.COSTS["push"]
        elif strategy == "rule_based":
            total_cost = target_users * settings.COSTS["vip"] * 0.5
        else:  # ai_personalized
            total_cost = target_users * settings.COSTS["vip"]

        total_ltv = saved * settings.VALUE_LTV["mid"]  # 保守取 mid 层 LTV
        net_revenue = calc_net_revenue(total_ltv, total_cost)
        roi = calc_roi(total_ltv, total_cost)

        results[strategy] = {
            "target_users": target_users,
            "retained_users": retained,
            "saved_users": saved,
            "total_cost": round(total_cost, 2),
            "total_ltv": round(total_ltv, 2),
            "net_revenue": round(net_revenue, 2),
            "roi": round(roi, 4),
        }

    return results


def _empty_simulation_result() -> dict:
    """空结果模板"""
    return {
        strategy: {
            "target_users": 0,
            "retained_users": 0,
            "saved_users": 0,
            "total_cost": 0.0,
            "total_ltv": 0.0,
            "net_revenue": 0.0,
            "roi": 0.0,
        }
        for strategy in settings.RETENTION_BASELINE
    }


# ========== 批量成本汇总 ==========

def summarize_costs(candidates: list[dict]) -> dict:
    """汇总候选用户的成本分布"""
    if not candidates:
        return {"total_cost": 0.0, "by_strategy": {}, "by_tier": {}, "avg_cost": 0.0}

    total_cost = calc_total_cost(candidates)
    by_strategy = {}
    by_tier = {}

    for c in candidates:
        strategy = c.get("strategy_type", "unknown")
        tier = c.get("value_tier", "low")
        cost = c.get("cost", 0)

        by_strategy[strategy] = by_strategy.get(strategy, 0) + cost
        by_tier[tier] = by_tier.get(tier, 0) + cost

    return {
        "total_cost": round(total_cost, 2),
        "by_strategy": by_strategy,
        "by_tier": by_tier,
        "avg_cost": round(total_cost / len(candidates), 2),
        "user_count": len(candidates),
    }