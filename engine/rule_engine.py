"""规则引擎 —— 流失风险评估、标签权重、干预优先级、干预防护规则"""

from datetime import datetime, timedelta
from typing import Any, Optional

from config import settings


# ========== 价值系数 ==========

def get_value_coefficient(value_tier: str) -> float:
    """根据用户 value_tier 字段返回价值系数（规则 7.1）"""
    mapping = {"high": 1.5, "mid": 1.0, "low": 0.5}
    return mapping.get(value_tier, 1.0)


# ========== 风险评分（规则 7.2）==========

def calc_risk_score(user: dict) -> int:
    """计算用户风险评分，返回 0-100 之间的整数"""
    last_active = user.get("last_active_days", 0)
    complaint = user.get("complaint_record", "")

    # 投诉用户：raw_score 直接设为 80，不叠加基础分和维度加分
    if complaint != "":
        raw_score = 80
    else:
        # 基础分
        if last_active > 14:
            base = 60
        elif last_active > 7:
            base = 30
        else:
            base = 0

        # 维度加分
        interest_bonus = 30 if user.get("favorite_genre") != user.get("recent_genre") else 0
        fatigue_bonus = 25 if (user.get("play_days_last_7", 0) >= 5 and user.get("new_playlists_added", 0) <= 2) else 0
        isolation_bonus = 15 if (user.get("social_interaction", 0) <= 3 and user.get("social_following", 0) <= 10) else 0

        raw_score = base + interest_bonus + fatigue_bonus + isolation_bonus

    # 周期性调整：weekend_active 且当前非周末，减 10 分
    if user.get("periodic_pattern", "") == "weekend_active" and not _is_weekend():
        raw_score -= 10

    # 钳位 0-100
    return max(0, min(100, raw_score))


# ========== 标签权重（规则 7.3）==========

def calc_tag_weights(user: dict) -> dict:
    """计算多标签权重，返回各维度权重字典"""
    weights = {
        "interest_shift": 0.0,
        "content_fatigue": 0.0,
        "social_isolation": 0.0,
        "low_activity": 0.0,
        "function_issue": 0.0,
    }

    complaint = user.get("complaint_record", "")

    # 投诉用户：function_issue 权重 1.0
    if complaint != "":
        weights["function_issue"] = 1.0
        return weights

    # 非投诉用户：各维度原始贡献值 / 贡献总和
    last_active = user.get("last_active_days", 0)
    if last_active > 14:
        base = 60
    elif last_active > 7:
        base = 30
    else:
        base = 0

    interest_bonus = 30 if user.get("favorite_genre") != user.get("recent_genre") else 0
    fatigue_bonus = 25 if (user.get("play_days_last_7", 0) >= 5 and user.get("new_playlists_added", 0) <= 2) else 0
    isolation_bonus = 15 if (user.get("social_interaction", 0) <= 3 and user.get("social_following", 0) <= 10) else 0

    total = base + interest_bonus + fatigue_bonus + isolation_bonus
    if total > 0:
        weights["low_activity"] = base / total
        weights["interest_shift"] = interest_bonus / total
        weights["content_fatigue"] = fatigue_bonus / total
        weights["social_isolation"] = isolation_bonus / total
    else:
        weights["low_activity"] = 1.0

    return weights


def get_primary_secondary_tags(weights: dict) -> tuple:
    """从权重字典中提取 primary_tag 和 secondary_tag"""
    sorted_tags = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    primary = sorted_tags[0][0]
    # 次高权重为 0 时，secondary = primary
    secondary = sorted_tags[1][0] if sorted_tags[1][1] > 0 else primary
    return primary, secondary


# ========== 干预优先级（规则 7.4）==========

def calc_priority_score(risk_score: int, value_tier: str) -> float:
    """priority_score = risk_score × value_coefficient"""
    return risk_score * get_value_coefficient(value_tier)


# ========== 干预适配性判断（规则 7.6）==========

def is_intervention_applicable(user: dict) -> bool:
    """complaint_record 非空 → 不进入常规干预池，需流转客服/产品团队"""
    return user.get("complaint_record", "") == ""


# ========== 干预防护规则（规则 7.5）==========

def _is_weekend() -> bool:
    """判断当前是否为周末（周六/周日）"""
    return datetime.now().weekday() >= 5


def _check_cooldown(user_id: str, history: dict) -> bool:
    """检查用户是否在冷却期内（7 天内已干预过）

    history 格式: {user_id: {"last_intervention_date": datetime, "strategy_types": [...], "aversion_tags": [...]}}
    """
    if history is None or user_id not in history:
        return False
    last_date = history[user_id].get("last_intervention_date")
    if last_date is None:
        return False
    return (datetime.now() - last_date).days < settings.COOLDOWN_DAYS


def _check_strategy_dedup(user_id: str, strategy_type: str, history: dict) -> bool:
    """检查 30 天内是否已使用过同一策略类型

    strategy_type 对应 primary_tag: low_activity / interest_shift / content_fatigue / social_isolation
    """
    if history is None or user_id not in history:
        return False
    strategies = history[user_id].get("strategy_types", [])
    for s in strategies:
        if s["type"] == strategy_type and (datetime.now() - s["date"]).days < 30:
            return True
    return False


def apply_aversion_adjustment(user_id: str, weights: dict, history: dict) -> dict:
    """应用反感标记：用户标记「不感兴趣」的标签权重降低 50%

    反感标记 90 天后自动恢复。
    """
    if history is None or user_id not in history:
        return weights
    aversion_tags = history[user_id].get("aversion_tags", [])
    now = datetime.now()
    adjusted = dict(weights)
    for tag_info in aversion_tags:
        tag = tag_info["tag"]
        marked_date = tag_info["date"]
        if (now - marked_date).days < 90 and tag in adjusted:
            adjusted[tag] *= 0.5
    # 重新归一化
    total = sum(adjusted.values())
    if total > 0:
        adjusted = {k: v / total for k, v in adjusted.items()}
    return adjusted


# ========== 综合评估 ==========

def evaluate_user(user: dict, history: Optional[dict] = None) -> dict:
    """对单个用户进行完整评估，返回所有评估指标"""
    risk_score = calc_risk_score(user)
    weights = calc_tag_weights(user)

    # 应用反感调整
    if history:
        weights = apply_aversion_adjustment(user["user_id"], weights, history)

    primary_tag, secondary_tag = get_primary_secondary_tags(weights)
    priority_score = calc_priority_score(risk_score, user.get("value_tier", "low"))
    applicable = is_intervention_applicable(user)

    return {
        "user_id": user["user_id"],
        "risk_score": risk_score,
        "tag_weights": weights,
        "primary_tag": primary_tag,
        "secondary_tag": secondary_tag,
        "priority_score": priority_score,
        "is_applicable": applicable,
    }


# ========== 批量筛选（规则 8）==========

def filter_intervention_candidates(
    users: list[dict],
    budget: float = None,
    history: Optional[dict] = None,
    risk_threshold: int = None,
) -> tuple[list[dict], float]:
    """基于预算约束筛选干预候选用户

    流程：
    1. 过滤 risk_score >= 风险阈值
    2. 过滤 is_applicable=True
    3. 过滤冷却期（7 天内已干预）
    4. 按 priority_score 降序排列
    5. 累加成本，超过预算截断

    Returns:
        (入选用户列表, 实际总成本)
    """
    if budget is None:
        budget = settings.BUDGET_LIMIT
    if risk_threshold is None:
        risk_threshold = settings.RISK_THRESHOLD

    candidates = []
    total_cost = 0.0

    # 先评估所有用户
    evaluated = []
    for user in users:
        result = evaluate_user(user, history)
        # 第一步：风险阈值过滤
        if result["risk_score"] < risk_threshold:
            continue
        # 第二步：适配性过滤
        if not result["is_applicable"]:
            continue
        # 第三步：冷却期过滤
        if _check_cooldown(user["user_id"], history):
            continue
        evaluated.append((user, result))

    # 第四步：按 priority_score 降序
    evaluated.sort(key=lambda x: x[1]["priority_score"], reverse=True)

    # 第五步：预算截断
    for user, result in evaluated:
        # 策略去重：30 天内同一策略类型不重复
        strategy_type = result["primary_tag"]
        # 功能体验类用户不应走到这里（is_applicable 已过滤），但保留防御
        if strategy_type == "function_issue":
            continue

        cost = _get_intervention_cost(strategy_type)
        if total_cost + cost > budget:
            break
        total_cost += cost
        candidates.append({
            "user_id": user["user_id"],
            "name": user.get("name", ""),
            "risk_score": result["risk_score"],
            "primary_tag": result["primary_tag"],
            "secondary_tag": result["secondary_tag"],
            "priority_score": result["priority_score"],
            "strategy_type": strategy_type,
            "cost": cost,
            "value_tier": user.get("value_tier", "low"),
            "expected_ltv": _get_expected_ltv(result),
        })

    return candidates, total_cost


def _get_intervention_cost(strategy_type: str) -> float:
    """根据策略类型获取干预成本"""
    cost_map = {
        "low_activity": settings.COSTS["push"],
        "interest_shift": settings.COSTS["vip"],
        "content_fatigue": settings.COSTS["vip"],
        "social_isolation": settings.COSTS["manual"],
        "function_issue": settings.COSTS["manual"],
    }
    return cost_map.get(strategy_type, settings.COSTS["push"])


def _get_expected_ltv(result: dict) -> float:
    """根据风险分和留存基线估算预期挽回 LTV"""
    # 简化：高风险用户预期挽回价值更高
    return result["risk_score"] * 0.5