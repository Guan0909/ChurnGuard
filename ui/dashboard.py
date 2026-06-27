"""决策看板 —— 风险分布直方图、标签占比饼图、阈值-成本-召回率曲线、特征重要性排序、Bad Case 展示"""

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from config import settings
from engine.cost_calculator import calc_roi, calc_net_revenue, calc_expected_ltv
from engine.rule_engine import evaluate_user, is_intervention_applicable
from utils.data_loader import load_current_users


# ========== 全局中文字体配置 ==========

FONT_FAMILY = "Microsoft YaHei, SimHei, sans-serif"


def _apply_font(fig: go.Figure) -> None:
    """统一应用中文字体配置"""
    fig.update_layout(font_family=FONT_FAMILY)


# ========== 数据加载（缓存）==========

@st.cache_data
def _load_bad_cases() -> str:
    """加载 Bad Case 分析文档"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "docs", "bad_case_analysis.md")
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    except FileNotFoundError:
        return ""


@st.cache_data
def _evaluate_all() -> pd.DataFrame:
    """批量评估所有用户，返回 DataFrame"""
    users = load_current_users()
    records = []
    for u in users:
        ev = evaluate_user(u)
        records.append({**u, **ev})
    return pd.DataFrame(records)


# ========== 特征重要性计算 ==========

@st.cache_data
def _calc_feature_importance(df: pd.DataFrame) -> pd.DataFrame:
    """计算全量用户各维度累计贡献总分占比

    返回 DataFrame: feature, total_contribution, proportion, rule_bonus
    """
    contributions = {
        "基础活跃度": 0,
        "兴趣突变": 0,
        "内容疲劳": 0,
        "社交孤独": 0,
        "功能体验": 0,
    }

    for _, row in df.iterrows():
        last_active = row.get("last_active_days", 0)
        complaint = row.get("complaint_record", "")

        if complaint != "":
            contributions["功能体验"] += 80
        else:
            # 基础分
            if last_active > 14:
                contributions["基础活跃度"] += 60
            elif last_active > 7:
                contributions["基础活跃度"] += 30

            # 兴趣突变
            if row.get("favorite_genre") != row.get("recent_genre"):
                contributions["兴趣突变"] += 30

            # 内容疲劳
            if row.get("play_days_last_7", 0) >= 5 and row.get("new_playlists_added", 0) <= 2:
                contributions["内容疲劳"] += 25

            # 社交孤独
            if row.get("social_interaction", 0) <= 3 and row.get("social_following", 0) <= 10:
                contributions["社交孤独"] += 15

    total = sum(contributions.values())
    rows = []
    for feature, contrib in contributions.items():
        rows.append({
            "feature": feature,
            "total_contribution": contrib,
            "proportion": contrib / total if total > 0 else 0,
            "rule_bonus": _get_rule_bonus(feature),
        })

    df_importance = pd.DataFrame(rows)
    df_importance = df_importance.sort_values("total_contribution", ascending=True)
    return df_importance


def _get_rule_bonus(feature: str) -> int:
    """获取规则加分模拟值"""
    mapping = {
        "基础活跃度": 60,
        "兴趣突变": 30,
        "内容疲劳": 25,
        "社交孤独": 15,
        "功能体验": 80,
    }
    return mapping.get(feature, 0)


# ========== 阈值扫描（复用 cost_calculator 口径）==========

def _scan_thresholds(df: pd.DataFrame) -> pd.DataFrame:
    """扫描风险阈值 20-100，计算召回率与总成本"""
    applicable = df[df["is_applicable"]].copy()
    total_applicable = len(applicable)

    rows = []
    for threshold in range(20, 101, 5):
        above = applicable[applicable["risk_score"] >= threshold].copy()
        covered = len(above)

        if covered == 0:
            rows.append({
                "threshold": threshold,
                "covered_users": 0,
                "total_cost": 0.0,
                "recall_rate": 0.0,
            })
            continue

        # 按优先级排序 + 预算截断
        above = above.sort_values("priority_score", ascending=False)
        total_cost = 0.0
        selected = 0
        for _, u in above.iterrows():
            cost = _strategy_cost(u["primary_tag"])
            if total_cost + cost > settings.BUDGET_LIMIT:
                break
            total_cost += cost
            selected += 1

        recall_rate = selected / total_applicable if total_applicable > 0 else 0

        rows.append({
            "threshold": threshold,
            "covered_users": selected,
            "total_cost": round(total_cost, 2),
            "recall_rate": round(recall_rate, 4),
        })

    return pd.DataFrame(rows)


def _strategy_cost(primary_tag: str) -> float:
    """主标签 → 策略成本"""
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
    st.header("决策看板")

    df = _evaluate_all()

    # ---- 顶部 KPI 卡片 ----
    st.subheader("全局概览")
    total_users = len(df)
    avg_risk = df["risk_score"].mean()
    high_risk_pct = (df["risk_score"] >= settings.RISK_THRESHOLD).mean()
    applicable_pct = df["is_applicable"].mean()

    kpi_cols = st.columns(4)
    with kpi_cols[0]:
        st.metric("总用户数", total_users)
    with kpi_cols[1]:
        st.metric("平均风险分", f"{avg_risk:.1f}")
    with kpi_cols[2]:
        st.metric("高风险占比", f"{high_risk_pct:.1%}")
    with kpi_cols[3]:
        st.metric("可干预占比", f"{applicable_pct:.1%}")

    # ---- 图表区 2×2 ----
    st.subheader("数据分析")

    row1_cols = st.columns(2)

    # 图表 1：风险分布直方图
    with row1_cols[0]:
        _render_risk_histogram(df)

    # 图表 2：标签占比饼图
    with row1_cols[1]:
        _render_tag_pie(df)

    row2_cols = st.columns(2)

    # 图表 3：阈值-成本-召回率曲线
    with row2_cols[0]:
        _render_threshold_curve(df)

    # 图表 4：特征重要性排序
    with row2_cols[1]:
        _render_feature_importance(df)

    # ---- Bad Case 展示 ----
    st.divider()
    st.subheader("Bad Case 分析")

    bad_cases = _load_bad_cases()
    if bad_cases:
        with st.expander("查看典型案例", expanded=False):
            st.markdown(bad_cases)
    else:
        st.info("Bad Case 分析文档不存在，请检查 docs/bad_case_analysis.md")


def _render_risk_histogram(df: pd.DataFrame) -> None:
    """风险分布直方图"""
    bins = [0, 20, 40, 60, 80, 100]
    labels = ["0-20", "21-40", "41-60", "61-80", "81-100"]
    df_bin = df.copy()
    df_bin["风险区间"] = pd.cut(df_bin["risk_score"], bins=bins, labels=labels, right=True)

    bin_counts = df_bin["风险区间"].value_counts().sort_index().reset_index()
    bin_counts.columns = ["风险区间", "用户数"]

    fig = px.bar(
        bin_counts,
        x="风险区间",
        y="用户数",
        text="用户数",
        color="风险区间",
        color_discrete_sequence=px.colors.sequential.Blues_r,
        title="风险评分分布",
    )
    fig.update_traces(textposition="outside")
    _apply_font(fig)
    st.plotly_chart(fig, use_container_width=True)


def _render_tag_pie(df: pd.DataFrame) -> None:
    """标签占比饼图"""
    tag_map = {
        "low_activity": "活跃度下降",
        "interest_shift": "兴趣突变",
        "content_fatigue": "内容疲劳",
        "social_isolation": "社交孤独",
        "function_issue": "功能体验",
    }
    tag_counts = df["primary_tag"].map(tag_map).value_counts().reset_index()
    tag_counts.columns = ["主标签", "用户数"]

    fig = px.pie(
        tag_counts,
        names="主标签",
        values="用户数",
        title="主标签分布",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    _apply_font(fig)
    st.plotly_chart(fig, use_container_width=True)


def _render_threshold_curve(df: pd.DataFrame) -> None:
    """阈值-成本-召回率双 Y 轴曲线"""
    scan_df = _scan_thresholds(df)

    if scan_df.empty:
        st.info("暂无数据")
        return

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 召回率（左 Y）
    fig.add_trace(
        go.Scatter(
            x=scan_df["threshold"],
            y=scan_df["recall_rate"],
            mode="lines+markers",
            name="召回率",
            line=dict(color="#636EFA", width=2),
            marker=dict(size=4),
            hovertemplate="阈值: %{x}<br>召回率: %{y:.1%}<extra></extra>",
        ),
        secondary_y=False,
    )

    # 总成本（右 Y）
    fig.add_trace(
        go.Scatter(
            x=scan_df["threshold"],
            y=scan_df["total_cost"],
            mode="lines",
            name="总成本",
            line=dict(color="#EF553B", width=2, dash="dash"),
            hovertemplate="阈值: %{x}<br>总成本: ¥%{y:.2f}<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title="风险阈值 vs 召回率 & 总成本",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(title_text="风险阈值", dtick=10)
    fig.update_yaxes(title_text="召回率", tickformat=".0%", secondary_y=False)
    fig.update_yaxes(title_text="总成本 (¥)", secondary_y=True)
    _apply_font(fig)
    st.plotly_chart(fig, use_container_width=True)


def _render_feature_importance(df: pd.DataFrame) -> None:
    """特征重要性排序（全量用户累计贡献占比）"""
    importance_df = _calc_feature_importance(df)

    fig = px.bar(
        importance_df,
        x="total_contribution",
        y="feature",
        text=importance_df["rule_bonus"].apply(lambda x: f"模拟值: {x}"),
        orientation="h",
        color="feature",
        color_discrete_sequence=px.colors.qualitative.Pastel,
        title="特征重要性排序（规则加分模拟值）",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        xaxis_title="累计贡献总分",
        yaxis_title="",
        showlegend=False,
        margin=dict(l=100),
    )
    _apply_font(fig)
    st.plotly_chart(fig, use_container_width=True)