"""Configuration for persona-core, loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class PersonaCoreConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PERSONA_")

    backend: str = "anthropic"
    api_key: str = ""
    model: str = "claude-sonnet-4-6"
    chroma_path: str = ".chroma/"
    log_level: str = "INFO"
