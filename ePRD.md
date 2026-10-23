# ePRD: YT-DLP Web Downloader

## 1. Product Purpose

A self-hosted web application that provides a clean browser interface for downloading publicly accessible YouTube videos using the yt-dlp open-source library. Intended for personal or small-team use on a local network or trusted environment.

### Target Users

- Technical users who want a browser-based interface for yt-dlp.
- Small teams needing a shared download station on a local network.
- Users who prefer a GUI over command-line yt-dlp.

## 2. MVP Scope

### In Scope

- Single-video downloads from YouTube with quality/format selection.
- Bulk downloads from a list of YouTube URLs (one per line).
- Playlist downloads with configurable item limits.
- Real-time progress tracking via yt-dlp hooks.
- Persistent job state in SQLite.
- Background download processing with bounded concurrency.
- Controlled file serving through application endpoints.
- Basic security controls (URL validation, SSRF prevention, path traversal prevention).

### Explicit Non-Goals

- User authentication or multi-user access control (documented as future work).
- Support for non-YouTube sites.
- DRM bypass, paywall circumvention, or private video access.
- Distributed workers, Redis, Celery, or Docker.
- Mobile-native applications.
- Video transcoding beyond what yt-dlp/FFmpeg provide natively.
- Streaming or playback within the application.
- Cloud storage integration.

## 3. Input Types

### 3.1 Single Video URL

A single YouTube video URL. Examples:
- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://www.youtube.com/shorts/VIDEO_ID`

### 3.2 Bulk URL List

Multiple YouTube video URLs provided as text, one URL per line. Each URL is validated individually. Duplicates are removed. This is NOT a playlist — it is a user-curated list of individual video URLs.

### 3.3 Playlist URL

A YouTube playlist URL such as `https://www.youtube.com/playlist?list=PLAYLIST_ID`. The application uses yt-dlp to enumerate playlist items, applies configured item limits, and creates individual jobs for each video.

**Key Distinction:** A bulk URL list is user-supplied and each URL is validated independently. A playlist URL is a single input that yt-dlp expands into multiple videos.

## 4. Supported Formats and Quality

### Video Qualities (Presets)

| Preset ID | Label | Description |
|-----------|-------|-------------|
| `best` | Best Available | Highest quality video+audio |
| `1080p` | 1080p | Up to 1080p video+audio |
| `720p` | 720p | Up to 720p video+audio |
| `480p` | 480p | Up to 480p video+audio |

### Audio-Only

| Preset ID | Label | Description |
|-----------|-------|-------------|
| `audio_best` | Best Audio | Best available audio (M4A/WebM) |
| `audio_mp3` | MP3 | Convert to MP3 (requires FFmpeg) |

### Notes

- Requested quality may not be available; yt-dlp selects the nearest match.
- Video+audio merging requires FFmpeg.
- MP3 conversion requires FFmpeg. Missing FFmpeg produces a clear error.

## 5. Job Lifecycle

```
QUEUED → RUNNING → COMPLETED
                 → FAILED
QUEUED → CANCELLED (future enhancement)
```

### States

| State | Description |
|-------|-------------|
| `QUEUED` | Job accepted, waiting for a worker |
| `RUNNING` | yt-dlp is actively downloading |
| `COMPLETED` | Download finished, file available |
| `FAILED` | Download failed, error recorded |
| `CANCELLED` | Job cancelled before completion (future) |

### Progress Data (when available)

- Percentage complete
- Downloaded bytes / total bytes
- Download speed
- ETA
- Current filename

When yt-dlp does not provide progress data, an indeterminate indicator is shown.

## 6. Functional Requirements

### Single Video Download

| ID | Requirement | Acceptance Criteria |
|----|-------------|-------------------|
| FR-001 | User can paste a YouTube video URL | URL input field accepts text, validates on submission |
| FR-002 | Server validates URL format and hostname | Invalid URLs return 400 with specific error message |
| FR-003 | User selects quality preset | Dropdown with predefined options, default is "best" |
| FR-004 | User selects video or audio-only mode | Toggle/selector for video vs audio output |
| FR-005 | Submission creates a background job | POST returns job ID and QUEUED status |
| FR-006 | User sees real-time progress | Polling returns percentage, speed, ETA when available |
| FR-007 | Completed job provides download link | Download button triggers controlled file endpoint |
| FR-008 | Failed job shows useful error | Error message is sanitized but informative |
| FR-009 | Metadata extraction before download | POST /api/metadata returns video title, duration, thumbnail |

### Bulk Download

| ID | Requirement | Acceptance Criteria |
|----|-------------|-------------------|
| FR-010 | User pastes multiple URLs (one per line) | Textarea accepts multi-line input |
| FR-011 | Each URL is validated individually | Per-line error reporting before submission |
| FR-012 | Duplicates are detected and removed | Count of duplicates shown to user |
| FR-013 | Valid/invalid/duplicate counts shown | Summary displayed before submission |
| FR-014 | Batch submission creates batch + jobs | POST returns batch_id and individual job_ids |
| FR-015 | Per-item progress tracking | Each job shows individual status |
| FR-016 | Partial success is handled | One failure does not cancel other jobs |
| FR-017 | Failed items can be retried | Retry button on failed items (within limits) |
| FR-018 | Batch size enforced | Configurable MAX_BATCH_SIZE, default 20 |

### Playlist Download

| ID | Requirement | Acceptance Criteria |
|----|-------------|-------------------|
| FR-019 | User pastes a playlist URL | Detected and handled distinctly from single video |
| FR-020 | Playlist items enumerated | Item count shown before download |
| FR-021 | Playlist item limit enforced | Configurable MAX_PLAYLIST_ITEMS, default 50 |
| FR-022 | Playlist creates a batch | Treated as batch with individual job tracking |

### Job Management

| ID | Requirement | Acceptance Criteria |
|----|-------------|-------------------|
| FR-023 | Job status queryable by ID | GET /api/jobs/<id> returns current state |
| FR-024 | Job state persisted in SQLite | Survives application restart |
| FR-025 | Completed files served safely | Only through /api/jobs/<id>/file with validation |
| FR-026 | Old files cleaned up | Configurable retention, never cleans active jobs |

### System

| ID | Requirement | Acceptance Criteria |
|----|-------------|-------------------|
| FR-027 | Health endpoint | GET /api/health returns status and FFmpeg availability |
| FR-028 | Dashboard renders | GET / returns the main page |

## 7. Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-001 | Response time for page load | < 2 seconds |
| NFR-002 | Concurrent download limit | Configurable, default 3 |
| NFR-003 | Queue depth limit | Configurable, default 50 |
| NFR-004 | Download timeout | Configurable, default 1800 seconds |
| NFR-005 | File retention | Configurable, default 24 hours |
| NFR-006 | Database | SQLite, single-file |
| NFR-007 | Accessibility | Semantic HTML, focus states, ARIA labels |
| NFR-008 | Responsive design | Usable on 320px–1920px viewports |
| NFR-009 | Browser support | Modern evergreen browsers |

## 8. Security Requirements

| ID | Requirement |
|----|-------------|
| SEC-001 | Server-side URL validation with hostname allowlist |
| SEC-002 | SSRF prevention: reject private IPs, loopback, local file URLs |
| SEC-003 | Path traversal prevention in file serving |
| SEC-004 | Request body size limits |
| SEC-005 | Rate limiting on download endpoints |
| SEC-006 | No user input in shell commands |
| SEC-007 | Sanitized error messages (no stack traces to client) |
| SEC-008 | Safe HTML rendering (escape user content) |
| SEC-009 | Restricted yt-dlp options (server-controlled) |
| SEC-010 | No arbitrary filesystem access |

## 9. Privacy

- No user tracking or analytics.
- No cookies beyond Flask session (if needed).
- No external API calls except to YouTube via yt-dlp.
- Job IDs are not equivalent to authentication tokens. Document this limitation.

## 10. MVP Limitations

- No user authentication. Job IDs provide access (documented risk).
- No HTTPS (user must configure reverse proxy for production).
- No distributed workers. Single-process with threading.
- No video preview or playback.
- YouTube only (no other extractors enabled).
- No resume of interrupted downloads across restarts (jobs reset to FAILED).
- No WebSocket push (polling-based progress).

## 11. Browser Storage & History Privacy

### Requirements
- **Permission-Gated Local History**: Video links and download history are only stored in the client's browser storage (cache / Chrome localStorage) if the user explicitly turns ON the permission toggle in the history section.
- **Privacy by Default**: By default, history storage is disabled. No past video links or download records are stored in browser storage.
- **Zero Popups / Modals**: Absolutely no popup dialogs, modal overlays, or browser alert prompts are shown. All controls, status indicators, and privacy notices reside strictly inside the History section.
- **User Agency**: The user manages permissions, item deletion, and history clearing directly from the History section toolbar.
- **Immediate Data Removal**: Turning off the storage toggle immediately wipes all stored video links and metadata from browser storage.

## 12. Future Enhancements

- User authentication and authorization for multi-user servers.
- WebSocket-based real-time progress.
- Job cancellation.
- Archive download for completed batches.
- Additional site support.
- Reverse proxy and HTTPS documentation.
- Storage quotas per user.

