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

    # Dataset exported from the market warehouse (src/data/qlib_export.py). This
    # is the only dataset the engine reads: the retired official-download path is
    # gone, so a stale or foreign dataset cannot be picked up silently.
    qlib_export_path: str = str(Path(__file__).parent.parent / "data" / "market" / "qlib")

    # Database
    sqlite_db_path: str = "./data/aifund.db"

    # ChromaDB
    chroma_persist_dir: str = "./chroma_db"

    # Data provider: "pytdx" (default, pure Python)
    data_provider: str = "pytdx"

    # Market data warehouse (DuckDB). Holds unadjusted bars plus adjustment
    # factors; the Qlib dataset is exported from here for backtesting.
    market_data_dir: str = str(Path(__file__).parent.parent / "data" / "market")
    market_data_db: str = str(Path(__file__).parent.parent / "data" / "market" / "market.duckdb")

    # Index exported alongside stock data, used as the backtest benchmark. Its
    # features ship with the dataset but it must not look tradable, so the
    # exporter keeps it out of instruments/all.txt.
    benchmark_code: str = "000300.SH"

    # Agent-side sync defaults, so a conversational pull has sane bounds: one
    # year keeps the loop fast, and csi300 is the universe the engine works on.
    default_sync_index: str = "csi300"
    years_sync_default: int = 1

    # Source priority, most stable first. Used by build_provider_chain().
    data_source_priority: str = "baostock,pytdx,akshare"

    # Ceiling for a data-source login. BaoStock's login alone measured 75-78s
    # here, so this has to clear that comfortably: the point is to bound a stall,
    # not to fail fast, because the SDK itself sets no socket timeout.
    data_login_timeout: float = 180.0

    # Logging
    log_level: str = "INFO"

    # Project paths
    project_root: str = str(Path(__file__).parent.parent)
    factors_builtin_dir: str = str(Path(__file__).parent.parent / "factors" / "builtin")
    factors_custom_dir: str = str(Path(__file__).parent.parent / "factors" / "custom")
    strategies_dir: str = str(Path(__file__).parent.parent / "strategies")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
