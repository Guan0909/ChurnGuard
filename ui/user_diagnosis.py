"""用户诊断页面 —— 单用户画像、风险评估、Prompt 版本选择、文案生成并排对比、模拟发送"""

from typing import Optional

import streamlit as st

from engine.rule_engine import evaluate_user
from llm.llm_client import classify_churn_reason, generate_copywriting
from llm.prompts import get_prompt
from utils.data_loader import load_current_users


# ========== 数据辅助 ==========

def _get_user_by_id(uid: str, users: list) -> Optional[dict]:
    """按 user_id 在列表中查找用户"""
    for u in users:
        if u["user_id"] == uid:
            return u
    return None


@st.cache_data
def _run_evaluation(uid: str) -> dict:
    """缓存规则引擎评估结果"""
    user = _get_user_by_id(uid, load_current_users())
    if user is None:
        return {}
    return evaluate_user(user)


@st.cache_data
def _run_classification(uid: str) -> dict:
    """缓存 LLM 分类结果（仅取 explanation）"""
    user = _get_user_by_id(uid, load_current_users())
    if user is None:
        return {}
    return classify_churn_reason(user)


@st.cache_data
def _run_copywriting(uid: str, primary_tag: str, version: str) -> dict:
    """缓存单版本文案生成"""
    user = _get_user_by_id(uid, load_current_users())
    if user is None:
        return {}
    return generate_copywriting(user, primary_tag, version)


# ========== 页面渲染 ==========

def render() -> None:
    st.header("用户诊断")

    # 初始化 session_state
    if "intervened_users" not in st.session_state:
        st.session_state.intervened_users = set()
    if "show_compare" not in st.session_state:
        st.session_state.show_compare = False

    users = load_current_users()
    user_options = [f"{u['user_id']} - {u['name']}" for u in users]
    user_map = {f"{u['user_id']} - {u['name']}": u for u in users}

    # ---- 用户选择器 ----
    selected_label = st.selectbox(
        "选择用户",
        user_options,
        index=0,
        key="user_selector",
    )
    user = user_map[selected_label]
    if not user:
        st.warning("用户数据加载失败")
        return

    # ---- 评估（规则引擎 + LLM 解释）----
    uid = user["user_id"]
    eval_result = _run_evaluation(uid)
    class_result = _run_classification(uid)

    risk_score = eval_result["risk_score"]
    weights = eval_result["tag_weights"]
    primary_tag = eval_result["primary_tag"]
    secondary_tag = eval_result["secondary_tag"]
    priority_score = eval_result["priority_score"]
    is_applicable = eval_result["is_applicable"]
    explanation = class_result.get("explanation", "")

    # ---- 上半区：画像 + 风险评估 ----
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.subheader("用户画像")

        # 基本信息行
        info_cols = st.columns(4)
        with info_cols[0]:
            st.metric("价值层级", user.get("value_tier", "-").upper())
        with info_cols[1]:
            st.metric("活跃天数", f"{user.get('last_active_days', '-')}天")
        with info_cols[2]:
            paid = "是" if user.get("has_paid") else "否"
            st.metric("付费用户", paid)
        with info_cols[3]:
            churned = "是" if user.get("churned") else "否"
            st.metric("已流失", churned)

        # 关键指标
        st.markdown("**关键行为指标**")
        metric_cols = st.columns(4)
        with metric_cols[0]:
            st.metric("近7天播放", f"{user.get('play_days_last_7', 0)}天")
        with metric_cols[1]:
            st.metric("播放时长", f"{user.get('total_play_hours_last_7', 0):.1f}h")
        with metric_cols[2]:
            st.metric("社交互动", f"{user.get('social_interaction', 0)}次")
        with metric_cols[3]:
            st.metric("新增歌单", f"{user.get('new_playlists_added', 0)}个")

        # 偏好信息
        st.caption(
            f"偏好流派: {user.get('favorite_genre', '-')}  |  "
            f"近期流派: {user.get('recent_genre', '-')}  |  "
            f"周期模式: {user.get('periodic_pattern', '-')}"
        )

        # 投诉记录（红色高亮）
        complaint = user.get("complaint_record", "")
        if complaint:
            st.error(f"投诉记录: {complaint}")

    with col_right:
        st.subheader("风险评估")

        # 风险分大数字
        risk_color = "inverse" if risk_score >= 70 else ("off" if risk_score >= 40 else "normal")
        st.metric("风险评分", f"{risk_score}/100", delta=None, delta_color=risk_color)

        # 标签权重柱状图
        st.markdown("**标签权重**")
        for tag, weight in weights.items():
            if weight > 0:
                label_map = {
                    "low_activity": "活跃度下降",
                    "interest_shift": "兴趣突变",
                    "content_fatigue": "内容疲劳",
                    "social_isolation": "社交孤独",
                    "function_issue": "功能体验",
                }
                label = label_map.get(tag, tag)
                st.progress(weight, text=f"{label}: {weight:.0%}")

        # 主次标签
        tag_map_cn = {
            "low_activity": "活跃度下降",
            "interest_shift": "兴趣突变",
            "content_fatigue": "内容疲劳",
            "social_isolation": "社交孤独",
            "function_issue": "功能体验",
        }
        st.caption(f"主标签: **{tag_map_cn.get(primary_tag, primary_tag)}**")
        st.caption(f"次标签: **{tag_map_cn.get(secondary_tag, secondary_tag)}**")
        st.caption(f"优先级分数: **{priority_score:.1f}**")

        # 干预适配性
        if is_applicable:
            st.success("该用户可进入常规干预池")
        else:
            st.error("该用户不可进入常规干预池 —— 需流转客服/产品团队处理投诉问题")

        # 解释文本
        if explanation:
            st.info(explanation)

    st.divider()

    # ---- 下半区：Prompt 与文案 ----
    st.subheader("Prompt 版本与文案生成")

    # 版本选择器（不可干预时禁用）
    version = st.radio(
        "选择 Prompt 版本",
        ["basic", "optimized", "warm"],
        format_func=lambda v: {"basic": "基础版", "optimized": "优化版", "warm": "温情版"}[v],
        horizontal=True,
        disabled=not is_applicable,
        key="version_radio",
    )

    if not is_applicable:
        st.warning("该用户存在投诉记录，不进入常规干预池，文案生成功能已禁用。")

    # Prompt 模板展示
    with st.expander("查看 Prompt 模板", expanded=False):
        prompt_data = get_prompt(version, primary_tag)
        st.caption(f"**System Prompt ({version})**")
        st.code(prompt_data["system"], language="text")
        st.caption("**User Prompt Template**")
        st.code(prompt_data["template"], language="text")

    # 文案生成（仅在可干预时）
    if is_applicable:
        copy_result = _run_copywriting(uid, primary_tag, version)

        st.markdown("### 当前版本文案")
        copy_cols = st.columns([2, 1, 1])
        with copy_cols[0]:
            st.markdown(f"**{copy_result.get('title', '')}**")
            st.markdown(copy_result.get("body", ""))
        with copy_cols[1]:
            st.markdown(f"CTA: `{copy_result.get('cta', '')}`")
        with copy_cols[2]:
            songs = copy_result.get("songs", [])
            if songs:
                st.caption("推荐歌曲:")
                for s in songs:
                    st.caption(f"- {s}")

        # 模拟发送
        if uid in st.session_state.intervened_users:
            st.info(f"用户 {user['name']} 已在 7 天冷却期内，暂不可重复干预。")
        else:
            if st.button("模拟发送", type="primary", disabled=not is_applicable):
                st.session_state.intervened_users.add(uid)
                st.toast(f"已向 {user['name']} 发送 {version} 版干预文案！", icon="✅")
                st.success(f"模拟发送成功！用户 {user['name']} 已进入 7 天冷却期。")

        # 一键对比三版
        st.divider()
        if st.button("一键对比三版"):
            st.session_state.show_compare = True

        if st.session_state.show_compare:
            st.markdown("### 三版文案并排对比")
            compare_cols = st.columns(3)
            versions = [
                ("basic", "基础版"),
                ("optimized", "优化版"),
                ("warm", "温情版"),
            ]

            for i, (ver, label) in enumerate(versions):
                with compare_cols[i]:
                    st.markdown(f"**{label}**")
                    ver_result = _run_copywriting(uid, primary_tag, ver)
                    st.markdown(f"*{ver_result.get('title', '')}*")
                    st.caption(ver_result.get("body", ""))
                    st.caption(f"CTA: {ver_result.get('cta', '')}")
                    songs = ver_result.get("songs", [])
                    if songs:
                        for s in songs:
                            st.caption(f"♪ {s}")