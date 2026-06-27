"""数据集管理 —— 多数据集独立切换、上传校验、统一数据源"""

import csv
import io
import json
import os

import streamlit as st

from engine.rule_engine import is_intervention_applicable
from utils.validator import validate_user_data

# ========== 必填字段 ==========

REQUIRED_FIELDS = [
    "user_id", "name", "last_active_days", "play_days_last_7",
    "total_play_hours_last_7", "favorite_genre", "recent_genre",
    "new_playlists_added", "social_following", "social_interaction",
    "has_paid", "searches_used", "complaint_record",
    "periodic_pattern", "value_tier", "churned",
]

# ========== 基准数据集加载 ==========

def _load_default_users():
    """从 data/users.json 加载基准数据"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "data", "users.json")
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _init_default_dataset() -> None:
    """幂等初始化基准数据集（仅首次注入）"""
    if "datasets" not in st.session_state:
        default_users = _load_default_users()
        st.session_state["datasets"] = {
            "默认基准数据": {
                "label": "默认基准数据",
                "users": default_users,
                "is_default": True,
            },
        }
        st.session_state["current_dataset"] = "默认基准数据"


# ========== 核心 API ==========

def get_available_datasets():
    """获取所有可用数据集

    Returns:
        {name: {"label": str, "users": list, "is_default": bool}}
    """
    _init_default_dataset()
    return st.session_state.get("datasets", {})


def load_current_users():
    """获取当前选中数据集的用户列表"""
    _init_default_dataset()
    datasets = st.session_state.get("datasets", {})
    current_name = st.session_state.get("current_dataset", "默认基准数据")
    dataset = datasets.get(current_name, {})
    return dataset.get("users", [])


def get_current_dataset_name() -> str:
    """获取当前数据集名称"""
    _init_default_dataset()
    return st.session_state.get("current_dataset", "默认基准数据")


def switch_dataset(name: str) -> None:
    """切换当前数据集并清空所有计算缓存"""
    if name in st.session_state.get("datasets", {}):
        st.session_state["current_dataset"] = name
        st.cache_data.clear()
        st.rerun()


# ========== 上传校验与新增 ==========

def validate_and_add_dataset(name, raw_data):
    """校验并新增数据集

    Args:
        name: 数据集名称（文件名）
        raw_data: 原始用户数据列表

    Returns:
        (成功/失败, 消息)
    """
    _init_default_dataset()

    # 字段名校验
    if not raw_data:
        return False, "上传数据为空，请检查文件内容"

    sample = raw_data[0]
    missing_fields = [f for f in REQUIRED_FIELDS if f not in sample]
    if missing_fields:
        return False, f"缺少必填字段: {', '.join(missing_fields)}"

    # 逐行校验
    passed = []
    failed_count = 0
    seen_ids = set()

    for i, row in enumerate(raw_data, start=1):
        ok, err = validate_user_data(row)
        if not ok:
            failed_count += 1
            # 只记录前 5 条错误，避免消息过长
            if failed_count <= 5:
                continue
        else:
            uid = row.get("user_id", "")
            if uid in seen_ids:
                continue  # 重复 user_id 自动去重，保留第一条
            seen_ids.add(uid)
            passed.append(row)

    if failed_count > 0:
        if len(passed) == 0:
            return False, f"全部 {failed_count} 条数据校验失败，请检查字段类型和取值范围"
        # 部分失败
        detail = ""
        if failed_count <= 5:
            detail = f"，{failed_count} 条失败"
        else:
            detail = f"，{failed_count} 条失败（仅展示前5条）"
        st.warning(f"数据集「{name}」导入完成：{len(passed)} 条通过{detail}")

    if len(passed) == 0:
        return False, "无有效数据通过校验"

    # 重复文件名处理
    datasets = st.session_state["datasets"]
    final_name = name
    counter = 1
    while final_name in datasets:
        final_name = f"{name} ({counter})"
        counter += 1

    # 存入 session_state
    datasets[final_name] = {
        "label": final_name,
        "users": passed,
        "is_default": False,
    }
    st.session_state["datasets"] = datasets

    # 自动切换
    st.session_state["current_dataset"] = final_name
    st.cache_data.clear()

    duplicate_note = ""
    if final_name != name:
        duplicate_note = f"（重名已自动重命名为「{final_name}」）"

    return True, f"导入成功：{len(passed)} 条用户数据已加入数据集列表{duplicate_note}"


# ========== 文件解析 ==========

def parse_uploaded_file(file_content, filename):
    """解析上传文件内容为 dict 列表

    Returns:
        (数据列表, 错误信息) — 成功时 error 为 None
    """
    lower_name = filename.lower()

    if lower_name.endswith(".json"):
        return _parse_json(file_content)

    if lower_name.endswith(".csv"):
        return _parse_csv(file_content)

    return None, f"不支持的文件格式: {filename}，请上传 .csv 或 .json 文件"


def _parse_json(content):
    """解析 JSON 文件"""
    try:
        text = content.decode("utf-8-sig")
        data = json.loads(text)
        if not isinstance(data, list):
            return None, "JSON 文件必须是数组格式 [{...}, {...}]"
        return data, None
    except json.JSONDecodeError as e:
        return None, f"JSON 解析失败: {e}"
    except UnicodeDecodeError:
        return None, "文件编码错误，请使用 UTF-8 编码"


def _parse_csv(content: bytes):
    """解析 CSV 文件，前置列名校验"""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, "文件编码错误，请使用 UTF-8 编码"

    try:
        reader = csv.DictReader(io.StringIO(text))
        fieldnames = reader.fieldnames
        if fieldnames is None:
            return None, "CSV 文件为空或格式错误"

        # 前置列名校验
        missing_cols = [f for f in REQUIRED_FIELDS if f not in fieldnames]
        if missing_cols:
            return None, f"CSV 缺少必填列: {', '.join(missing_cols)}"

        rows = []
        for row in reader:
            # 类型转换
            converted = {}
            for key, val in row.items():
                if key in ("last_active_days", "play_days_last_7", "new_playlists_added",
                           "social_following", "social_interaction", "searches_used"):
                    try:
                        converted[key] = int(val) if val.strip() else 0
                    except ValueError:
                        converted[key] = 0
                elif key == "total_play_hours_last_7":
                    try:
                        converted[key] = float(val) if val.strip() else 0.0
                    except ValueError:
                        converted[key] = 0.0
                elif key == "has_paid":
                    converted[key] = val.strip().lower() in ("true", "1", "yes")
                elif key == "churned":
                    converted[key] = val.strip().lower() in ("true", "1", "yes")
                else:
                    converted[key] = val.strip()
            rows.append(converted)
        return rows, None
    except Exception as e:
        return None, f"CSV 解析失败: {e}"


# ========== 统计信息 ==========

def get_dataset_stats() -> dict:
    """获取当前数据集统计信息"""
    users = load_current_users()
    total = len(users)
    applicable = sum(1 for u in users if is_intervention_applicable(u))
    return {
        "name": get_current_dataset_name(),
        "total": total,
        "applicable": applicable,
    }