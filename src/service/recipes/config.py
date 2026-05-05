from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RECIPES_", env_file=".env", extra="ignore")

    sites: str = ""
    db_path: str = "recipes.db"
    rate_limit_delay: float = 2.0
    max_workers: int = 1
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    url_filter_pattern: str = r"/recipe"

    embed_url: str = Field(
        default="http://localhost:11434",
        description="Base URL of the embedding API (OpenAI-compatible: POST /v1/embeddings)",
    )
    embed_model: str = Field(
        default="",
        description="Embedding model name, e.g. 'nomic-embed-text'. Empty = disabled.",
    )
    embed_dim: int = Field(
        default=768,
        description="Vector dimension — must match the chosen model.",
    )
    embed_timeout: float = Field(
        default=30.0,
        description="Seconds before an embedding API request times out. Set RECIPES_EMBED_TIMEOUT to override.",
    )

    inference_url: str = Field(
        default="http://localhost:11434",
        description="Base URL of the inference API (OpenAI-compatible: POST /v1/chat/completions)",
    )
    inference_model: str = Field(
        default="",
        description="Chat model for recipe templatization, e.g. 'llama3.2'. Empty = disabled.",
    )
    inference_timeout: float = Field(
        default=120.0,
        description="Seconds before an inference API request times out.",
    )

    @property
    def site_list(self) -> list[str]:
        return [s.strip() for s in self.sites.split(",") if s.strip()]


settings = Settings()
