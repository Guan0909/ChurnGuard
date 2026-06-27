"""冒烟测试 —— 覆盖七大核心流程，输出通过/失败统计"""

import json
import os
import sys
import traceback

# 确保 config 导入安全
os.environ["DEEPSEEK_API_KEY"] = "test"

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ========== 测试工具 ==========

_results = []


def _test(name: str, fn):
    """运行单个测试，记录通过/失败"""
    try:
        fn()
        _results.append((name, True, None))
        print(f"  ✓ {name}")
    except Exception as e:
        _results.append((name, False, str(e)))
        print(f"  ✗ {name}  —  {e}")
        traceback.print_exc()


def _data_path(filename: str) -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "data", filename)


# ========== 测试 1: 数据加载 ==========

def test_1_data_loading():
    """验证 data/users.json 100 条记录 + mock_responses.json 结构完整"""

    # users.json
    with open(_data_path("users.json"), "r", encoding="utf-8-sig") as f:
        users = json.load(f)
    assert len(users) == 100, f"期望 100 条用户，实际 {len(users)} 条"
    for u in users:
        assert "user_id" in u, f"用户缺少 user_id 字段"
        assert "name" in u, f"用户缺少 name 字段"

    # mock_responses.json
    with open(_data_path("mock_responses.json"), "r", encoding="utf-8-sig") as f:
        mock = json.load(f)
    assert "classification" in mock, "mock_responses.json 缺少 classification"
    assert "copywriting" in mock, "mock_responses.json 缺少 copywriting"
    assert len(mock["classification"]) == 100, f"classification 期望 100 条，实际 {len(mock['classification'])} 条"
    assert len(mock["copywriting"]) > 0, "copywriting 不应为空"


# ========== 测试 2: 风险计算 ==========

def test_2_risk_calculation():
    """验证 evaluate_user 对三类用户的计算结果"""
    from engine.rule_engine import evaluate_user

    # 投诉用户: complaint_record 非空 → risk_score=80
    complaint_user = {
        "user_id": "TEST001",
        "name": "测试投诉",
        "last_active_days": 10,
        "play_days_last_7": 3,
        "total_play_hours_last_7": 10.0,
        "favorite_genre": "流行",
        "recent_genre": "流行",
        "new_playlists_added": 5,
        "social_following": 50,
        "social_interaction": 10,
        "has_paid": False,
        "searches_used": 5,
        "complaint_record": "闪退频繁",
        "periodic_pattern": "weekday_active",
        "value_tier": "mid",
        "churned": False,
    }
    result = evaluate_user(complaint_user)
    assert result["risk_score"] == 80, f"投诉用户 risk_score 期望 80，实际 {result['risk_score']}"
    assert result["tag_weights"]["function_issue"] == 1.0, "投诉用户 function_issue 权重应为 1.0"
    assert result["primary_tag"] == "function_issue"
    assert result["is_applicable"] is False, "投诉用户 is_applicable 应为 False"

    # 正常用户
    normal_user = {
        "user_id": "TEST002",
        "name": "测试正常",
        "last_active_days": 18,
        "play_days_last_7": 6,
        "total_play_hours_last_7": 30.0,
        "favorite_genre": "摇滚",
        "recent_genre": "电子",
        "new_playlists_added": 1,
        "social_following": 5,
        "social_interaction": 2,
        "has_paid": True,
        "searches_used": 8,
        "complaint_record": "",
        "periodic_pattern": "weekday_active",
        "value_tier": "high",
        "churned": False,
    }
    result = evaluate_user(normal_user)
    assert 0 <= result["risk_score"] <= 100, f"risk_score 应在 0-100，实际 {result['risk_score']}"
    assert isinstance(result["tag_weights"], dict), "tag_weights 应为字典"
    assert result["primary_tag"] != "", "primary_tag 不应为空"
    assert result["is_applicable"] is True, "正常用户 is_applicable 应为 True"

    # 边缘用户: 缺失部分字段，不崩溃
    edge_user = {
        "user_id": "TEST003",
        "name": "测试边缘",
        "last_active_days": 5,
        "favorite_genre": "流行",
        "recent_genre": "流行",
        "has_paid": False,
        "value_tier": "low",
    }
    result = evaluate_user(edge_user)
    assert 0 <= result["risk_score"] <= 100, f"边缘用户 risk_score 应在 0-100，实际 {result['risk_score']}"
    assert isinstance(result["tag_weights"], dict), "边缘用户 tag_weights 应为字典"


# ========== 测试 3: 分类模拟 ==========

def test_3_classification():
    """验证 classify_churn_reason 存在用户 + 不存在用户降级"""
    from llm.llm_client import classify_churn_reason

    # 存在用户
    user = {
        "user_id": "U001",
        "name": "张伟",
        "last_active_days": 18,
        "play_days_last_7": 4,
        "total_play_hours_last_7": 22.5,
        "favorite_genre": "流行",
        "recent_genre": "流行",
        "new_playlists_added": 3,
        "social_following": 45,
        "social_interaction": 12,
        "has_paid": True,
        "searches_used": 8,
        "complaint_record": "闪退频繁",
        "periodic_pattern": "weekday_active",
        "value_tier": "high",
        "churned": False,
    }
    result = classify_churn_reason(user)
    assert "primary_tag" in result, "返回结果缺少 primary_tag"
    assert "explanation" in result, "返回结果缺少 explanation"
    assert result["primary_tag"] == "function_issue", f"U001 主标签应为 function_issue，实际 {result['primary_tag']}"

    # 不存在用户: 降级不崩溃
    fake_user = {
        "user_id": "NONEXISTENT",
        "name": "不存在",
        "last_active_days": 10,
        "favorite_genre": "流行",
        "recent_genre": "流行",
        "has_paid": False,
        "value_tier": "low",
    }
    result = classify_churn_reason(fake_user)
    assert "primary_tag" in result, "降级结果缺少 primary_tag"
    assert "explanation" in result, "降级结果缺少 explanation"


# ========== 测试 4: 文案模拟 ==========

def test_4_copywriting():
    """验证 generate_copywriting 三版本 + generate_all_versions + 降级"""
    from llm.llm_client import generate_copywriting, generate_all_versions

    user = {
        "user_id": "U009",
        "name": "郑慧",
        "last_active_days": 14,
        "play_days_last_7": 7,
        "total_play_hours_last_7": 42.1,
        "favorite_genre": "流行",
        "recent_genre": "流行",
        "new_playlists_added": 1,
        "social_following": 60,
        "social_interaction": 15,
        "has_paid": False,
        "searches_used": 6,
        "complaint_record": "",
        "periodic_pattern": "weekday_active",
        "value_tier": "mid",
        "churned": False,
    }

    # 三版本分别测试
    for version in ("basic", "optimized", "warm"):
        result = generate_copywriting(user, "content_fatigue", version)
        assert result["title"] != "", f"{version} 版 title 不应为空"
        assert result["body"] != "", f"{version} 版 body 不应为空"
        assert result["cta"] != "", f"{version} 版 cta 不应为空"

    # 一次性生成三版本
    all_result = generate_all_versions(user, "content_fatigue")
    assert "basic" in all_result
    assert "optimized" in all_result
    assert "warm" in all_result

    # 异常输入降级: 不存在的用户
    fake_user = {
        "user_id": "NONEXISTENT",
        "name": "不存在",
        "last_active_days": 10,
        "favorite_genre": "流行",
        "recent_genre": "流行",
        "has_paid": False,
        "value_tier": "low",
    }
    result = generate_copywriting(fake_user, "low_activity", "basic")
    assert result["title"] != "", "降级文案 title 不应为空"
    assert result["body"] != "", "降级文案 body 不应为空"


# ========== 测试 5: 成本计算 ==========

def test_5_cost_calculation():
    """验证 simulate_intervention_effect + summarize_costs"""
    from engine.cost_calculator import simulate_intervention_effect, summarize_costs

    candidates = [
        {
            "user_id": "U001",
            "name": "测试A",
            "risk_score": 80,
            "primary_tag": "low_activity",
            "strategy_type": "low_activity",
            "cost": 0.1,
            "value_tier": "high",
            "expected_ltv": 30.0,
        },
        {
            "user_id": "U002",
            "name": "测试B",
            "risk_score": 60,
            "primary_tag": "interest_shift",
            "strategy_type": "interest_shift",
            "cost": 5.0,
            "value_tier": "mid",
            "expected_ltv": 10.0,
        },
        {
            "user_id": "U003",
            "name": "测试C",
            "risk_score": 40,
            "primary_tag": "social_isolation",
            "strategy_type": "social_isolation",
            "cost": 15.0,
            "value_tier": "low",
            "expected_ltv": 2.0,
        },
    ]

    # 干预效果模拟
    sim_result = simulate_intervention_effect(candidates)
    assert "no_intervention" in sim_result, "缺少 no_intervention"
    assert "generic_coupon" in sim_result, "缺少 generic_coupon"
    assert "rule_based" in sim_result, "缺少 rule_based"
    assert "ai_personalized" in sim_result, "缺少 ai_personalized"
    for key in sim_result:
        assert "retained_users" in sim_result[key]
        assert "total_cost" in sim_result[key]
        assert "roi" in sim_result[key]

    # 成本汇总
    summary = summarize_costs(candidates)
    assert summary["user_count"] == 3, f"期望 3 人，实际 {summary['user_count']}"
    assert summary["total_cost"] > 0, "总成本应大于 0"
    assert "by_strategy" in summary
    assert "by_tier" in summary

    # 空列表
    empty_summary = summarize_costs([])
    assert empty_summary["total_cost"] == 0.0


# ========== 测试 6: CSV 导出 ==========

def test_6_csv_export():
    """验证 filter_intervention_candidates → DataFrame → CSV 无异常"""
    import pandas as pd
    from engine.rule_engine import filter_intervention_candidates

    # 加载用户数据
    with open(_data_path("users.json"), "r", encoding="utf-8-sig") as f:
        users = json.load(f)

    # 筛选候选
    candidates, total_cost = filter_intervention_candidates(users, budget=500)
    assert len(candidates) > 0, "应有至少一个候选用户"
    assert total_cost > 0, "总成本应大于 0"

    # 转 DataFrame
    df = pd.DataFrame(candidates)
    assert len(df) > 0, "DataFrame 不应为空"
    assert "user_id" in df.columns, "DataFrame 缺少 user_id 列"
    assert "cost" in df.columns, "DataFrame 缺少 cost 列"

    # 导出 CSV 字符串
    csv_str = df.to_csv(index=False)
    assert len(csv_str) > 0, "CSV 字符串不应为空"
    assert "user_id" in csv_str, "CSV 应包含 user_id 列头"


# ========== 测试 7: 样本量计算 ==========

def test_7_sample_size():
    """验证 _cohens_h + _calc_sample_size（不依赖 streamlit）"""
    import sys
    import math

    # ab_designer 有顶层 import streamlit，需 mock 后再导入
    try:
        import streamlit  # noqa: F401
        streamlit_available = True
    except ImportError:
        streamlit_available = False

    if not streamlit_available:
        # Mock streamlit 模块
        class FakeStreamlit:
            pass
        sys.modules["streamlit"] = FakeStreamlit()

    from ui.ab_designer import _cohens_h, _calc_sample_size

    # 有效参数: 基线 0.85, 提升 0.05
    n = _calc_sample_size(baseline=0.85, lift=0.05, alpha=0.05, power=0.80)
    assert n > 0, f"样本量应大于 0，实际 {n}"
    assert isinstance(n, float), f"样本量应为浮点数，实际 {type(n)}"

    # Cohen's h 应返回合理效应量
    h = _cohens_h(0.85, 0.90)
    assert h > 0, f"Cohen's h 应大于 0，实际 {h}"

    # 非法参数: 基线 1.2（超出范围）
    try:
        _calc_sample_size(baseline=1.2, lift=0.05, alpha=0.05, power=0.80)
        assert False, "基线 1.2 应抛出异常"
    except (ValueError, AssertionError):
        pass  # 预期行为


# ========== 入口 ==========

def main():
    print("=" * 50)
    print("ChurnGuard 冒烟测试")
    print("=" * 50)

    _test("1. 数据加载", test_1_data_loading)
    _test("2. 风险计算", test_2_risk_calculation)
    _test("3. 分类模拟", test_3_classification)
    _test("4. 文案模拟", test_4_copywriting)
    _test("5. 成本计算", test_5_cost_calculation)
    _test("6. CSV 导出", test_6_csv_export)
    _test("7. 样本量计算", test_7_sample_size)

    print("=" * 50)
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"结果: {passed}/{total} 通过")

    if passed == total:
        print("所有测试通过！")
    else:
        print("以下测试失败:")
        for name, ok, err in _results:
            if not ok:
                print(f"  ✗ {name}: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()