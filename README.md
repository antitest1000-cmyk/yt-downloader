# YT-DLP Web Downloader

A lightweight, robust, self-hosted web application for downloading publicly accessible YouTube videos and audio using the official open-source `yt-dlp` library.

Built with Python, Flask, SQLite, and vanilla modern JavaScript/CSS. No complex node build chains, external message queues, or heavy dependencies required.

---

## Features

- **Single & Bulk Downloads**: Download individual YouTube videos or paste multiple URLs (up to 20 by default) for batched queueing with automatic duplicate detection.
- **Playlist Extraction**: Support for YouTube playlists and playlist URLs with automated batch item generation.
- **Format & Quality Options**:
  - Video Presets: Best Available, 1080p, 720p, 480p.
  - Audio Extraction: Best Audio (M4A/WebM) or converted MP3 (requires FFmpeg).
- **Metadata Preview**: Instant video title, duration, uploader, thumbnail, and format inspection prior to downloading.
- **Real-Time Job Queue**: Live progress reporting (progress percentage, download speed, ETA, downloaded bytes) with non-blocking polling and exponential backoff.
- **Robust Failure & Retry Handling**: Automatic restart recovery (marks interrupted jobs as failed), safe error sanitization (no internal filepaths or secrets leaked to client), and single-click retry with maximum retry limits.
- **Safe File Storage & Serving**: Server-generated UUID-based storage filenames preventing path traversal attacks (`../`), served with sanitized user-friendly attachment names.
- **Automatic File Retention Cleanup**: Background worker periodically sweeps and removes downloaded media files and stale database records older than the configured retention threshold (default: 24 hours).
- **Security & SSRF Hardening**: Host allowlisting restricted to legitimate YouTube domains, local and private IP range resolution blocking (rejects RFC 1918, loopback, link-local metadata addresses), request body size limiting (1 MB default), and per-IP rate limiting (Flask-Limiter).

---

## Prerequisites

- **Python**: Version 3.11 or newer (tested with Python 3.14).
- **FFmpeg**: Required for media stream merging (video + audio) and MP3 conversion.
  - Windows: Download via [ffmpeg.org](https://ffmpeg.org/download.html) or `winget install Gyan.FFmpeg` / `choco install ffmpeg`.
  - Linux (Ubuntu/Debian): `sudo apt-get install -y ffmpeg`
  - macOS: `brew install ffmpeg`

---

## Quickstart

### 1. Clone & Navigate

```bash
cd yt-downloader
```

### 2. Set Up Virtual Environment

```bash
# Windows
python -m venv .venv
.\.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configuration

Copy the sample environment file and adjust settings as needed:

```bash
cp .env.example .env
```

Key environment options:

| Variable | Default | Description |
|---|---|---|
| `FLASK_ENV` | `development` | Flask runtime environment (`development`, `production`, `testing`) |
| `SECRET_KEY` | Auto-generated hex | Session and CSRF secret key |
| `DOWNLOAD_DIR` | `./downloads` | Path where downloaded files are saved |
| `DATABASE_PATH` | `./ytdl.db` | Path to SQLite database file |
| `MAX_CONCURRENT_DOWNLOADS` | `3` | Maximum concurrent active worker threads |
| `MAX_BATCH_SIZE` | `20` | Maximum URLs permitted per bulk download request |
| `MAX_PLAYLIST_ITEMS` | `50` | Maximum items extracted from a single playlist |
| `MAX_QUEUE_DEPTH` | `50` | Maximum pending jobs allowed in queue |
| `DOWNLOAD_TIMEOUT` | `1800` | yt-dlp process timeout in seconds (30 mins) |
| `FILE_RETENTION_HOURS` | `24` | Hours to retain completed files before auto-deletion |
| `RATE_LIMIT_PER_MINUTE` | `30` | Maximum HTTP requests per IP per minute |
| `FFMPEG_PATH` | `""` | Optional explicit path to `ffmpeg` binary |

### 5. Run the Application

```bash
python app.py
```

The application will start on `http://127.0.0.1:5000`.

---

## Running the Automated Test Suite

Execute the full automated test suite with pytest:

```bash
# Run all tests
python -m pytest tests/

# Run tests with code coverage report
python -m pytest tests/ --cov=app --cov=downloader --cov-report=term-missing
```

---

## API Reference

All API responses return standard JSON format:

```json
{
  "success": true,
  "data": { ... }
}
```

On error:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description"
  }
}
```

### Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Web dashboard UI |
| `GET` | `/api/health` | System health, worker statistics, and FFmpeg detection |
| `POST` | `/api/metadata` | Inspect video/playlist info without downloading (`{"url": "..."}`) |
| `POST` | `/api/downloads` | Submit single download job (`{"url": "...", "quality": "best", "format_type": "video"}`) |
| `POST` | `/api/batches` | Submit bulk batch (`{"urls": ["..."], "quality": "...", "format_type": "..."}`) |
| `GET` | `/api/jobs` | List recent download jobs (`?limit=50`) |
| `GET` | `/api/jobs/<job_id>` | Get job progress and status |
| `GET` | `/api/jobs/<job_id>/file` | Download the completed video or audio file |
| `POST` | `/api/jobs/<job_id>/retry` | Retry a failed download job |
| `GET` | `/api/batches/<batch_id>` | Get batch summary and constituent job statuses |

---

## Project Structure

```text
yt-downloader/
├── app.py                  # Flask HTTP application, routing, error handlers
├── downloader.py           # yt-dlp service, worker queue, SQLite persistence
├── requirements.txt        # Pinned dependencies
├── .env.example            # Sample configuration file
├── .gitignore              # Git ignore rules
├── templates/
│   └── index.html          # Semantic HTML5 dashboard interface
├── static/
│   ├── css/
│   │   └── style.css       # Design tokens, responsive styles, animations
│   └── js/
│       └── app.js          # Client-side UI logic, polling, API client
├── tests/
│   ├── test_app.py         # Route, validation, rate limiting, and serving tests
│   └── test_downloader.py  # Downloader, SSRF, hooks, worker, and cleanup tests
├── ARCHITECTURE.md         # Architecture blueprint & API contracts
├── DESIGN.md               # Visual design system specifications
├── ePRD.md                 # Product requirements document
├── MEMORY.md               # Project decisions and state memory
├── RULES.md                # 32 core non-negotiable rules
├── TRACKER.md              # Task and phase implementation tracker
└── README.md               # User & developer guide
```

---

## Legal & Acceptable Use Policy

1. **Legitimate Access Only**: This software is intended strictly for downloading publicly accessible media that you have the right to download for personal/archival use.
2. **No DRM Bypass**: This tool does NOT circumvent digital rights management (DRM), paywalls, encryption, geo-blocks, or private-access controls.
3. **Local Deployment**: This tool is designed for private, single-user/local network usage. Public internet deployments require additional authentication, strict egress proxying, and comprehensive access control.
