"""阈值模拟器 —— 滑块调节风险阈值/预算/价值层级，实时指标 + 最优 ROI 推荐 + 双 Y 轴曲线"""

import json

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from config import settings
from engine.cost_calculator import (
    calc_expected_ltv,
    calc_roi,
    calc_net_revenue,
    calc_total_cost,
)
from engine.rule_engine import evaluate_user, is_intervention_applicable
from utils.data_loader import load_current_users


@st.cache_data
def _evaluate_all_users(users_json: str) -> list[dict]:
    """批量评估所有用户（缓存），返回带评估结果的用户列表"""
    users = json.loads(users_json)
    results = []
    for u in users:
        ev = evaluate_user(u)
        results.append({**u, **ev})
    return results


# ========== 阈值扫描 ==========

def _scan_thresholds(
    evaluated_users: list[dict],
    budget: float,
    value_tiers: list[str],
) -> pd.DataFrame:
    """遍历风险阈值 20-100（步长 1），计算每个阈值下的指标

    Returns:
        DataFrame with columns: threshold, covered_users, total_cost, recall_rate,
        recovery_revenue, roi, net_revenue
    """
    # 按价值层级过滤
    filtered = [u for u in evaluated_users if u.get("value_tier", "low") in value_tiers]
    applicable = [u for u in filtered if is_intervention_applicable(u)]
    total_applicable = len(applicable)

    rows = []
    for threshold in range(20, 101, 1):
        # 按风险阈值筛选
        above = [u for u in applicable if u["risk_score"] >= threshold]
        covered = len(above)

        if covered == 0:
            rows.append({
                "threshold": threshold,
                "covered_users": 0,
                "total_cost": 0.0,
                "recall_rate": 0.0,
                "recovery_revenue": 0.0,
                "roi": 0.0,
                "net_revenue": 0.0,
            })
            continue

        # 按优先级排序 + 预算截断
        above.sort(key=lambda u: u["priority_score"], reverse=True)
        total_cost = 0.0
        selected = []
        for u in above:
            cost = _get_strategy_cost(u["primary_tag"])
            if total_cost + cost > budget:
                break
            total_cost += cost
            selected.append(u)

        actual_covered = len(selected)
        recall_rate = actual_covered / total_applicable if total_applicable > 0 else 0
        recovery_revenue = sum(calc_expected_ltv(u) for u in selected) * settings.RETENTION_BASELINE["ai_personalized"]
        roi = calc_roi(recovery_revenue, total_cost) if total_cost > 0 else 0.0
        net_revenue = calc_net_revenue(recovery_revenue, total_cost)

        rows.append({
            "threshold": threshold,
            "covered_users": actual_covered,
            "total_cost": round(total_cost, 2),
            "recall_rate": round(recall_rate, 4),
            "recovery_revenue": round(recovery_revenue, 2),
            "roi": round(roi, 4),
            "net_revenue": round(net_revenue, 2),
        })

    return pd.DataFrame(rows)


def _get_strategy_cost(primary_tag: str) -> float:
    """主标签 → 策略成本映射"""
    cost_map = {
        "low_activity": settings.COSTS["push"],
        "interest_shift": settings.COSTS["vip"],
        "content_fatigue": settings.COSTS["vip"],
        "social_isolation": settings.COSTS["manual"],
        "function_issue": settings.COSTS["manual"],
    }
    return cost_map.get(primary_tag, settings.COSTS["push"])


# ========== 页面渲染 ==========

def render() -> None:
    st.header("阈值模拟器")

    # ---- 控制区 ----
    st.subheader("参数调节")

    control_cols = st.columns(3)
    with control_cols[0]:
        risk_threshold = st.slider(
            "风险阈值",
            min_value=20,
            max_value=100,
            value=settings.RISK_THRESHOLD,
            step=1,
            help="仅筛选风险分 >= 此阈值的用户",
            key="threshold_sim_risk",
        )
    with control_cols[1]:
        budget = st.slider(
            "预算上限",
            min_value=0,
            max_value=1000,
            value=settings.BUDGET_LIMIT,
            step=50,
            help="干预总预算上限",
            key="threshold_sim_budget",
        )
    with control_cols[2]:
        value_tiers = st.multiselect(
            "价值层级",
            options=["high", "mid", "low"],
            default=["high", "mid", "low"],
            help="选择要纳入模拟的价值层级",
        )

    # ---- 加载并评估所有用户 ----
    users = load_current_users()
    evaluated = _evaluate_all_users(json.dumps(users, ensure_ascii=False))

    # 按价值层级 + 可干预过滤
    ev_filtered = [u for u in evaluated if u.get("value_tier", "low") in value_tiers]
    ev_applicable = [u for u in ev_filtered if is_intervention_applicable(u)]
    total_applicable = len(ev_applicable)

    # 当前阈值下的指标
    above = [u for u in ev_applicable if u["risk_score"] >= risk_threshold]
    above.sort(key=lambda u: u["priority_score"], reverse=True)

    total_cost = 0.0
    selected = []
    for u in above:
        cost = _get_strategy_cost(u["primary_tag"])
        if total_cost + cost > budget:
            break
        total_cost += cost
        selected.append(u)

    covered_users = len(selected)
    recall_rate = covered_users / total_applicable if total_applicable > 0 else 0.0
    recovery_revenue = sum(calc_expected_ltv(u) for u in selected) * settings.RETENTION_BASELINE["ai_personalized"]
    current_roi = calc_roi(recovery_revenue, total_cost) if total_cost > 0 else 0.0
    net_revenue = calc_net_revenue(recovery_revenue, total_cost)

    # ---- 实时指标卡 ----
    st.subheader("实时指标")
    metric_cols = st.columns(5)
    with metric_cols[0]:
        st.metric("覆盖用户数", covered_users)
    with metric_cols[1]:
        st.metric("预计总成本", f"¥{total_cost:.2f}")
    with metric_cols[2]:
        st.metric("预期召回率", f"{recall_rate:.1%}")
    with metric_cols[3]:
        st.metric("预期挽回收益", f"¥{recovery_revenue:.2f}")
    with metric_cols[4]:
        st.metric("预计净收益", f"¥{net_revenue:.2f}")

    # ---- 阈值扫描（自动计算最优）----
    df = _scan_thresholds(evaluated, budget, value_tiers)

    if df.empty or df["covered_users"].sum() == 0:
        st.warning("当前参数下无符合条件的用户，请调整价值层级或预算。")
        return

    # 找最优 ROI 阈值
    best_row = df.loc[df["roi"].idxmax()]
    optimal_threshold = int(best_row["threshold"])
    optimal_roi = best_row["roi"]
    optimal_covered = int(best_row["covered_users"])

    # ---- 最优推荐语句 ----
    all_negative = (df["roi"] <= 0).all()

    if all_negative:
        st.warning(
            "当前参数下所有阈值的 ROI 均为非正，无法推荐最优阈值。"
            "建议增加预算或扩大价值层级范围以覆盖更多高价值用户。"
        )
    else:
        st.info(
            f"推荐风险阈值 **{optimal_threshold}**，"
            f"ROI 达 **{optimal_roi:.2%}**，"
            f"覆盖 **{optimal_covered}** 位用户，"
            f"预计净收益 **¥{best_row['net_revenue']:.2f}**。"
        )

    # ---- 双 Y 轴曲线图 ----
    st.subheader("阈值-ROI-成本曲线")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 左 Y 轴：ROI 曲线
    fig.add_trace(
        go.Scatter(
            x=df["threshold"],
            y=df["roi"],
            mode="lines+markers",
            name="ROI",
            line=dict(color="#636EFA", width=2),
            marker=dict(size=4),
            hovertemplate="阈值: %{x}<br>ROI: %{y:.2%}<extra></extra>",
        ),
        secondary_y=False,
    )

    # 右 Y 轴：总成本曲线
    fig.add_trace(
        go.Scatter(
            x=df["threshold"],
            y=df["total_cost"],
            mode="lines",
            name="总成本",
            line=dict(color="#EF553B", width=2, dash="dash"),
            hovertemplate="阈值: %{x}<br>总成本: ¥%{y:.2f}<extra></extra>",
        ),
        secondary_y=True,
    )

    # 红色星号标记最优点
    if not all_negative:
        fig.add_trace(
            go.Scatter(
                x=[optimal_threshold],
                y=[optimal_roi],
                mode="markers+text",
                name="最优 ROI",
                marker=dict(color="red", size=14, symbol="star"),
                text=[f"最优<br>阈值{optimal_threshold}"],
                textposition="top center",
                textfont=dict(color="red", size=12),
                hovertemplate="最优阈值: %{x}<br>ROI: %{y:.2%}<extra></extra>",
                showlegend=True,
            ),
            secondary_y=False,
        )

    # 布局
    fig.update_layout(
        title="风险阈值 vs ROI & 总成本",
        font_family="Microsoft YaHei, SimHei, sans-serif",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(title_text="风险阈值", dtick=10)
    fig.update_yaxes(title_text="ROI", tickformat=".0%", secondary_y=False)
    fig.update_yaxes(title_text="总成本 (¥)", secondary_y=True)

    st.plotly_chart(fig, use_container_width=True)

    # ---- 覆盖人数曲线 ----
    st.subheader("阈值-覆盖人数曲线")
    fig2 = go.Figure()
    fig2.add_trace(
        go.Scatter(
            x=df["threshold"],
            y=df["covered_users"],
            mode="lines+markers",
            name="覆盖用户数",
            line=dict(color="#00CC96", width=2),
            marker=dict(size=4),
            fill="tozeroy",
            fillcolor="rgba(0,204,150,0.1)",
            hovertemplate="阈值: %{x}<br>覆盖: %{y}人<extra></extra>",
        )
    )
    if not all_negative:
        fig2.add_trace(
            go.Scatter(
                x=[optimal_threshold],
                y=[optimal_covered],
                mode="markers+text",
                name="最优 ROI",
                marker=dict(color="red", size=14, symbol="star"),
                text=[f"最优<br>{optimal_covered}人"],
                textposition="top center",
                textfont=dict(color="red", size=12),
                showlegend=True,
            )
        )
    fig2.update_layout(
        title="风险阈值 vs 覆盖用户数",
        font_family="Microsoft YaHei, SimHei, sans-serif",
        hovermode="x unified",
        xaxis_title="风险阈值",
        yaxis_title="覆盖用户数",
        xaxis=dict(dtick=10),
    )
    st.plotly_chart(fig2, use_container_width=True)