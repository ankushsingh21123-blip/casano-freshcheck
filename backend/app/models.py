"""Pydantic v2 request/response models with strict input bounds."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CheckCreate(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    answer: str = Field(..., min_length=1, max_length=5000)
    answer_date: date | None = None
    topic: Literal["general", "news"] = "general"

    @field_validator("question", "answer", mode="before")
    @classmethod
    def _strip_and_reject_blank(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("must not be blank")
            return stripped
        return value


class CheckResponse(BaseModel):
    id: int
    question: str
    answer: str
    answer_date: str | None
    topic: str
    mode: str
    verdict: str
    query: str
    reasons: list[str]
    signals: dict
    evidence: list[dict]
    error: dict | None
    message: str
    created_at: str


class HealthResponse(BaseModel):
    status: str
    mode: str
    service: str
