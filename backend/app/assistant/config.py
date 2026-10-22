from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AssistantSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="ASSISTANT_")

    enabled: bool = False
    model: str = "Qwen/Qwen3.8-27B"
    base_url: HttpUrl = "http://localhost:8001/v1"
    api_key: str = ""
    timeout_seconds: int = Field(90, ge=5, le=300)
    turn_timeout_seconds: int = Field(180, ge=10, le=600)
    max_output_tokens: int = Field(2048, ge=128, le=8192)
    max_tool_rounds: int = Field(3, ge=1, le=5)
    requests_per_minute: int = Field(12, ge=1, le=120)
    max_parallel_per_user: int = Field(2, ge=1, le=10)
    history_turns: int = Field(8, ge=1, le=20)

    @field_validator("base_url")
    @classmethod
    def endpoint_only(cls, value):
        if value.username or value.password or value.query or value.fragment:
            raise ValueError("Use a base URL without credentials, query or fragment")
        return value


settings = AssistantSettings()
