# Offline-First Python Course Platform Architecture

## 1. Vision and Goals

The goal is to deliver an offline-first desktop platform for Algorithmics-like schools that provides a complete Python curriculum with automatic evaluation, local student profiles, and subscription control. The application must operate for weeks without internet access while synchronizing progress, licenses, and content updates once a connection becomes available.

## 2. Target Personas and Key Scenarios

### Personas
- **Student** – Authenticates locally, studies theory, completes quizzes and coding tasks, and runs the judge offline.
- **Teacher** – Manages classes, monitors progress, imports/exports data, and installs content packs.
- **Franchise Owner / Methodologist** – Maintains licenses, distributes content packages, and ensures compliance.

### Core Scenarios
1. Student completes a lesson offline: theory → quiz → coding task → judge feedback.
2. Teacher adds a new task by placing a JSON file into `/tasks/` and triggering "Rescan Content".
3. Administrator installs a `course_xxx.zip` package from USB, validates the license, and activates new content without connectivity.
4. Synchronization pipeline sends progress to the cloud and pulls license/content updates when the network is restored.

## 3. Architecture Overview

### Recommended Stack (Variant A)
- **Shell:** Tauri (Rust) desktop container bundling a React/TypeScript UI.
- **UI:** React + TypeScript with local state management (Redux Toolkit) and offline storage (IndexedDB via Dexie).
- **Local API:** FastAPI (Python) exposed over `http://127.0.0.1:<port>` with JWT-based session tokens.
- **Database:** SQLite (WAL mode) stored under the application data directory; optional envelope encryption.
- **Judge:** Python execution sandbox with Docker/Podman when available, falling back to RestrictedPython + resource limits.
- **Support Services:**
  - Content Manager (zip import, schema validation, task registry caching).
  - Sync Engine (event sourcing queue with retry/backoff logic).
  - License Agent (Ed25519 signature verification, grace-period handling).

### Deployment Model
- Single installer (`.msi/.exe`) packages Tauri shell, UI assets, FastAPI backend, Python runtime, and sandbox tooling.
- Auto-update support with differential patches; manual offline update packages for schools without internet.

## 4. Content Model

### Package Layout
```
<course_root>/
  manifest.json
  theory/
    01_intro.md
    02_loops.md
  quizzes/
    quiz_01.json
  tasks/
    sum_two_numbers.json
    max_of_three.json
    factorial/
      task.json
      checker.py
      tests/
        public/
          01.in
          01.out
        private/
          02.in
          02.out
  assets/
    images/
```

### JSON Schemas
- `task.json` (declarative) – defines ID, title, description, tests (input/expected), checker type (`exact`, `strip`, `regex`, `python_expr`), limits, hints, and tags.
- `task.json` (folder/custom) – describes metadata for custom checker tasks; tests executed by `checker.py`.
- `manifest.json` – course metadata, versioning, localization, and minimum supported app version.
- `quiz_*.json` – quiz metadata, questions array (single-choice, multiple-choice, free-form).

FastAPI validates incoming content using JSON Schema Draft-07 during import or rescan. Validation errors are logged and surfaced in the UI for teacher review.

## 5. Local Data Storage

### Core Tables (SQLite)
- `users(id, role, display_name, local_auth_hash, last_login_at)`
- `classes(id, name)`
- `enrollments(user_id, class_id)`
- `content(id, version, title, installed_at, status)`
- `tasks(id, course_id, version, kind, json_path, folder_path)`
- `progress(user_id, content_id, lesson_id, percent, updated_at)`
- `submissions(id, user_id, task_id, verdict, runtime_ms, memory_kb, stdout, stderr, created_at)`
- `attempts(id, user_id, quiz_id, score, details_json, created_at)`
- `license(tenant_id, seats, valid_until, signature)`

Backups are exported as encrypted zip archives containing the SQLite database and content manifests.

## 6. Local API Surface (FastAPI)

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/auth/login` | Local authentication with Argon2 password check → JWT token |
| GET | `/content` | List installed content packages |
| POST | `/content/import` | Multipart zip upload (import course) |
| POST | `/content/scan` | Rescan content root, validate JSON, refresh cache |
| GET | `/tasks` | List tasks filtered by course/version |
| GET | `/tasks/{task_id}` | Return task details |
| POST | `/judge/{task_id}` | Execute student solution against sandbox |
| GET | `/progress/{user_id}` | Fetch aggregated progress |
| POST | `/submissions` | Persist verdict results |
| GET/POST | `/license`, `/license/activate` | Manage offline license tokens |
| POST | `/backup/export` | Produce backup zip |
| POST | `/backup/import` | Restore from backup |

All endpoints are exposed only on `localhost` and require JWT with role claims. Teacher/admin actions perform extra role checks.

## 7. Judge and Sandbox

### Execution Flow
1. Client submits `source` for a task ID.
2. API resolves task metadata and selects the execution mode:
   - **Declarative** – iterate over inline tests using sandboxed subprocess (Docker container or RestrictedPython) with per-test time/memory limits, comparing output using the configured checker strategy.
   - **Custom Checker** – load `checker.py` inside sandbox, provide a `run_solution` callback to execute the student's code against custom logic.
3. Collect verdict (`OK`, `WA`, `RE`, `TL`, etc.), per-test results, runtime, stdout/stderr truncated to safe limits (≤64KB).
4. Persist submission record and return structured response to the client.

### Security Measures
- Prefer Docker/Podman with `python:3.12-slim`, disabled networking, constrained CPU (`--cpus=0.5`), memory (`--memory=256m`), and PID limits.
- Fallback sandbox uses RestrictedPython, `resource.setrlimit`, `faulthandler`, and a guarded import whitelist.
- Output size, execution time, and memory are capped; file system access is blocked.

## 8. License Management

- License file: signed JSON `{tenant_id, seats, valid_until, features, license_version, signature}`.
- Signatures validated locally via embedded Ed25519 public key.
- Grace period (30 days) for offline operation after expiry if no connectivity.
- Device activation tracked via hardware fingerprint hashes; seat count enforces simultaneous device limit.
- License version monotonically increases to prevent replay.

## 9. Synchronization Strategy

- Event sourcing queue persists actions: `progress.updated`, `submission.created`, `attempt.created`.
- Background worker attempts sync with exponential backoff; conflicts resolved via last-write-wins by timestamp.
- Content and license updates pulled from cloud endpoints, verified before applying.
- Sync runs opportunistically; system must stay functional for ≥4 weeks offline.

## 10. Client Application (Tauri + React)

### Key Screens
- Login (PIN/QR/manual) with recent users list.
- Course catalog with offline availability indicators and progress bars.
- Lesson view: tabs for Theory (markdown renderer), Quiz (interactive forms), Coding Task (Monaco editor + run/check controls).
- Teacher dashboard: content import/scan, task validation status, class monitor, backup/export interface.

### Offline Considerations
- Local caching of theory assets and quizzes via IndexedDB.
- Autosave student code every 5 seconds; conflict resolution merges latest local version unless remote is newer.
- Light-weight UI theme optimized for low-spec PCs; optional animation toggle.

## 11. Performance Targets

- App startup < 3 seconds on typical school hardware.
- Single solution check < 2 seconds; batch check for 25 students < 1 minute.
- SQLite WAL ensures responsive writes; periodic vacuum/maintenance scheduled during idle periods.

## 12. Logging and Diagnostics

- Rotating `app.log` with INFO/WARN/ERROR levels.
- Content validation log capturing schema violations and warnings.
- Export diagnostics bundle (logs + system info + anonymized DB snapshot) for support.

## 13. Roadmap

1. **Pre-production (1–2 weeks)** – finalize requirements, UI mockups, content schema agreement.
2. **MVP (4–6 weeks)** – Tauri shell, React UI basics, FastAPI core, declarative judge, local users/classes, minimal reports.
3. **v0.9 (3–4 weeks)** – Docker sandbox support, content versioning, offline licensing, backup import/export.
4. **v1.0 (2–3 weeks)** – Cloud sync, teacher monitor, batch judging, installers & auto-updates.

## 14. Risk Mitigation

- Provide RestrictedPython fallback when Docker is unavailable.
- Implement aggressive autosave and backup workflows to avoid data loss.
- Supply content as external packages to satisfy licensing constraints.
- Maintain lightweight frontend and limit background processing for low-powered devices.

## 15. Acceptance Criteria for MVP

- Import course from zip, validate JSON, and render theory/quizzes/tasks offline.
- Students can author solutions, run local judge, and view test breakdowns.
- Teachers add new JSON tasks and see them after rescan without restarting the app.
- Backup/export and offline license validation operate without internet connectivity.
