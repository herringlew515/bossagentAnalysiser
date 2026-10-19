from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")
    app_name: str = "职向 · 智能就业分析助手"
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "bossinfo"
    mysql_table: str = "jobinfo"
    allow_demo: bool = True
    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_model: str = ""
    llm_timeout_seconds: int = 60
    sql_max_attempts: int = Field(3, ge=1, le=5)
    sql_max_rows: int = Field(100, ge=1, le=1000)
    sql_timeout_ms: int = Field(5000, ge=100, le=30000)
    embedding_provider: Literal["hash", "sentence_transformers", "api"] = "hash"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_dimensions: int = Field(768, ge=32)
    embedding_batch_size: int = Field(32, ge=1, le=128)
    embedding_cpu_threads: int = Field(4, ge=1, le=32)
    index_dir: Path = ROOT / "data/index"
    rag_top_k: int = Field(5, ge=1, le=20)
    rag_candidates: int = Field(30, ge=5, le=100)
    chunk_max_chars: int = Field(500, ge=100)
    chunk_semantic_threshold: float = Field(0.55, ge=-1, le=1)
    service_api_key: str = ""

    @model_validator(mode="after")
    def validate_identifiers(self):
        import re
        for name in (self.mysql_database, self.mysql_table):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ValueError("数据库和表名必须是合法标识符")
        if not self.index_dir.is_absolute():
            self.index_dir = ROOT / self.index_dir
        return self

    @property
    def llm_ready(self) -> bool:
        return bool(self.kimi_api_key and self.kimi_model)


@lru_cache
def get_settings() -> Settings:
    return Settings()
