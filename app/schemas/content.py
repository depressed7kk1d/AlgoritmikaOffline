from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class TaskIndex(BaseModel):
    id: str
    course_id: str
    version: str
    kind: Literal["declarative", "custom_checker"]
    source_path: Path = Field(description="Relative path to the task descriptor inside the course")


class ContentInfo(BaseModel):
    id: str
    version: str
    title: str
    installed_at: datetime
    status: str | None = None
    tasks: list[TaskIndex] = Field(default_factory=list)


class ContentImportResult(BaseModel):
    course_id: str
    version: str
    title: str
    installed_at: datetime
    tasks_indexed: int
    warnings: list[str] = Field(default_factory=list)


class ScanResult(BaseModel):
    imported: list[ContentImportResult] = Field(default_factory=list)

