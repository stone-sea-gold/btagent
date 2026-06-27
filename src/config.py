"""Application configuration via pydantic-settings.

LLM Provider Design:
- Named providers (anthropic, openai, deepseek, ollama) as shortcuts
- Any provider with a custom base_url: auto-detects protocol from URL
  - URL contains "/anthropic" → Anthropic protocol (ChatAnthropic)
  - Otherwise → OpenAI protocol (ChatOpenAI)
- "custom" provider: uses generic LLM_API_KEY / LLM_MODEL / LLM_BASE_URL
"""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM Provider: "anthropic", "openai", "deepseek", "ollama", "custom"
    llm_provider: str = "anthropic"

    # Anthropic (Claude) — official API
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # OpenAI — official API
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = ""

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

    # Ollama (local)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b"

    # Custom provider (any OpenAI/Anthropic-compatible API)
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""

    # Shared LLM settings
    llm_timeout: float = 60.0
    llm_max_retries: int = 3

    # Qlib
    qlib_data_path: str = str(Path.home() / ".qlib" / "qlib_data" / "cn_data")

    # Database
    sqlite_db_path: str = "./data/aifund.db"

    # ChromaDB
    chroma_persist_dir: str = "./chroma_db"

    # Logging
    log_level: str = "INFO"

    # Project paths
    project_root: str = str(Path(__file__).parent.parent)
    factors_builtin_dir: str = str(Path(__file__).parent.parent / "factors" / "builtin")
    factors_custom_dir: str = str(Path(__file__).parent.parent / "factors" / "custom")
    strategies_dir: str = str(Path(__file__).parent.parent / "strategies")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
