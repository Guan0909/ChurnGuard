"""Mock 数据校验脚本 —— 遍历所有用户，比对规则引擎计算值与 mock_responses.json 的理论值"""

import json
import os
from typing import Any


# ========== 数据加载 ==========

def _load_json(filename: str) -> Any:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "data", filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ========== 规则引擎逻辑（与 engine/rule_engine.py 完全镜像）==========

def _calc_risk_score(user: dict) -> int:
    """计算风险评分，规则严格对齐项目规则第 7.2 节"""
    last_active = user["last_active_days"]

    # 基础分
    if last_active > 14:
        base = 60
    elif last_active > 7:
        base = 30
    else:
        base = 0

    # 维度加分
    interest_bonus = 30 if user["favorite_genre"] != user["recent_genre"] else 0
    fatigue_bonus = 25 if (user["play_days_last_7"] >= 5 and user["new_playlists_added"] <= 2) else 0
    isolation_bonus = 15 if (user["social_interaction"] <= 3 and user["social_following"] <= 10) else 0

    # 功能体验 → 直接 80 分
    if user.get("complaint_record", "") != "":
        score = 80
    else:
        score = base + interest_bonus + fatigue_bonus + isolation_bonus

    # 周期性调整
    if user.get("periodic_pattern", "") == "weekend_active" and score > 0:
        score -= 10

    return max(0, min(100, score))


def _calc_tag_weights(user: dict, risk_score: int) -> dict:
    """计算标签权重，规则严格对齐项目规则第 7.3 节"""
    weights = {
        "interest_shift": 0.0,
        "content_fatigue": 0.0,
        "social_isolation": 0.0,
        "low_activity": 0.0,
        "function_issue": 0.0,
    }

    if user.get("complaint_record", "") != "":
        weights["function_issue"] = 1.0
        return weights

    last_active = user["last_active_days"]
    if last_active > 14:
        base = 60
    elif last_active > 7:
        base = 30
    else:
        base = 0

    interest_bonus = 30 if user["favorite_genre"] != user["recent_genre"] else 0
    fatigue_bonus = 25 if (user["play_days_last_7"] >= 5 and user["new_playlists_added"] <= 2) else 0
    isolation_bonus = 15 if (user["social_interaction"] <= 3 and user["social_following"] <= 10) else 0

    total = base + interest_bonus + fatigue_bonus + isolation_bonus
    if total > 0:
        weights["low_activity"] = base / total
        weights["interest_shift"] = interest_bonus / total
        weights["content_fatigue"] = fatigue_bonus / total
        weights["social_isolation"] = isolation_bonus / total
    else:
        weights["low_activity"] = 1.0

    return weights


def _get_primary_secondary(weights: dict) -> tuple:
    """从权重字典中取 primary_tag 和 secondary_tag"""
    sorted_tags = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    primary = sorted_tags[0][0]
    secondary = sorted_tags[1][0] if len(sorted_tags) > 1 else primary
    if sorted_tags[1][1] == 0:
        secondary = primary
    return primary, secondary


def _calc_priority_score(risk_score: int, value_tier: str) -> float:
    """计算干预优先级"""
    coeff = {"high": 1.5, "mid": 1.0, "low": 0.5}
    return risk_score * coeff.get(value_tier, 1.0)


def _is_applicable(user: dict) -> bool:
    """判断是否可进入常规干预池"""
    return user.get("complaint_record", "") == ""


# ========== 校验主逻辑 ==========

def validate() -> list[dict]:
    """遍历所有用户，比对理论值与 mock 数据，返回偏差用户列表"""
    users = _load_json("users.json")
    mock = _load_json("mock_responses.json")
    classifications = {c["user_id"]: c for c in mock["classification"]}

    deviations = []

    for user in users:
        uid = user["user_id"]
        mock_entry = classifications.get(uid)

        if mock_entry is None:
            deviations.append({
                "user_id": uid,
                "field": "missing",
                "expected": "存在",
                "actual": "缺失",
            })
            continue

        # 风险分
        expected_score = _calc_risk_score(user)
        if mock_entry["risk_score"] != expected_score:
            deviations.append({
                "user_id": uid,
                "field": "risk_score",
                "expected": expected_score,
                "actual": mock_entry["risk_score"],
            })

        # 标签权重
        expected_weights = _calc_tag_weights(user, expected_score)
        for tag in expected_weights:
            if abs(mock_entry["tag_weights"].get(tag, 0) - expected_weights[tag]) > 0.001:
                deviations.append({
                    "user_id": uid,
                    "field": f"tag_weights.{tag}",
                    "expected": round(expected_weights[tag], 4),
                    "actual": round(mock_entry["tag_weights"].get(tag, 0), 4),
                })

        # primary_tag / secondary_tag
        exp_primary, exp_secondary = _get_primary_secondary(expected_weights)
        if mock_entry["primary_tag"] != exp_primary:
            deviations.append({
                "user_id": uid,
                "field": "primary_tag",
                "expected": exp_primary,
                "actual": mock_entry["primary_tag"],
            })
        if mock_entry["secondary_tag"] != exp_secondary:
            deviations.append({
                "user_id": uid,
                "field": "secondary_tag",
                "expected": exp_secondary,
                "actual": mock_entry["secondary_tag"],
            })

        # 优先级
        expected_priority = _calc_priority_score(expected_score, user["value_tier"])
        if abs(mock_entry["priority_score"] - expected_priority) > 0.001:
            deviations.append({
                "user_id": uid,
                "field": "priority_score",
                "expected": expected_priority,
                "actual": mock_entry["priority_score"],
            })

        # 干预适配性
        expected_applicable = _is_applicable(user)
        if mock_entry["is_applicable"] != expected_applicable:
            deviations.append({
                "user_id": uid,
                "field": "is_applicable",
                "expected": expected_applicable,
                "actual": mock_entry["is_applicable"],
            })

    return deviations


# ========== 入口 ==========

if __name__ == "__main__":
    devs = validate()
    if devs:
        print(f"发现 {len(devs)} 个偏差：")
        for d in devs:
            print(f"  {d['user_id']} | {d['field']} | 期望={d['expected']} | 实际={d['actual']}")
    else:
        print("所有用户标签与分数偏差为 0，校验通过！")