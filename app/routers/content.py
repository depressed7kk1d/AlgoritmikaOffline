from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models import Content, Task
from app.schemas.content import ContentImportResult, ContentInfo, ScanResult, TaskIndex
from app.services.content import import_course_archive, scan_content_root

router = APIRouter(prefix="/content", tags=["content"])


@router.get("", response_model=list[ContentInfo])
def list_content(session: Session = Depends(get_session)) -> list[ContentInfo]:
    contents = session.query(Content).order_by(Content.id, Content.version).all()
    tasks = session.query(Task).all()

    tasks_by_content: dict[tuple[str, str], list[TaskIndex]] = defaultdict(list)
    for task in tasks:
        source = task.json_path or task.folder_path
        if not source:
            continue
        tasks_by_content[(task.course_id, task.version)].append(
            TaskIndex(
                id=task.id,
                course_id=task.course_id,
                version=task.version,
                kind=task.kind,  # type: ignore[arg-type]
                source_path=Path(source),
            )
        )

    response: list[ContentInfo] = []
    for content in contents:
        installed_at = datetime.fromtimestamp(content.installed_at, tz=timezone.utc)
        response.append(
            ContentInfo(
                id=content.id,
                version=content.version,
                title=content.title,
                installed_at=installed_at,
                status=content.status,
                tasks=sorted(tasks_by_content.get((content.id, content.version), []), key=lambda t: t.id),
            )
        )
    return response


@router.post("/import", response_model=ContentImportResult)
def import_content_package(
    file: UploadFile = File(..., description="Zip archive containing a course package"),
    session: Session = Depends(get_session),
) -> ContentImportResult:
    return import_course_archive(session, file)


@router.post("/scan", response_model=ScanResult)
def scan_content(session: Session = Depends(get_session)) -> ScanResult:
    results = scan_content_root(session)
    return ScanResult(imported=results)

