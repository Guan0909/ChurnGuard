"""A/B 实验设计器 —— 样本量计算、输入校验、四臂方案表、结果解读"""

import math

import streamlit as st
from statsmodels.stats.power import NormalIndPower

from config import settings


# ========== 效应量计算 ==========

def _cohens_h(p1: float, p2: float) -> float:
    """Cohen's h 效应量：比例检验的标准效应量转换

    h = 2 * (arcsin(sqrt(p2)) - arcsin(sqrt(p1)))
    """
    return 2.0 * (math.asin(math.sqrt(p2)) - math.asin(math.sqrt(p1)))


# ========== 样本量计算 ==========

def _calc_sample_size(
    baseline: float,
    lift: float,
    alpha: float,
    power: float,
) -> float:
    """使用 statsmodels 计算两独立样本比例检验所需每组样本量

    Args:
        baseline: 基线留存率
        lift: 最小可检测提升
        alpha: 显著性水平
        power: 统计功效

    Returns:
        每组所需样本量（浮点数）
    """
    p2 = baseline + lift
    effect_size = _cohens_h(baseline, p2)
    n = NormalIndPower().solve_power(
        effect_size=effect_size,
        alpha=alpha,
        power=power,
        ratio=1.0,
        alternative="larger",
    )
    return n


# ========== 输入校验 ==========

def _validate_inputs(
    baseline: float,
    lift: float,
    alpha: float,
    power: float,
    daily_inflow: int,
) -> list[str]:
    """校验输入参数，返回错误信息列表"""
    errors = []

    if baseline <= 0 or baseline >= 1.0:
        errors.append("基线留存率必须在 (0, 1) 区间内")

    if lift <= 0:
        errors.append("最小可检测提升必须大于 0")

    if baseline + lift >= 1.0:
        errors.append(f"基线留存率({baseline:.2f}) + 最小可检测提升({lift:.2f}) = {baseline + lift:.2f}，超出有效范围")

    if lift < 0.01:
        errors.append("最小可检测提升幅度过小（< 1%），样本量需求可能极大，建议提高 MDE")

    if alpha <= 0 or alpha >= 1.0:
        errors.append("显著性水平 α 必须在 (0, 1) 区间内")

    if power <= 0 or power >= 1.0:
        errors.append("统计功效必须在 (0, 1) 区间内")

    if daily_inflow <= 0:
        errors.append("日高风险流入量必须大于 0")

    return errors


# ========== 页面渲染 ==========

def render() -> None:
    st.header("A/B 实验设计器")

    st.markdown(
        "基于两独立样本比例检验（Two-Sample Z-Test for Proportions），"
        "使用 Cohen's h 效应量 + statsmodels 计算样本量。"
    )

    # ---- 输入区 ----
    st.subheader("实验参数")

    input_cols = st.columns(4)
    with input_cols[0]:
        baseline = st.number_input(
            "基线留存率",
            min_value=0.0,
            max_value=1.0,
            value=settings.RETENTION_BASELINE["no_intervention"],
            step=0.01,
            format="%.2f",
            help="对照组（不干预）的预期留存率",
        )
    with input_cols[1]:
        lift = st.number_input(
            "最小可检测提升 (MDE)",
            min_value=0.0,
            max_value=1.0,
            value=0.05,
            step=0.01,
            format="%.2f",
            help="期望检测到的最小留存率提升幅度",
        )
    with input_cols[2]:
        alpha = st.number_input(
            "显著性水平 α",
            min_value=0.01,
            max_value=0.10,
            value=0.05,
            step=0.01,
            format="%.2f",
            help="第一类错误概率，通常设为 0.05",
        )
    with input_cols[3]:
        power = st.number_input(
            "统计功效 (1-β)",
            min_value=0.50,
            max_value=0.99,
            value=0.80,
            step=0.05,
            format="%.2f",
            help="第二类错误概率的补数，通常设为 0.80",
        )

    daily_inflow = st.number_input(
        "日高风险流入量",
        min_value=1,
        max_value=100000,
        value=100,
        step=10,
        help="每日新增高风险用户数量",
    )

    # ---- 输入校验 ----
    errors = _validate_inputs(baseline, lift, alpha, power, daily_inflow)
    if errors:
        for err in errors:
            st.error(err)
        return

    # ---- 计算 ----
    per_group = _calc_sample_size(baseline, lift, alpha, power)
    per_group_ceil = math.ceil(per_group)
    # 四臂：A(对照) + B(通用发券) + C(规则干预) + D(AI个性化)
    total_sample = per_group_ceil * 4
    # 实验周期：四组均分流量
    experiment_days = math.ceil(total_sample / daily_inflow)

    # ---- 结果卡片 ----
    st.subheader("计算结果")

    result_cols = st.columns(4)
    with result_cols[0]:
        st.metric("每组样本量", f"{per_group_ceil} 人", help=f"精确值: {per_group:.2f}")
    with result_cols[1]:
        st.metric("总样本量", f"{total_sample} 人", help="四臂 × 每组样本量")
    with result_cols[2]:
        st.metric("实验周期", f"{experiment_days} 天", help=f"总样本量 / 日流入量 = {total_sample}/{daily_inflow}")
    with result_cols[3]:
        cohens_h = _cohens_h(baseline, baseline + lift)
        st.metric("Cohen's h", f"{cohens_h:.4f}", help="效应量")

    # ---- 计算依据 ----
    with st.expander("计算依据", expanded=False):
        st.markdown(f"""
        - **统计方法**: 两独立样本比例检验（Two-Sample Z-Test for Proportions）
        - **效应量**: Cohen's h = 2 × (arcsin(√p₂) - arcsin(√p₁)) = {cohens_h:.4f}
        - **p₁ (基线留存率)**: {baseline:.2%}
        - **p₂ (实验留存率)**: {baseline + lift:.2%}
        - **显著性水平 α**: {alpha}
        - **统计功效 1-β**: {power}
        - **样本量计算**: statsmodels.stats.power.NormalIndPower.solve_power
        - **每组样本量**: {per_group:.2f} → 向上取整 {per_group_ceil}
        - **总样本量**: {per_group_ceil} × 4 臂 = {total_sample}
        - **实验周期**: {total_sample} / {daily_inflow} = {experiment_days} 天（向上取整）
        """)

    # ---- 四臂实验方案表 ----
    st.subheader("四臂实验方案")

    arms = [
        {
            "组别": "A（对照组）",
            "策略": "不干预",
            "样本量": per_group_ceil,
            "预期留存率": f"{baseline:.1%}",
            "核心观测指标": "留存率",
            "统计方法": "双样本 Z 检验",
            "说明": "基准对照，不发送任何干预",
        },
        {
            "组别": "B（实验组）",
            "策略": "通用发券",
            "样本量": per_group_ceil,
            "预期留存率": f"{baseline + lift:.1%}",
            "核心观测指标": "留存率、优惠券核销率",
            "统计方法": "双样本 Z 检验 vs A",
            "说明": "统一发放通用优惠券",
        },
        {
            "组别": "C（实验组）",
            "策略": "规则引擎干预",
            "样本量": per_group_ceil,
            "预期留存率": f"{baseline + lift:.1%}",
            "核心观测指标": "留存率、标签命中准确率",
            "统计方法": "双样本 Z 检验 vs A",
            "说明": "基于规则引擎的标签匹配策略",
        },
        {
            "组别": "D（实验组）",
            "策略": "AI 个性化干预",
            "样本量": per_group_ceil,
            "预期留存率": f"{baseline + lift:.1%}",
            "核心观测指标": "留存率、文案 CTR、用户满意度",
            "统计方法": "双样本 Z 检验 vs A",
            "说明": "AI 驱动的个性化文案推送",
        },
    ]

    st.table(arms)

    # ---- 结果解读 ----
    st.subheader("结果解读")

    st.markdown(f"""
    **实验设计要点：**

    1. **样本量充足性**: 每组需要 {per_group_ceil} 人，总样本量 {total_sample} 人，满足统计功效 {power:.0%} 的要求。
    2. **实验周期**: 在日流入 {daily_inflow} 人的条件下，预计需要 {experiment_days} 天完成实验。
       {"⚠️ 实验周期较长，建议考虑提高 MDE 或增加样本来源渠道。" if experiment_days > 60 else ""}
    3. **统计推断**: 使用双样本 Z 检验（单侧），显著性水平 α={alpha}。若实验组留存率显著高于对照组，且达到 {lift:.1%} 的最小可检测提升，则拒绝零假设。
    4. **多重比较**: 三组实验组同时与对照组比较，建议使用 Bonferroni 校正（α' = α/3 = {alpha/3:.4f}）控制族错误率。
    5. **效应量解读**: Cohen's h = {cohens_h:.4f}，属于{"小" if abs(cohens_h) < 0.2 else ("中" if abs(cohens_h) < 0.5 else "大")}效应量。
    """)