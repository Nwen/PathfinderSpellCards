from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    port: int = 8000
    base_url: str = "http://localhost:8000"
    database_url: str = "sqlite:///./data/spells.db"
    data_dir: Path = Path("./data")
    wiki_dump_url: str = "http://db.pathfinder-fr.org/raw/wikixml.7z"
    log_level: str = "INFO"
    debug: bool = False
    scheduler_enabled: bool = True


settings = Settings()
