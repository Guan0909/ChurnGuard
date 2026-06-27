"""批量干预页面 —— 用户筛选、预算约束下生成干预计划、CSV 导出、模拟 7 日效果四组对比"""

import pandas as pd
import plotly.express as px
import streamlit as st

from config import settings
from engine.cost_calculator import (
    calc_single_cost,
    calc_total_cost,
    simulate_intervention_effect,
)
from engine.rule_engine import filter_intervention_candidates
from utils.data_loader import load_current_users


# ========== 页面渲染 ==========

def render() -> None:
    st.header("批量干预")

    # 初始化 session_state
    if "batch_plan" not in st.session_state:
        st.session_state.batch_plan = None
    if "batch_total_cost" not in st.session_state:
        st.session_state.batch_total_cost = 0.0
    if "show_simulation" not in st.session_state:
        st.session_state.show_simulation = False

    users = load_current_users()

    # ---- 筛选区 ----
    st.subheader("筛选条件")

    filter_cols = st.columns(3)
    with filter_cols[0]:
        risk_threshold = st.slider(
            "风险阈值",
            min_value=0,
            max_value=100,
            value=settings.RISK_THRESHOLD,
            step=5,
            help="仅筛选风险分 >= 此阈值的用户",
            key="batch_risk",
        )
    with filter_cols[1]:
        value_tiers = st.multiselect(
            "价值层级",
            options=["high", "mid", "low"],
            default=["high", "mid", "low"],
            help="选择要纳入筛选的价值层级",
        )
    with filter_cols[2]:
        budget = st.slider(
            "预算上限",
            min_value=0,
            max_value=1000,
            value=settings.BUDGET_LIMIT,
            step=50,
            help="干预总预算上限",
            key="batch_budget",
        )

    # ---- 生成计划 ----
    st.divider()
    gen_col, export_col, sim_col = st.columns([2, 1, 1])

    with gen_col:
        if st.button("生成干预计划", type="primary", use_container_width=True):
            with st.spinner("正在评估用户并生成干预计划..."):
                # 按价值层级过滤用户
                filtered_users = [u for u in users if u.get("value_tier", "low") in value_tiers]

                if not filtered_users:
                    st.warning("当前筛选条件下无用户，请调整价值层级选择。")
                    st.session_state.batch_plan = None
                    st.session_state.batch_total_cost = 0.0
                else:
                    # 统一调用规则引擎筛选
                    candidates, total_cost = filter_intervention_candidates(
                        filtered_users,
                        budget=budget,
                        risk_threshold=risk_threshold,
                    )

                    if not candidates:
                        st.warning("无符合条件的干预用户，请调整筛选条件（降低风险阈值或增加预算）。")
                        st.session_state.batch_plan = None
                        st.session_state.batch_total_cost = 0.0
                    else:
                        st.session_state.batch_plan = candidates
                        st.session_state.batch_total_cost = total_cost
                        st.success(f"已生成 {len(candidates)} 位用户的干预计划")

    plan = st.session_state.batch_plan
    total_cost = st.session_state.batch_total_cost

    # ---- 预算利用率进度条 ----
    if plan:
        utilization = total_cost / budget if budget > 0 else 0
        st.progress(
            min(utilization, 1.0),
            text=f"预算利用率: {total_cost:.1f} / {budget} ({utilization:.0%})",
        )

    # ---- 干预计划表 ----
    if plan:
        st.subheader(f"干预计划 ({len(plan)} 人)")

        # 构建 DataFrame
        tag_map = {
            "low_activity": "活跃度下降",
            "interest_shift": "兴趣突变",
            "content_fatigue": "内容疲劳",
            "social_isolation": "社交孤独",
        }
        df = pd.DataFrame(plan)
        df_display = df.rename(columns={
            "user_id": "用户ID",
            "name": "姓名",
            "risk_score": "风险分",
            "primary_tag": "主标签",
            "strategy_type": "策略类型",
            "cost": "干预成本",
            "expected_ltv": "预期LTV",
            "priority_score": "优先级",
            "value_tier": "价值层级",
        })
        df_display["主标签"] = df_display["主标签"].map(tag_map)
        df_display["策略类型"] = df_display["策略类型"].map(tag_map)
        df_display["价值层级"] = df_display["价值层级"].str.upper()

        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "干预成本": st.column_config.NumberColumn(format="¥%.2f"),
                "预期LTV": st.column_config.NumberColumn(format="¥%.2f"),
                "优先级": st.column_config.NumberColumn(format="%.1f"),
            },
        )

        # 汇总统计
        total_ltv = sum(c.get("expected_ltv", 0) for c in plan)
        avg_risk = sum(c["risk_score"] for c in plan) / len(plan)
        summary_cols = st.columns(4)
        with summary_cols[0]:
            st.metric("入选人数", len(plan))
        with summary_cols[1]:
            st.metric("总成本", f"¥{total_cost:.2f}")
        with summary_cols[2]:
            st.metric("总预期LTV", f"¥{total_ltv:.2f}")
        with summary_cols[3]:
            st.metric("平均风险分", f"{avg_risk:.1f}")

    # ---- CSV 导出 ----
    with export_col:
        if plan:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="导出 CSV",
                data=csv,
                file_name="intervention_plan.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.button(
                "导出 CSV",
                disabled=True,
                use_container_width=True,
                help="请先生成干预计划",
            )

    # ---- 模拟 7 日效果 ----
    with sim_col:
        simulate_disabled = plan is None or len(plan) == 0
        if st.button(
            "模拟 7 日效果",
            disabled=simulate_disabled,
            use_container_width=True,
            type="secondary",
        ):
            st.session_state.show_simulation = True

    if plan and st.session_state.get("show_simulation", False):
        st.divider()
        st.subheader("模拟 7 日效果对比")

        sim_result = simulate_intervention_effect(plan, target_users=len(plan))

        # 四组指标卡片
        sim_cols = st.columns(4)
        labels = {
            "no_intervention": "不干预",
            "generic_coupon": "通用发券",
            "rule_based": "规则干预",
            "ai_personalized": "AI 个性化",
        }

        for i, (key, label) in enumerate(labels.items()):
            r = sim_result[key]
            with sim_cols[i]:
                st.markdown(f"**{label}**")
                st.metric("留存人数", r["retained_users"])
                st.metric("挽回数", r["saved_users"])
                st.metric("总成本", f"¥{r['total_cost']:.2f}")
                st.metric("总挽回LTV", f"¥{r['total_ltv']:.2f}")
                st.metric("净收益", f"¥{r['net_revenue']:.2f}")
                # ROI 颜色
                roi_val = r["roi"]
                roi_display = f"{roi_val:.2%}"
                if roi_val > 0:
                    st.success(f"ROI: {roi_display}")
                elif roi_val == 0:
                    st.info(f"ROI: {roi_display}")
                else:
                    st.error(f"ROI: {roi_display}")

        # Plotly ROI 对比柱状图
        st.markdown("**ROI 对比**")
        roi_data = pd.DataFrame([
            {"策略": labels[k], "ROI": v["roi"]} for k, v in sim_result.items()
        ])
        fig = px.bar(
            roi_data,
            x="策略",
            y="ROI",
            text=roi_data["ROI"].apply(lambda x: f"{x:.2%}"),
            color="策略",
            color_discrete_sequence=["#636EFA", "#EF553B", "#00CC96", "#AB63FA"],
            title="四种干预策略 ROI 对比",
        )
        fig.update_traces(textposition="outside")
        # 中文字体
        fig.update_layout(
            font_family="Microsoft YaHei, SimHei, sans-serif",
            yaxis_tickformat=".0%",
            showlegend=False,
            yaxis_title="ROI",
            xaxis_title="",
        )
        st.plotly_chart(fig, use_container_width=True)

        # 净收益对比
        st.markdown("**净收益对比**")
        revenue_data = pd.DataFrame([
            {"策略": labels[k], "净收益": v["net_revenue"]} for k, v in sim_result.items()
        ])
        fig2 = px.bar(
            revenue_data,
            x="策略",
            y="净收益",
            text=revenue_data["净收益"].apply(lambda x: f"¥{x:.2f}"),
            color="策略",
            color_discrete_sequence=["#636EFA", "#EF553B", "#00CC96", "#AB63FA"],
            title="四种干预策略净收益对比",
        )
        fig2.update_traces(textposition="outside")
        fig2.update_layout(
            font_family="Microsoft YaHei, SimHei, sans-serif",
            showlegend=False,
            yaxis_title="净收益 (¥)",
            xaxis_title="",
        )
        st.plotly_chart(fig2, use_container_width=True)