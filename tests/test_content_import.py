from __future__ import annotations

import json
from importlib import reload
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
import app.db.session as session_module


@pytest.fixture()
def test_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("APP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("APP_DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")

    global session_module

    get_settings.cache_clear()
    session_module.reset_engine()
    session_module = reload(session_module)

    import app.main as main_module

    main_module = reload(main_module)

    client = TestClient(main_module.app)
    try:
        yield client
    finally:
        client.close()
        session_module.reset_engine()
        get_settings.cache_clear()


def build_course_archive(base_dir: Path) -> Path:
    course_dir = base_dir / "course"
    tasks_dir = course_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "id": "py-basics",
        "version": "1.0.0",
        "title": "Python Basics",
        "modules": ["intro"],
    }
    (course_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    task = {
        "id": "sum_two_numbers",
        "title": "Сумма двух чисел",
        "description": "Считай два числа и выведи их сумму",
        "language": "python",
        "kind": "declarative",
        "tests": [
            {"name": "t1", "input": "1\n2\n", "expected": "3\n"},
            {"name": "t2", "input": "5\n7\n", "expected": "12\n"},
        ],
    }
    (tasks_dir / "sum_two_numbers.json").write_text(json.dumps(task), encoding="utf-8")

    archive_path = base_dir / "course.zip"
    with ZipFile(archive_path, "w") as zf:
        for file in course_dir.rglob("*"):
            zf.write(file, file.relative_to(course_dir))
    return archive_path


def test_import_and_list_content(test_client: TestClient, tmp_path: Path) -> None:
    archive = build_course_archive(tmp_path)
    with archive.open("rb") as fh:
        response = test_client.post("/content/import", files={"file": ("course.zip", fh, "application/zip")})
    assert response.status_code == 200
    payload = response.json()
    assert payload["course_id"] == "py-basics"
    assert payload["tasks_indexed"] == 1

    response = test_client.get("/content")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Python Basics"
    assert data[0]["tasks"][0]["id"] == "sum_two_numbers"


def test_scan_content(test_client: TestClient, tmp_path: Path) -> None:
    archive = build_course_archive(tmp_path)
    with archive.open("rb") as fh:
        test_client.post("/content/import", files={"file": ("course.zip", fh, "application/zip")})

    response = test_client.post("/content/scan")
    assert response.status_code == 200
    data = response.json()
    assert len(data["imported"]) == 1
    assert data["imported"][0]["course_id"] == "py-basics"
    assert data["imported"][0]["tasks_indexed"] == 1

