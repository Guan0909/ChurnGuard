"""Pydantic 配置中心 —— 全项目基准常量与配置"""

from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """全局配置，所有常量带类型注解"""

    # ========== API 基础参数（保留架构扩展点，不硬编码密钥）==========
    DEEPSEEK_API_KEY: Optional[str] = None  # 从环境变量读取，None 表示未配置
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-v4-pro"

    # ========== 干预成本常量 ==========
    COSTS: dict = {"vip": 5.0, "push": 0.1, "manual": 15.0}

    # ========== 用户价值 LTV ==========
    VALUE_LTV: dict = {"high": 30, "mid": 10, "low": 2}

    # ========== 留存基线（四组对照）==========
    RETENTION_BASELINE: dict = {
        "no_intervention": 0.20,
        "generic_coupon": 0.30,
        "rule_based": 0.40,
        "ai_personalized": 0.48,
    }

    # ========== 风险与预算 ==========
    RISK_THRESHOLD: int = 70
    BUDGET_LIMIT: int = 500
    COOLDOWN_DAYS: int = 7

    # ========== Mock 模式 ==========
    MOCK_MODE: bool = True  # 始终为 True，演示环境零网络零配置

    # ========== 应用配置 ==========
    app_title: str = "ChurnGuard"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()