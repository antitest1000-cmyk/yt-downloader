# TRACKER.md: YT-DLP Web Downloader

## Phase 0: Repository Inspection & Specification

| ID | Task | Status | Files | Verification | Blocker |
|----|------|--------|-------|-------------|---------|
| P0-001 | Inspect existing repository | DONE | — | Empty directory confirmed | — |
| P0-002 | Create ePRD.md | DONE | ePRD.md | File exists with requirements | — |
| P0-003 | Create ARCHITECTURE.md | DONE | ARCHITECTURE.md | File exists with API contracts, schema | — |
| P0-004 | Create DESIGN.md | DONE | DESIGN.md | File exists with tokens, components | — |
| P0-005 | Create MEMORY.md | DONE | MEMORY.md | File exists with project context | — |
| P0-006 | Create RULES.md | DONE | RULES.md | File exists with 32 rules | — |
| P0-007 | Create TRACKER.md | DONE | TRACKER.md | This file | — |

## Phase 1: Project Scaffold & Configuration

| ID | Task | Status | Files | Verification | Blocker |
|----|------|--------|-------|-------------|---------|
| P1-001 | Create project directory structure | DONE | all | All folders and paths created | — |
| P1-002 | Create requirements.txt | DONE | requirements.txt | Deps installed cleanly in .venv | — |
| P1-003 | Create .env.example | DONE | .env.example | All 14 environment variables documented | — |
| P1-004 | Create .gitignore | DONE | .gitignore | Ignores virtualenvs, dbs, downloaded media | — |
| P1-005 | Implement config loading | DONE | app.py | Loads env vars with robust fallbacks | — |
| P1-006 | Implement DB initialization | DONE | app.py, downloader.py | Schema + indexes verified via SQLite | — |
| P1-007 | Create README.md | DONE | README.md | Complete guide with quickstart & API docs | — |
| P1-008 | Create initial test files | DONE | tests/ | pytest discovers and executes 81 tests | — |

## Phase 2: Backend & Downloader Service

| ID | Task | Status | Files | Verification | Blocker |
|----|------|--------|-------|-------------|---------|
| P2-001 | Implement URL validation | DONE | downloader.py | Accepts watch, shorts, playlist, youtu.be | — |
| P2-002 | Implement SSRF checks | DONE | downloader.py | Rejects private IPs, loopback, link-local | — |
| P2-003 | Implement yt-dlp integration | DONE | downloader.py | Safe templates, preset formats, error traps | — |
| P2-004 | Implement progress hooks | DONE | downloader.py | Captures speed, ETA, percent, bytes | — |
| P2-005 | Implement worker pool | DONE | downloader.py | ThreadPoolExecutor with bounded concurrency | — |
| P2-006 | Implement job state management | DONE | downloader.py | Full CRUD + status lifecycle in SQLite | — |
| P2-007 | Implement safe file storage | DONE | downloader.py | UUID-named local files prevent traversal | — |
| P2-008 | Implement metadata extraction | DONE | downloader.py | Fast extract_info without download | — |
| P2-009 | Implement batch/playlist handling | DONE | downloader.py | Multi-URL validation, deduplication, batching | — |
| P2-010 | Implement file cleanup | DONE | downloader.py | Background worker prunes files > retention | — |
| P2-011 | Implement FFmpeg detection | DONE | downloader.py | shutil.which reports status in health API | — |

## Phase 3: Single-Download Workflow (API)

| ID | Task | Status | Files | Verification | Blocker |
|----|------|--------|-------|-------------|---------|
| P3-001 | GET / — dashboard route | DONE | app.py | Returns HTML 200 with UI layout | — |
| P3-002 | GET /api/health | DONE | app.py | Returns JSON 200 with worker & ffmpeg stats | — |
| P3-003 | POST /api/metadata | DONE | app.py | Returns title, duration, thumbnail, formats | — |
| P3-004 | POST /api/downloads | DONE | app.py | Creates job, returns 202 Accepted | — |
| P3-005 | GET /api/jobs/<job_id> | DONE | app.py | Returns job status and progress object | — |
| P3-006 | GET /api/jobs/<job_id>/file | DONE | app.py | Serves file as attachment safely | — |
| P3-007 | POST /api/jobs/<job_id>/retry | DONE | app.py | Resets failed job, checks retry cap | — |
| P3-008 | POST /api/batches | DONE | app.py | Validates URLs, deduplicates, queues jobs | — |
| P3-009 | GET /api/batches/<batch_id> | DONE | app.py | Returns batch summary and sub-job states | — |

## Phase 4: Bulk-Download Workflow

| ID | Task | Status | Files | Verification | Blocker |
|----|------|--------|-------|-------------|---------|
| P4-001 | Bulk URL parsing and validation | DONE | app.py, downloader.py | Line-by-line validation reporting errors | — |
| P4-002 | Duplicate detection | DONE | downloader.py | Deduplicates identical URLs in batch | — |
| P4-003 | Batch size enforcement | DONE | app.py, downloader.py | Enforces MAX_BATCH_SIZE (413 if exceeded) | — |
| P4-004 | Per-item progress tracking | DONE | static/js/app.js | Individual cards track each batch item | — |
| P4-005 | Partial success handling | DONE | downloader.py | Failed items do not block valid siblings | — |

## Phase 5: Frontend Integration

| ID | Task | Status | Files | Verification | Blocker |
|----|------|--------|-------|-------------|---------|
| P5-001 | HTML dashboard layout | DONE | templates/index.html | Semantic HTML5 structure with ARIA roles | — |
| P5-002 | CSS design system | DONE | static/css/style.css | Dark mode tokens, glassmorphism, responsive | — |
| P5-003 | Single download UI | DONE | static/js/app.js | Form validation, format toggling, submission | — |
| P5-004 | Bulk download UI | DONE | static/js/app.js | Textarea validation summary counters | — |
| P5-005 | Job queue display | DONE | static/js/app.js | Live-updating cards with action buttons | — |
| P5-006 | Progress indicators | DONE | static/js/app.js | Smooth animated bars, ETA, speed display | — |
| P5-007 | Error display | DONE | static/js/app.js | Inline feedback + toast notifications | — |
| P5-008 | Download file serving | DONE | static/js/app.js | Direct download button triggers file download | — |
| P5-009 | Responsive design | DONE | static/css/style.css | Mobile, tablet, and desktop media queries | — |
| P5-010 | Accessibility | DONE | all frontend | Focus rings, ARIA live regions, labels | — |

## Phase 6: Security & Failure Handling

| ID | Task | Status | Files | Verification | Blocker |
|----|------|--------|-------|-------------|---------|
| P6-001 | SSRF defense review | DONE | downloader.py | getaddrinfo checked against ip_address rules | — |
| P6-002 | Path traversal defense | DONE | app.py, downloader.py | UUID files + abspath check in get_file_path | — |
| P6-003 | Rate limiting | DONE | app.py | Flask-Limiter returns 429 when threshold met | — |
| P6-004 | Request size limits | DONE | app.py | MAX_CONTENT_LENGTH configured and enforced | — |
| P6-005 | Concurrency limits | DONE | downloader.py | MAX_QUEUE_DEPTH and ThreadPool bounded | — |
| P6-006 | Restart recovery | DONE | downloader.py | RUNNING jobs marked FAILED on startup | — |
| P6-007 | Safe error messages | DONE | downloader.py, app.py | _sanitize_error strips paths and tokens | — |
| P6-008 | File access control | DONE | app.py | Only COMPLETED files within dir are served | — |

## Phase 7: Automated Testing

| ID | Task | Status | Files | Verification | Blocker |
|----|------|--------|-------|-------------|---------|
| P7-001 | Dashboard rendering test | DONE | tests/test_app.py | Verified 200 OK + UI elements present | — |
| P7-002 | URL validation tests | DONE | tests/test_downloader.py | Standard, short, shorts, playlist verified | — |
| P7-003 | SSRF rejection tests | DONE | tests/test_downloader.py | Loopback, private, link-local rejected | — |
| P7-004 | Job lifecycle tests | DONE | tests/test_downloader.py, tests/test_app.py | QUEUED -> RUNNING -> COMPLETED/FAILED | — |
| P7-005 | Batch/playlist tests | DONE | tests/test_downloader.py, tests/test_app.py | Deduplication, batch limits, mixed URLs | — |
| P7-006 | Error handling tests | DONE | tests/test_app.py | JSON 400, 404, 413, 429, no tracebacks | — |
| P7-007 | File serving tests | DONE | tests/test_app.py | 200 attachment, 404 missing, 409 queued | — |
| P7-008 | Retry tests | DONE | tests/test_app.py, tests/test_downloader.py | Retry counter, max retry rejection | — |
| P7-009 | Progress hook tests | DONE | tests/test_downloader.py | Bytes, speed, ETA, percent DB updates | — |
| P7-010 | Rate limit tests | DONE | tests/test_app.py | 429 received when limit exceeded | — |
| P7-011 | Cleanup tests | DONE | tests/test_downloader.py | Deletion of files & records > retention | — |

## Phase 8: Documentation Review & Release Readiness

| ID | Task | Status | Files | Verification | Blocker |
|----|------|--------|-------|-------------|---------|
| P8-001 | Verify all endpoints vs docs | DONE | ARCHITECTURE.md, README.md | Routes and JSON schemas match code | — |
| P8-002 | Verify setup instructions | DONE | README.md | Steps tested in .venv environment | — |
| P8-003 | Update all documentation | DONE | all .md files | Consistent with active implementation | — |
| P8-004 | Final test run | DONE | tests/ | 81/81 tests passing (85% coverage) | — |
| P8-005 | Final report | DONE | — | All deliverables implemented & verified | — |
