from __future__ import annotations

import json
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from zipfile import ZipFile

from fastapi import HTTPException, UploadFile, status
from jsonschema import Draft7Validator
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Content, Task
from app.schemas.content import ContentImportResult

_SCHEMAS_CACHE: dict[str, Draft7Validator] = {}


def _load_schema(name: str) -> Draft7Validator:
    if name in _SCHEMAS_CACHE:
        return _SCHEMAS_CACHE[name]

    schema_path = Path(__file__).resolve().parent.parent / "schemas" / "json" / f"{name}.json"
    if not schema_path.exists():
        raise RuntimeError(f"Schema '{name}' not found at {schema_path}")
    with schema_path.open("r", encoding="utf-8") as fh:
        schema_data = json.load(fh)
    validator = Draft7Validator(schema_data)
    _SCHEMAS_CACHE[name] = validator
    return validator


def _validate_json(data: dict, schema_name: str) -> list[str]:
    validator = _load_schema(schema_name)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    return [f"{'.'.join(map(str, error.path))}: {error.message}" for error in errors]


def _ensure_single_root(temp_dir: Path) -> Path:
    entries = [p for p in temp_dir.iterdir() if not p.name.startswith("__MACOSX")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return temp_dir


def _iter_task_descriptors(tasks_dir: Path) -> Iterable[Path]:
    seen: set[Path] = set()
    for path in sorted(tasks_dir.rglob("*")):
        candidate: Path | None = None
        if path.is_dir() and (path / "task.json").exists():
            candidate = path / "task.json"
        elif path.is_file() and path.suffix.lower() == ".json":
            candidate = path

        if candidate and candidate not in seen:
            seen.add(candidate)
            yield candidate


def _relative_to_course(path: Path, course_root: Path) -> Path:
    return path.relative_to(course_root)


def _index_course(
    session: Session,
    course_dir: Path,
    manifest: dict,
    *,
    installed_at_ts: int | None = None,
) -> ContentImportResult:
    course_id = manifest["id"]
    version = manifest["version"]
    title = manifest.get("title", course_id)

    if installed_at_ts is None:
        existing = (
            session.query(Content)
            .filter(Content.id == course_id, Content.version == version)
            .one_or_none()
        )
        installed_at_ts = existing.installed_at if existing else int(time.time())

    session.execute(delete(Content).where(Content.id == course_id, Content.version == version))

    content = Content(
        id=course_id,
        version=version,
        title=title,
        installed_at=installed_at_ts,
        status="installed",
    )
    session.add(content)
    session.flush()

    session.execute(delete(Task).where(Task.course_id == course_id, Task.version == version))

    tasks_dir = course_dir / "tasks"
    warnings: list[str] = []
    indexed = 0

    if tasks_dir.exists():
        for descriptor_path in _iter_task_descriptors(tasks_dir):
            if descriptor_path.name == "task.json":
                schema_name = "task_folder.schema"
            else:
                schema_name = "task.schema"

            with descriptor_path.open("r", encoding="utf-8") as fh:
                task_data = json.load(fh)

            errors = _validate_json(task_data, schema_name)
            if errors:
                warnings.append(f"{_relative_to_course(descriptor_path, course_dir)}: {'; '.join(errors)}")
                continue

            task_id = task_data["id"]
            kind = task_data["kind"]
            rel_path = _relative_to_course(descriptor_path, course_dir)
            if descriptor_path.name == "task.json":
                json_path: str | None = None
                folder_path: str | None = str(rel_path.parent)
            else:
                json_path = str(rel_path)
                folder_path = None

            session.add(
                Task(
                    id=task_id,
                    course_id=course_id,
                    version=version,
                    kind=kind,
                    json_path=json_path,
                    folder_path=folder_path,
                )
            )
            indexed += 1

    installed_at = datetime.fromtimestamp(installed_at_ts, tz=timezone.utc)

    return ContentImportResult(
        course_id=course_id,
        version=version,
        title=title,
        installed_at=installed_at,
        tasks_indexed=indexed,
        warnings=warnings,
    )


def import_course_archive(session: Session, upload: UploadFile) -> ContentImportResult:
    settings = get_settings()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        archive_path = tmp_path / "upload.zip"
        with archive_path.open("wb") as buffer:
            shutil.copyfileobj(upload.file, buffer)

        extract_dir = tmp_path / "extracted"
        with ZipFile(archive_path) as zf:
            zf.extractall(extract_dir)

        course_root = _ensure_single_root(extract_dir)
        manifest_path = course_root / "manifest.json"
        if not manifest_path.exists():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="manifest.json not found")

        with manifest_path.open("r", encoding="utf-8") as fh:
            manifest = json.load(fh)

        manifest_errors = _validate_json(manifest, "manifest.schema")
        if manifest_errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"manifest": manifest_errors},
            )

        destination = settings.content_dir / manifest["id"] / manifest["version"]
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(course_root), destination)

    installed_at_ts = int(time.time())
    return _index_course(session, destination, manifest, installed_at_ts=installed_at_ts)


def scan_content_root(session: Session) -> list[ContentImportResult]:
    settings = get_settings()
    results: list[ContentImportResult] = []

    for course_dir in sorted(settings.content_dir.iterdir()):
        if not course_dir.is_dir():
            continue
        for version_dir in sorted(course_dir.iterdir()):
            if not version_dir.is_dir():
                continue

            manifest_path = version_dir / "manifest.json"
            if not manifest_path.exists():
                installed_at = datetime.fromtimestamp(int(version_dir.stat().st_mtime), tz=timezone.utc)
                results.append(
                    ContentImportResult(
                        course_id=course_dir.name,
                        version=version_dir.name,
                        title=course_dir.name,
                        installed_at=installed_at,
                        tasks_indexed=0,
                        warnings=["manifest.json missing"],
                    )
                )
                continue

            with manifest_path.open("r", encoding="utf-8") as fh:
                manifest = json.load(fh)

            manifest.setdefault("id", course_dir.name)
            manifest.setdefault("version", version_dir.name)

            errors = _validate_json(manifest, "manifest.schema")
            warning = None
            if errors:
                warning = f"manifest.json: {'; '.join(errors)}"

            result = _index_course(session, version_dir, manifest, installed_at_ts=None)
            if warning:
                result.warnings.append(warning)
            results.append(result)

    return results

