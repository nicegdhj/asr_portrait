"""
应用配置管理

使用 pydantic-settings 管理环境变量配置
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # ===========================================
    # 应用配置
    # ===========================================
    app_name: str = Field(default="portrait", description="应用名称")
    app_env: Literal["development", "production", "testing"] = Field(
        default="development", description="运行环境"
    )
    debug: bool = Field(default=True, description="调试模式")
    log_level: str = Field(default="INFO", description="日志级别")
    
    # ===========================================
    # API 配置
    # ===========================================
    api_host: str = Field(default="0.0.0.0", description="API 监听地址")
    api_port: int = Field(default=8000, description="API 端口")
    api_prefix: str = Field(default="/api/v1", description="API 路由前缀")
    
    # ===========================================
    # PostgreSQL (画像存储)
    # ===========================================
    postgres_host: str = Field(default="localhost", description="PostgreSQL 主机")
    postgres_port: int = Field(default=5432, description="PostgreSQL 端口")
    postgres_user: str = Field(default="portrait", description="PostgreSQL 用户")
    postgres_password: str = Field(default="", description="PostgreSQL 密码")
    postgres_db: str = Field(default="portrait", description="PostgreSQL 数据库")
    
    @property
    def postgres_dsn(self) -> str:
        """PostgreSQL 异步连接字符串"""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    @property
    def postgres_sync_dsn(self) -> str:
        """PostgreSQL 同步连接字符串 (用于 Alembic)"""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    # ===========================================
    # MySQL (源数据 - 只读)
    # ===========================================
    mysql_host: str = Field(default="localhost", description="MySQL 主机")
    mysql_port: int = Field(default=3306, description="MySQL 端口")
    mysql_user: str = Field(default="root", description="MySQL 用户")
    mysql_password: str = Field(default="", description="MySQL 密码")
    mysql_db: str = Field(default="outbound_saas", description="MySQL 数据库")
    
    @property
    def mysql_dsn(self) -> str:
        """MySQL 异步连接字符串"""
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}"
        )
    
    # ===========================================
    # LLM 配置
    # ===========================================
    llm_provider: Literal["openai", "qwen"] = Field(
        default="openai", description="LLM 服务商"
    )
    llm_api_key: str = Field(default="", description="LLM API Key")
    llm_api_base_url: str = Field(
        default="https://api.openai.com/v1", description="LLM API Base URL"
    )
    llm_model: str = Field(default="gpt-4o-mini", description="LLM 模型名称")
    llm_batch_size: int = Field(default=50, description="LLM 批处理大小")
    llm_max_concurrent: int = Field(default=5, description="LLM 最大并发数")
    llm_timeout: int = Field(default=30, description="LLM 请求超时(秒)")
    
    # ===========================================
    # 定时任务配置
    # ===========================================
    scheduler_enabled: bool = Field(default=True, description="是否启用定时任务")
    scheduler_timezone: str = Field(default="Asia/Shanghai", description="时区")
    sync_cron_hour: int = Field(default=2, description="同步任务执行小时")
    sync_cron_minute: int = Field(default=0, description="同步任务执行分钟")


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


# 全局配置实例
settings = get_settings()

