# AlgoritmikaOffline

## Backend API (FastAPI)

The repository now contains the first iteration of the offline-first platform backend built with FastAPI and SQLite.

### Prerequisites

- Python 3.11+
- Recommended: a virtual environment (e.g. `python -m venv .venv`)

### Installation

```bash
pip install -e .[dev]
```

### Running the API locally

```bash
uvicorn app.main:app --reload
```

Application state (SQLite database, imported content) is stored under `./var` by default. Configure alternative locations with environment variables:

- `APP_DATA_DIR` – root directory for local data (default: `var`)
- `APP_DATABASE_URL` – SQLAlchemy database URL (default: `sqlite:///var/app.db`)

### Running tests

```bash
pytest
```

### Available endpoints (initial skeleton)

- `GET /health` – service health probe
- `GET /content` – list installed course packages and indexed tasks
- `POST /content/import` – upload a course `.zip` archive, validate it against JSON schemas, and index its tasks
- `POST /content/scan` – rescan the content directory and refresh the database index

JSON schema definitions for course manifests and tasks live in `app/schemas/json/`.
