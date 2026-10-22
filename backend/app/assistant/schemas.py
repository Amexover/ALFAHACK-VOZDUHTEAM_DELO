from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConversationIn(Input):
    company_id: int | None = Field(None, gt=0)
    application_id: int | None = Field(None, gt=0)
    title: str = Field("Новый диалог", min_length=1, max_length=120)


class MessageIn(Input):
    request_id: UUID
    content: str = Field(min_length=1, max_length=6000)
    intent: Literal["chat", "rating", "advice", "news", "application_review", "draft_reply"] = "chat"


class DocumentIn(Input):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=40000)
    audience: Literal["client", "staff"] = "client"
    kind: Literal["knowledge", "news"] = "knowledge"
    source_url: HttpUrl | None = None
    published_at: datetime | None = None

    @field_validator("source_url")
    @classmethod
    def public_link(cls, value):
        if value and (value.username or value.password):
            raise ValueError("Credentials are not allowed in source URLs")
        return value

    @model_validator(mode="after")
    def dated_news(self):
        if self.published_at is not None:
            if self.published_at.tzinfo is None or self.published_at > datetime.now(timezone.utc):
                raise ValueError("published_at must include timezone and must not be in the future")
        if self.kind == "news" and (not self.published_at or not self.source_url):
            raise ValueError("News requires source_url and published_at")
        return self


class Source(BaseModel):
    id: str
    title: str
    kind: str
    url: str | None = None
    published_at: str | None = None
    is_demo: bool = False
    excerpt: str = ""


class TurnOut(BaseModel):
    id: str
    request_id: str
    status: str
    intent: str
    user_content: str
    assistant_content: str | None
    sources: list[Source]
    tool_calls: list[dict]
    usage: dict
    model: str
    error_code: str | None
    latency_ms: int | None
    created_at: datetime
    finished_at: datetime | None

    @field_validator("created_at", "finished_at", mode="after")
    @classmethod
    def utc_dates(cls, value):
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


class ConversationOut(BaseModel):
    id: str
    audience: str
    company_id: int | None
    application_id: int | None
    title: str
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at", mode="after")
    @classmethod
    def utc_dates(cls, value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
