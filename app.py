"""ChurnGuard 应用入口 —— st.tabs 多页布局、全局异常捕获、Plotly 中文字体配置"""

import traceback

import streamlit as st

from config import settings
from utils.data_loader import (
    get_available_datasets,
    get_current_dataset_name,
    get_dataset_stats,
    load_current_users,
    parse_uploaded_file,
    switch_dataset,
    validate_and_add_dataset,
)
from utils.logger import get_logger

logger = get_logger(__name__)


# ========== 全局页面配置 ==========

st.set_page_config(
    page_title=settings.app_title,
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ========== 全局缓存设置 ==========
# Streamlit 默认缓存行为已满足需求，额外配置可在下方扩展

# ========== Plotly 全局中文字体 ==========
CHINESE_FONT = "Microsoft YaHei, SimHei, sans-serif"

# ========== 全局 CSS ==========
st.markdown(
    f"""
    <style>
    .stApp {{
        font-family: {CHINESE_FONT};
    }}
    .main .block-container {{
        padding-top: 2rem;
        padding-bottom: 2rem;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ========== 页面导入 ==========

@st.cache_resource
def _import_pages():
    """延迟导入各 Tab 页面模块"""
    from ui import user_diagnosis
    from ui import batch_intervention
    from ui import threshold_sim
    from ui import dashboard
    from ui import ab_designer
    return {
        "用户诊断": user_diagnosis,
        "批量干预": batch_intervention,
        "阈值模拟器": threshold_sim,
        "决策看板": dashboard,
        "A/B 实验设计": ab_designer,
    }


# ========== 全局异常捕获装饰器 ==========

def _safe_render(tab_name: str, render_func) -> None:
    """安全渲染 Tab 页面，捕获异常并显示友好提示"""
    try:
        render_func()
    except Exception as e:
        logger.error(f"页面 [{tab_name}] 渲染异常: {e}")
        logger.error(traceback.format_exc())
        st.error(
            f"页面「{tab_name}」加载时出现异常，请刷新重试。"
            f"如问题持续，请联系管理员。"
        )
        with st.expander("错误详情（调试用）", expanded=False):
            st.code(traceback.format_exc(), language="python")


# ========== 侧边栏：数据集管理 ==========

def _render_sidebar() -> None:
    """渲染侧边栏数据集管理模块"""
    st.sidebar.header("数据集管理")

    # 上传组件
    uploaded_file = st.sidebar.file_uploader(
        "上传数据集（.csv / .json）",
        type=["csv", "json"],
        help="支持 CSV（UTF-8 编码）或 JSON（数组格式），字段需与基准数据一致",
        key="dataset_uploader",
    )

    if uploaded_file is not None:
        _handle_upload(uploaded_file)

    # 数据集选择器
    datasets = get_available_datasets()
    dataset_names = list(datasets.keys())
    current_name = get_current_dataset_name()

    selected = st.sidebar.selectbox(
        "当前数据集",
        options=dataset_names,
        index=dataset_names.index(current_name) if current_name in dataset_names else 0,
        key="dataset_selector",
        on_change=lambda: switch_dataset(st.session_state["dataset_selector"]),
    )

    # 状态信息
    stats = get_dataset_stats()
    st.sidebar.divider()
    st.sidebar.caption(f"**数据集**: {stats['name']}")
    st.sidebar.caption(f"**用户总数**: {stats['total']} 人")
    st.sidebar.caption(f"**可干预用户**: {stats['applicable']} 人")


def _handle_upload(uploaded_file) -> None:
    """处理上传文件"""
    try:
        file_content = uploaded_file.read()
        filename = uploaded_file.name

        # 解析文件
        raw_data, parse_error = parse_uploaded_file(file_content, filename)
        if parse_error:
            st.sidebar.error(parse_error)
            return

        if raw_data is None:
            st.sidebar.error("文件解析失败，请检查文件格式")
            return

        # 校验并新增数据集
        success, message = validate_and_add_dataset(filename, raw_data)
        if success:
            st.sidebar.success(message)
            st.rerun()
        else:
            st.sidebar.error(message)
    except Exception as e:
        logger.error(f"上传处理异常: {e}")
        st.sidebar.error(f"上传处理失败，请检查文件格式（{e}）")


# ========== session_state 初始化 ==========

def _init_session() -> None:
    """幂等初始化 session_state（仅首次注入基准数据集）"""
    from utils.data_loader import _init_default_dataset
    _init_default_dataset()


# ========== 主入口 ==========

def main() -> None:
    """ChurnGuard 主应用"""
    _init_session()

    # 渲染侧边栏
    _render_sidebar()

    st.title(f"{settings.app_title} - 用户流失预警与干预系统")

    pages = _import_pages()
    tab_names = list(pages.keys())

    tabs = st.tabs(tab_names)

    for tab, (name, module) in zip(tabs, pages.items()):
        with tab:
            _safe_render(name, module.render)


if __name__ == "__main__":
    main()