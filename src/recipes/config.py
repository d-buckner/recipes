from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RECIPES_", env_file=".env", extra="ignore")

    sites: str = ""
    db_path: str = "recipes.db"
    rate_limit_delay: float = 2.0
    max_workers: int = 1
    user_agent: str = "RecipeBot/1.0 (+https://github.com/local/recipes)"
    url_filter_pattern: str = r"/recipe"

    @property
    def site_list(self) -> list[str]:
        return [s.strip() for s in self.sites.split(",") if s.strip()]


settings = Settings()
