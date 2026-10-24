# MEMORY.md: YT-DLP Web Downloader

## Project Purpose

A self-hosted web application providing a browser-based interface for downloading publicly accessible YouTube videos using yt-dlp. Built with Flask, SQLite, vanilla JS, and CSS.

## Technology Constraints

- Backend: Python 3.11+, Flask, yt-dlp Python API, FFmpeg, SQLite.
- Frontend: HTML5, CSS3, Vanilla JavaScript, Jinja2 templates.
- No React, Vue, Angular, Node.js, TypeScript, Tailwind, Bootstrap.
- No Redis, Celery, Docker.

## Current Implementation Status

### Phase 0: Documentation — DONE
- All six documentation files created with project-specific content.

### Phase 1: Scaffold & Configuration — DONE
- Full project structure in place with `.venv`, `requirements.txt`, `.env.example`, `.gitignore`, `README.md`.
- Database initialization with schema and indexes on startup.

### Phase 2: Backend & Downloader Service — DONE
- `downloader.py` complete with `DownloaderService`, URL validation, SSRF defense, worker pool (`ThreadPoolExecutor`), progress/postprocessor hooks, safe file serving, and background retention cleanup.

### Phase 3: Single-Download Workflow (API) — DONE
- `app.py` complete with all REST routes: `/api/health`, `/api/metadata`, `/api/downloads`, `/api/jobs`, `/api/jobs/<job_id>`, `/api/jobs/<job_id>/file`, `/api/jobs/<job_id>/retry`, `/api/batches`, `/api/batches/<batch_id>`.

### Phase 4: Bulk-Download Workflow — DONE
- Multi-URL batch parsing, duplicate URL removal, error aggregation, batch sizing limits, and sub-job status tracking.

### Phase 5: Frontend Integration — DONE
- Modern semantic HTML dashboard (`templates/index.html`), dark mode CSS design tokens with glassmorphism and responsiveness (`static/css/style.css`), vanilla JavaScript client with polling backoff and toast notifications (`static/js/app.js`).

### Phase 6: Security & Hardening — DONE
- Strict URL allowlisting for YouTube domains.
- SSRF prevention via DNS resolution and IP address classification (blocks private, loopback, link-local).
- Server-generated UUID filenames preventing path traversal (`../`).
- Rate limiting with Flask-Limiter (429 JSON response).
- Request size limit (1 MB).
- Error message sanitization preventing path/token leaks.
- Restart recovery (stale `RUNNING` jobs marked `FAILED`).

### Phase 7: Automated Testing — DONE
- 81 automated tests passing across `tests/test_app.py` and `tests/test_downloader.py`.
- 85% code coverage across `app.py` and `downloader.py`.

### Phase 8: Documentation & Release Readiness — DONE
- `README.md`, `ARCHITECTURE.md`, `DESIGN.md`, `ePRD.md`, `RULES.md`, `TRACKER.md`, `MEMORY.md` updated and synchronized with the codebase.

## Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| ThreadPoolExecutor for background jobs | Simple, no external broker dependency. Reliable for single-instance self-hosted deployment. |
| SQLite with WAL mode for persistence | Zero-config, single-file, thread-safe with WAL mode and busy timeout. |
| Polling with backoff for progress | Standard RESTful design, resilient against connection drops without WebSocket complexity. |
| Server-generated UUID filenames | Complete defense against path traversal and shell injection. |
| Quality presets instead of raw format codes | Prevents injection of arbitrary yt-dlp format strings, simplifies UX. |
| YouTube-only URL allowlist | Limits attack surface and focuses on intended scope. |

## Test Status

- Total Tests: 81
- Passed: 81 (100%)
- Code Coverage: 85% (app.py: 85%, downloader.py: 85%)

## Next Steps / Production Enhancements

- If deploying behind a reverse proxy (e.g., Nginx, Caddy), configure `ProxyFix` middleware.
- Optional user authentication (e.g., HTTP Basic Auth or session login) if hosted on a multi-user network.

## Bot-Detection Fix (Phase 9)

YouTube's bot-detection `"Sign in to confirm you're not a bot"` error was resolved by updating
`_apply_common_ydl_opts` in `downloader.py`:

1. **Player client upgrade**: Switched from `['android', 'web']` to `['tv', 'tv_simply', 'mweb']`.
   The `tv` (Smart TV) innertube client has priority=40 and is treated as a trusted first-party
   client by YouTube, rarely triggering bot challenges. `tv_simply` works without cookies. `mweb`
   covers mobile-web as a fallback.

2. **Automatic browser cookie extraction**: Added zero-config browser cookie detection. On startup,
   the app probes Chrome → Firefox → Edge → Brave and automatically uses the first available
   browser's YouTube session cookies. Controlled via `YTDL_COOKIES_BROWSER` env var
   (set to `none` to disable).

3. **Env vars documented** in `.env.example`: `YTDL_COOKIES_BROWSER`, `YTDL_COOKIES_PATH`,
   `YTDL_COOKIES_TEXT`.

