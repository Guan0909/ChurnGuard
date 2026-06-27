"""数据校验工具 —— Pydantic 模型校验 + 合规禁止词检查"""

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ========== Pydantic 数据模型 ==========

class UserSchema(BaseModel):
    """用户数据校验模型，字段与 data/users.json 严格对齐"""

    user_id: str = Field(..., min_length=1, max_length=10)
    name: str = Field(..., min_length=1, max_length=20)
    last_active_days: int = Field(..., ge=0, le=365)
    play_days_last_7: int = Field(..., ge=0, le=7)
    total_play_hours_last_7: float = Field(..., ge=0.0, le=168.0)
    favorite_genre: str
    recent_genre: str
    new_playlists_added: int = Field(..., ge=0, le=50)
    social_following: int = Field(..., ge=0)
    social_interaction: int = Field(..., ge=0)
    has_paid: bool
    searches_used: int = Field(..., ge=0)
    complaint_record: str = ""
    periodic_pattern: str = "no_pattern"
    value_tier: str = "low"
    churned: bool = False

    @field_validator("value_tier")
    @classmethod
    def check_value_tier(cls, v: str) -> str:
        if v not in ("high", "mid", "low"):
            raise ValueError(f"value_tier 必须是 high/mid/low，实际为: {v}")
        return v

    @field_validator("periodic_pattern")
    @classmethod
    def check_periodic_pattern(cls, v: str) -> str:
        if v not in ("weekday_active", "weekend_active", "no_pattern"):
            raise ValueError(f"periodic_pattern 必须是 weekday_active/weekend_active/no_pattern，实际为: {v}")
        return v

    @field_validator("favorite_genre", "recent_genre")
    @classmethod
    def check_genre(cls, v: str) -> str:
        valid_genres = {"流行", "摇滚", "电子", "古典", "说唱", "民谣", "爵士", "R&B"}
        if v not in valid_genres:
            raise ValueError(f"流派必须是 {valid_genres} 之一，实际为: {v}")
        return v


class ClassificationSchema(BaseModel):
    """Mock 分类结果校验模型"""

    user_id: str
    risk_score: int = Field(..., ge=0, le=100)
    tag_weights: dict
    primary_tag: str
    secondary_tag: str
    priority_score: float = Field(..., ge=0)
    is_applicable: bool


class CopywritingSchema(BaseModel):
    """Mock 文案校验模型 —— 输出字段: title / body / cta / songs"""

    user_id: str
    version: str
    title: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    cta: str = Field(default="打开 App")
    songs: list = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def check_version(cls, v: str) -> str:
        if v not in ("basic", "optimized", "warm"):
            raise ValueError(f"version 必须是 basic/optimized/warm，实际为: {v}")
        return v


# ========== 校验函数 ==========

def validate_user_data(user_data: dict) -> tuple[bool, Optional[str]]:
    """校验单个用户数据，返回 (是否通过, 错误信息)"""
    try:
        UserSchema(**user_data)
        return True, None
    except Exception as e:
        return False, str(e)


def validate_user_list(users: list[dict]) -> tuple[list[dict], list[dict]]:
    """批量校验用户列表，返回 (通过列表, 失败列表)"""
    passed = []
    failed = []
    for user in users:
        ok, err = validate_user_data(user)
        if ok:
            passed.append(user)
        else:
            failed.append({"user_id": user.get("user_id", "unknown"), "error": err})
    return passed, failed


def validate_classification(entry: dict) -> tuple[bool, Optional[str]]:
    """校验单条分类结果"""
    try:
        ClassificationSchema(**entry)
        return True, None
    except Exception as e:
        return False, str(e)


def validate_copywriting(entry: dict) -> tuple[bool, Optional[str]]:
    """校验单条文案"""
    try:
        CopywritingSchema(**entry)
        return True, None
    except Exception as e:
        return False, str(e)


# ========== 合规禁止词检查 ==========

FORBIDDEN_WORDS = [
    "免费领取",
    "点击就送",
    "限时抢购",
    "不买后悔",
    "最后机会",
    "立即购买",
    "疯狂打折",
    "绝版",
    "必买",
    "秒杀",
]


def check_forbidden_words(text: str) -> list[str]:
    """检查文案中是否包含合规禁止词，返回命中的禁止词列表"""
    hits = []
    for word in FORBIDDEN_WORDS:
        if word in text:
            hits.append(word)
    return hits


def validate_copywriting_compliance(copy_list: list[dict]) -> dict:
    """批量检查文案合规性

    Returns:
        {user_id: {version: [命中的禁止词]}}
    """
    violations = {}
    for entry in copy_list:
        uid = entry.get("user_id", "unknown")
        version = entry.get("version", "unknown")
        subject_hits = check_forbidden_words(entry.get("subject", ""))
        body_hits = check_forbidden_words(entry.get("body", ""))
        all_hits = subject_hits + body_hits
        if all_hits:
            if uid not in violations:
                violations[uid] = {}
            violations[uid][version] = all_hits
    return violations