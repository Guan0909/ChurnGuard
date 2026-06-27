"""LLM 统一客户端 —— Mock 模式下读取本地 JSON，架构上保留真实 API 扩展能力"""

import json
import os
import time
from functools import wraps
from typing import Any, Optional

from config import settings
from engine.rule_engine import evaluate_user
from llm.prompts import format_prompt
from utils.validator import ClassificationSchema, CopywritingSchema


# ========== 重试逻辑（内联实现，无需额外依赖）==========

def _retry(max_attempts: int = 2, base_delay: float = 1.0):
    """简易重试装饰器：最多重试 max_attempts 次，指数退避

    触发场景：网络异常、5xx、429、JSON 解析失败
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except (ConnectionError, TimeoutError, OSError) as e:
                    last_error = e
                    if attempt < max_attempts - 1:
                        delay = base_delay * (2 ** attempt)
                        time.sleep(delay)
                except (ValueError, json.JSONDecodeError) as e:
                    last_error = e
                    if attempt < max_attempts - 1:
                        delay = base_delay * (2 ** attempt)
                        time.sleep(delay)
                except Exception as e:
                    # HTTP 5xx / 429 等由调用方包装为特定异常
                    error_msg = str(e).lower()
                    if any(code in error_msg for code in ["500", "502", "503", "504", "429"]):
                        last_error = e
                        if attempt < max_attempts - 1:
                            delay = base_delay * (2 ** attempt)
                            time.sleep(delay)
                    else:
                        raise
            raise last_error  # type: ignore
        return wrapper
    return decorator


# ========== Mock 数据管理 ==========

_mock_cache: Optional[dict] = None


def _load_mock_data() -> dict:
    """加载 mock_responses.json，按 user_id 建立字典索引，仅首次读取"""
    global _mock_cache
    if _mock_cache is not None:
        return _mock_cache

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "data", "mock_responses.json")
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    # 按 user_id 建立字典索引
    classification_index = {}
    for entry in data.get("classification", []):
        classification_index[entry["user_id"]] = entry

    # copywriting 实际结构为 {user_id: {version: "纯文本"}}，需转换为结构化对象
    copywriting_index = {}
    raw_copy = data.get("copywriting", {})
    if isinstance(raw_copy, dict):
        for uid, versions in raw_copy.items():
            copywriting_index[uid] = {}
            for version, text in versions.items():
                # 纯文本 → 结构化：第一句为 title，其余为 body
                lines = text.split("。")
                title = lines[0].strip()
                body = "。".join(lines[1:]).strip() if len(lines) > 1 else text
                copywriting_index[uid][version] = {
                    "user_id": uid,
                    "version": version,
                    "title": title,
                    "body": body,
                    "cta": "打开 App 发现更多",
                    "songs": [],
                }
    else:
        # 兼容旧格式（数组）
        for entry in raw_copy:
            uid = entry["user_id"]
            version = entry.get("version", "basic")
            if uid not in copywriting_index:
                copywriting_index[uid] = {}
            copywriting_index[uid][version] = entry

    _mock_cache = {
        "classification": classification_index,
        "copywriting": copywriting_index,
    }
    return _mock_cache


# ========== 核心函数 1: 流失原因分类 ==========

def classify_churn_reason(user_profile: dict) -> dict:
    """对用户进行流失原因分类

    Mock 模式：从 mock_responses.json 按 user_id 匹配，返回标签相关结果。
    风险分由规则引擎负责，LLM 仅输出标签、权重、解释。

    Args:
        user_profile: 用户完整数据字典

    Returns:
        {user_id, risk_score, tag_weights, primary_tag, secondary_tag,
         priority_score, is_applicable, explanation}
    """
    if settings.MOCK_MODE:
        return _mock_classify(user_profile)
    else:
        return _real_classify(user_profile)


def _mock_classify(user_profile: dict) -> dict:
    """Mock 分类：从本地 JSON 匹配，失败时降级到规则引擎"""
    mock_data = _load_mock_data()
    uid = user_profile.get("user_id", "")

    # 尝试从 Mock 数据匹配
    mock_entry = mock_data["classification"].get(uid)
    if mock_entry:
        try:
            ClassificationSchema(**mock_entry)
            # 补充 explanation 字段
            result = dict(mock_entry)
            result["explanation"] = _build_explanation(user_profile, result)
            return result
        except Exception:
            pass  # 校验失败，降级到规则引擎

    # 降级：使用规则引擎计算
    engine_result = evaluate_user(user_profile)
    engine_result["explanation"] = _build_explanation(user_profile, engine_result)
    return engine_result


def _build_explanation(user_profile: dict, result: dict) -> str:
    """根据标签权重构建可读解释"""
    primary = result.get("primary_tag", "")
    tag_explanations = {
        "low_activity": f"用户已 {user_profile.get('last_active_days', 0)} 天未活跃，活跃度下降是主要流失原因",
        "interest_shift": f"用户兴趣从 {user_profile.get('favorite_genre', '')} 转向 {user_profile.get('recent_genre', '')}，兴趣迁移增加了流失风险",
        "content_fatigue": f"用户近 7 天播放 {user_profile.get('play_days_last_7', 0)} 天但仅新增 {user_profile.get('new_playlists_added', 0)} 个歌单，内容疲劳是核心问题",
        "social_isolation": f"用户社交互动仅 {user_profile.get('social_interaction', 0)} 次，关注 {user_profile.get('social_following', 0)} 人，社交连接薄弱",
        "function_issue": f"用户反馈「{user_profile.get('complaint_record', '')}」，功能体验问题需优先解决",
    }
    return tag_explanations.get(primary, "多因素综合导致流失风险")


@_retry(max_attempts=2, base_delay=1.0)
def _real_classify(user_profile: dict) -> dict:
    """真实 API 分类调用骨架

    API 约定：
    - 模型：settings.DEEPSEEK_MODEL
    - Temperature: 0.1（低温度保证分类稳定性）
    - 响应格式：JSON 模式
    - 请求体：{system_prompt, user_prompt}

    当前为骨架实现，接入真实 API 时替换内部逻辑。
    """
    # TODO: 实现真实 DeepSeek API 调用
    # import requests
    #
    # payload = {
    #     "model": settings.DEEPSEEK_MODEL,
    #     "messages": [
    #         {"role": "system", "content": "你是用户流失分析专家，输出 JSON 格式"},
    #         {"role": "user", "content": json.dumps(user_profile, ensure_ascii=False)},
    #     ],
    #     "temperature": 0.1,
    #     "response_format": {"type": "json_object"},
    # }
    # headers = {
    #     "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
    #     "Content-Type": "application/json",
    # }
    # resp = requests.post(
    #     f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
    #     json=payload,
    #     headers=headers,
    #     timeout=30,
    # )
    # if resp.status_code >= 500 or resp.status_code == 429:
    #     raise Exception(f"API {resp.status_code} error")
    # resp.raise_for_status()
    # result = resp.json()
    # content = result["choices"][0]["message"]["content"]
    # parsed = json.loads(content)
    # ClassificationSchema(**parsed)
    # return parsed

    # 当前回退到规则引擎
    return _mock_classify(user_profile)


# ========== 核心函数 2: 个性化文案生成 ==========

def generate_copywriting(
    user_profile: dict,
    primary_tag: str,
    version: str = "basic",
) -> dict:
    """生成个性化干预文案

    Mock 模式：从 mock_responses.json 按 user_id + version 匹配，返回预置文案。
    架构上保留真实 API 调用的接口。

    Args:
        user_profile: 用户完整数据字典
        primary_tag: 主标签（low_activity / interest_shift / content_fatigue / social_isolation / function_issue）
        version: Prompt 版本（basic / optimized / warm）

    Returns:
        {user_id, version, title, body, cta, songs}
    """
    if version not in ("basic", "optimized", "warm"):
        version = "basic"

    if settings.MOCK_MODE:
        return _mock_generate(user_profile, primary_tag, version)
    else:
        return _real_generate(user_profile, primary_tag, version)


def _mock_generate(user_profile: dict, primary_tag: str, version: str) -> dict:
    """Mock 文案生成：从本地 JSON 匹配，失败时降级到通用模板"""
    mock_data = _load_mock_data()
    uid = user_profile.get("user_id", "")

    # 尝试从 Mock 数据匹配
    user_versions = mock_data["copywriting"].get(uid, {})
    mock_entry = user_versions.get(version)
    if mock_entry:
        try:
            # 映射字段：subject → title，补充 cta 和 songs
            mapped = {
                "user_id": mock_entry.get("user_id", uid),
                "version": mock_entry.get("version", version),
                "title": mock_entry.get("subject", ""),
                "body": mock_entry.get("body", ""),
                "cta": mock_entry.get("cta", "打开 App 发现更多"),
                "songs": mock_entry.get("songs", []),
            }
            CopywritingSchema(**mapped)
            return mapped
        except Exception:
            pass  # 校验失败，降级

    # 降级：使用通用模板
    return _build_fallback_copywriting(user_profile, primary_tag, version)


def _build_fallback_copywriting(user_profile: dict, primary_tag: str, version: str) -> dict:
    """构建通用降级文案模板"""
    name = user_profile.get("name", "用户")
    genre = user_profile.get("favorite_genre", "音乐")

    templates = {
        "basic": {
            "title": f"嗨，{name}，好久不见！",
            "body": f"你喜欢的{genre}音乐还在等你，快回来听听吧。",
            "cta": "立即打开",
            "songs": [],
        },
        "optimized": {
            "title": f"{name}，为你精选了{genre}好歌",
            "body": f"根据你的听歌偏好，我们更新了一批{genre}歌单，等你来探索。",
            "cta": "探索新歌",
            "songs": [],
        },
        "warm": {
            "title": f"{name}，音乐一直在等你",
            "body": f"生活忙碌没关系，好音乐不会走远。你的{genre}歌单一直在这里，随时欢迎回来。",
            "cta": "回来听听",
            "songs": [],
        },
    }

    tpl = templates.get(version, templates["basic"])
    return {
        "user_id": user_profile.get("user_id", ""),
        "version": version,
        "title": tpl["title"],
        "body": tpl["body"],
        "cta": tpl["cta"],
        "songs": tpl["songs"],
    }


@_retry(max_attempts=2, base_delay=1.0)
def _real_generate(user_profile: dict, primary_tag: str, version: str) -> dict:
    """真实 API 文案生成骨架

    API 约定：
    - 模型：settings.DEEPSEEK_MODEL
    - Temperature: 0.8（较高温度增加文案多样性）
    - 响应格式：JSON 模式
    - 请求体：{system_prompt, user_prompt}
    - 输出字段：title / body / cta / songs

    当前为骨架实现，接入真实 API 时替换内部逻辑。
    """
    # TODO: 实现真实 DeepSeek API 调用
    # import requests
    #
    # prompt = format_prompt(version, primary_tag, user_profile)
    #
    # payload = {
    #     "model": settings.DEEPSEEK_MODEL,
    #     "messages": [
    #         {"role": "system", "content": prompt["system"]},
    #         {"role": "user", "content": prompt["template"]},
    #     ],
    #     "temperature": 0.8,
    #     "response_format": {"type": "json_object"},
    # }
    # headers = {
    #     "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
    #     "Content-Type": "application/json",
    # }
    # resp = requests.post(
    #     f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
    #     json=payload,
    #     headers=headers,
    #     timeout=30,
    # )
    # if resp.status_code >= 500 or resp.status_code == 429:
    #     raise Exception(f"API {resp.status_code} error")
    # resp.raise_for_status()
    # result = resp.json()
    # content = result["choices"][0]["message"]["content"]
    # parsed = json.loads(content)
    # CopywritingSchema(**parsed)
    # return parsed

    # 当前回退到 Mock 模式
    return _mock_generate(user_profile, primary_tag, version)


# ========== 便捷函数 ==========

def generate_all_versions(user_profile: dict, primary_tag: str) -> dict:
    """一次性生成三套版本文案（basic / optimized / warm）

    Returns:
        {"basic": {...}, "optimized": {...}, "warm": {...}}
    """
    results = {}
    for version in ("basic", "optimized", "warm"):
        results[version] = generate_copywriting(user_profile, primary_tag, version)
    return results