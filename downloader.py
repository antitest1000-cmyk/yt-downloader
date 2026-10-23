"""
downloader.py — YT-DLP Download Service

Handles URL validation, yt-dlp integration, background job execution,
job state management, and file cleanup.
"""

import hashlib
import ipaddress
import logging
import os
import re
import shutil
import socket
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import yt_dlp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_STATUSES = {'QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'}

QUALITY_PRESETS = {
    'best': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
    '1080p': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]',
    '720p': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]',
    '480p': 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]',
    'audio_best': 'bestaudio/best',
    'audio_mp3': 'bestaudio/best',
}

ALLOWED_QUALITIES = set(QUALITY_PRESETS.keys())

ALLOWED_FORMAT_TYPES = {'video', 'audio'}

# YouTube hostname allowlist
ALLOWED_HOSTS = {
    'www.youtube.com',
    'youtube.com',
    'm.youtube.com',
    'youtu.be',
    'www.youtube-nocookie.com',
    'music.youtube.com',
}

# URL patterns for YouTube
YOUTUBE_VIDEO_PATTERN = re.compile(
    r'^https://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?|shorts/|embed/|v/)|youtu\.be/)'
)
YOUTUBE_PLAYLIST_PATTERN = re.compile(
    r'^https://(?:www\.|m\.)?youtube\.com/playlist\?list='
)

# ---------------------------------------------------------------------------
# Database Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    batch_id TEXT,
    url TEXT NOT NULL,
    title TEXT,
    thumbnail TEXT,
    status TEXT NOT NULL DEFAULT 'QUEUED',
    quality TEXT NOT NULL DEFAULT 'best',
    format_type TEXT NOT NULL DEFAULT 'video',
    progress_percent REAL,
    downloaded_bytes INTEGER,
    total_bytes INTEGER,
    speed REAL,
    eta REAL,
    filename TEXT,
    file_size INTEGER,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (batch_id) REFERENCES batches(id)
);

CREATE TABLE IF NOT EXISTS batches (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'QUEUED',
    total_items INTEGER NOT NULL,
    quality TEXT NOT NULL DEFAULT 'best',
    format_type TEXT NOT NULL DEFAULT 'video',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_batch_id ON jobs(batch_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
"""

# ---------------------------------------------------------------------------
# URL Validation
# ---------------------------------------------------------------------------


def validate_url(url: str) -> dict:
    """
    Validate a URL against the YouTube allowlist and SSRF rules.

    Returns:
        dict with keys:
            valid (bool): Whether the URL is valid.
            error (str|None): Error message if invalid.
            url_type (str|None): 'video' or 'playlist' if valid.
            normalized (str|None): Normalized URL if valid.
    """
    if not url or not isinstance(url, str):
        return {'valid': False, 'error': 'URL is required.', 'url_type': None, 'normalized': None}

    url = url.strip()

    if len(url) > 2048:
        return {'valid': False, 'error': 'URL is too long.', 'url_type': None, 'normalized': None}

    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception:
        return {'valid': False, 'error': 'Invalid URL format.', 'url_type': None, 'normalized': None}

    # Scheme check
    if parsed.scheme not in ('https', 'http'):
        return {'valid': False, 'error': 'Only HTTPS URLs are supported.', 'url_type': None, 'normalized': None}

    # Force HTTPS
    if parsed.scheme == 'http':
        url = 'https' + url[4:]
        parsed = urlparse(url)

    # Hostname check
    hostname = parsed.hostname
    if not hostname:
        return {'valid': False, 'error': 'Invalid URL: no hostname.', 'url_type': None, 'normalized': None}

    if hostname not in ALLOWED_HOSTS:
        return {'valid': False, 'error': f'Unsupported host: {hostname}. Only YouTube URLs are supported.', 'url_type': None, 'normalized': None}

    # SSRF: resolve and check IP
    try:
        resolved_ips = socket.getaddrinfo(hostname, None)
        for family, stype, proto, canonname, sockaddr in resolved_ips:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return {'valid': False, 'error': 'URL resolves to a restricted network address.', 'url_type': None, 'normalized': None}
    except socket.gaierror:
        return {'valid': False, 'error': 'Could not resolve hostname.', 'url_type': None, 'normalized': None}

    # Determine URL type
    qs = parse_qs(parsed.query)
    playlist_id = qs.get('list', [None])[0]
    is_mix = bool(playlist_id and (playlist_id.startswith('RD') or playlist_id in ('LL', 'WL', 'LM')))
    has_playlist = bool(playlist_id and not is_mix)

    if YOUTUBE_PLAYLIST_PATTERN.match(url) or ('list' in qs and 'v' not in qs):
        url_type = 'playlist'
    elif YOUTUBE_VIDEO_PATTERN.match(url):
        url_type = 'video'
    else:
        if 'v' in qs or parsed.hostname == 'youtu.be':
            url_type = 'video'
        else:
            return {'valid': False, 'error': 'URL does not match a supported YouTube video or playlist pattern.', 'url_type': None, 'normalized': None, 'has_playlist': False, 'playlist_id': None, 'is_mix': False}

    return {
        'valid': True,
        'error': None,
        'url_type': url_type,
        'normalized': url,
        'has_playlist': has_playlist,
        'playlist_id': playlist_id,
        'is_mix': is_mix,
    }


def validate_quality(quality: str) -> bool:
    """Check if quality preset is in the allowlist."""
    return quality in ALLOWED_QUALITIES


def validate_format_type(format_type: str) -> bool:
    """Check if format type is allowed."""
    return format_type in ALLOWED_FORMAT_TYPES


# ---------------------------------------------------------------------------
# Database Helpers
# ---------------------------------------------------------------------------

_db_local = threading.local()
_db_write_lock = threading.Lock()


def get_db(db_path: str) -> sqlite3.Connection:
    """Get a thread-local SQLite connection with autocommit."""
    if not hasattr(_db_local, 'connections'):
        _db_local.connections = {}

    if db_path not in _db_local.connections:
        conn = sqlite3.connect(db_path, timeout=60.0, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=60000")
        conn.execute("PRAGMA synchronous=NORMAL")
        _db_local.connections[db_path] = conn

    return _db_local.connections[db_path]


def init_db(db_path: str):
    """Initialize the database schema and apply migrations."""
    with _db_write_lock:
        conn = sqlite3.connect(db_path, timeout=60.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=60000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(SCHEMA_SQL)
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN thumbnail TEXT")
        except sqlite3.OperationalError:
            pass
        conn.close()
        logger.info("Database initialized at %s", db_path)


_YOUTUBE_ID_REGEX = re.compile(r'(?:v=|youtu\.be/|shorts/|embed/)([a-zA-Z0-9_-]{11})')


def get_youtube_thumbnail(url: str) -> str | None:
    """Derive default thumbnail URL from YouTube URL if possible."""
    if not url:
        return None
    m = _YOUTUBE_ID_REGEX.search(url)
    if m:
        return f"https://i.ytimg.com/vi/{m.group(1)}/mqdefault.jpg"
    return None


def _now() -> str:
    """Current UTC timestamp in ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# FFmpeg Detection
# ---------------------------------------------------------------------------

def check_ffmpeg(ffmpeg_path: str = None) -> bool:
    """Check if FFmpeg is available."""
    cmd = ffmpeg_path if ffmpeg_path else 'ffmpeg'
    if shutil.which(cmd) is not None:
        return True
    if ffmpeg_path and os.path.isfile(ffmpeg_path):
        return True
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Downloader Service
# ---------------------------------------------------------------------------

class DownloaderService:
    """Manages downloads, jobs, batches, and background workers."""

    def __init__(self, config: dict):
        self.download_dir = os.path.abspath(config.get('DOWNLOAD_DIR', './downloads'))
        self.db_path = config.get('DATABASE_PATH', './ytdl.db')
        self.max_concurrent = int(config.get('MAX_CONCURRENT_DOWNLOADS', 3))
        self.max_batch_size = int(config.get('MAX_BATCH_SIZE', 20))
        self.max_playlist_items = int(config.get('MAX_PLAYLIST_ITEMS', 50))
        self.max_queue_depth = int(config.get('MAX_QUEUE_DEPTH', 50))
        self.download_timeout = int(config.get('DOWNLOAD_TIMEOUT', 1800))
        self.file_retention_hours = int(config.get('FILE_RETENTION_HOURS', 24))
        self.max_retries = int(config.get('MAX_RETRIES', 3))
        self.ffmpeg_path = config.get('FFMPEG_PATH', None)
        if not self.ffmpeg_path:
            try:
                import imageio_ffmpeg
                exe = imageio_ffmpeg.get_ffmpeg_exe()
                if exe and os.path.isfile(exe):
                    self.ffmpeg_path = exe
            except Exception:
                pass
        self.ffmpeg_available = check_ffmpeg(self.ffmpeg_path)

        # Ensure download directory exists
        os.makedirs(self.download_dir, exist_ok=True)

        # Initialize database
        init_db(self.db_path)

        # Reset stale RUNNING jobs on startup
        self._recover_stale_jobs()

        # Worker pool
        self._executor = ThreadPoolExecutor(max_workers=self.max_concurrent, thread_name_prefix='dl-worker')
        self._lock = threading.Lock()

        # Cleanup thread
        self._cleanup_event = threading.Event()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True, name='cleanup-worker')
        self._cleanup_thread.start()

        logger.info("DownloaderService initialized. FFmpeg: %s, Workers: %d",
                     self.ffmpeg_available, self.max_concurrent)

    def shutdown(self):
        """Gracefully shut down workers and cleanup thread."""
        self._cleanup_event.set()
        self._executor.shutdown(wait=False, cancel_futures=True)
        if hasattr(self, '_cleanup_thread') and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=2.0)
        logger.info("DownloaderService shut down.")

    # -----------------------------------------------------------------------
    # Job Recovery
    # -----------------------------------------------------------------------

    def _recover_stale_jobs(self):
        """Reset jobs stuck in RUNNING state (from crash/restart)."""
        with _db_write_lock:
            conn = get_db(self.db_path)
            now = _now()
            try:
                cursor = conn.execute(
                    "UPDATE jobs SET status = 'FAILED', error_message = 'Job interrupted by server restart.', updated_at = ? WHERE status = 'RUNNING'",
                    (now,)
                )
                if cursor.rowcount > 0:
                    logger.warning("Recovered %d stale RUNNING jobs.", cursor.rowcount)
            except Exception as e:
                logger.error("Error recovering stale jobs: %s", e)

    # -----------------------------------------------------------------------
    # Queue Depth
    # -----------------------------------------------------------------------

    def _get_queue_depth(self) -> int:
        """Count active (QUEUED + RUNNING) jobs."""
        conn = get_db(self.db_path)
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM jobs WHERE status IN ('QUEUED', 'RUNNING')"
        ).fetchone()
        return row['cnt'] if row else 0

    def _check_queue_capacity(self, count: int = 1):
        """Raise if adding count jobs would exceed queue depth."""
        current = self._get_queue_depth()
        if current + count > self.max_queue_depth:
            raise QueueFullError(
                f"Queue is full. {current} active jobs, limit is {self.max_queue_depth}."
            )

    # -----------------------------------------------------------------------
    # Job CRUD
    # -----------------------------------------------------------------------

    def create_job(self, url: str, quality: str = 'best', format_type: str = 'video',
                   batch_id: str = None, title: str = None, thumbnail: str = None) -> dict:
        """Create a new download job and submit it to the worker pool."""
        # Validate
        val = validate_url(url)
        if not val['valid']:
            raise InvalidURLError(val['error'])

        if not validate_quality(quality):
            raise InvalidOptionError(f"Invalid quality: {quality}")

        if not validate_format_type(format_type):
            raise InvalidOptionError(f"Invalid format type: {format_type}")

        # Audio format validation
        if format_type == 'audio':
            if quality not in ('audio_best', 'audio_mp3'):
                # Normalize 'best' or video qualities to audio_best
                quality = 'audio_best'
        elif quality.startswith('audio_'):
            format_type = 'audio'

        # FFmpeg-required checks
        if quality == 'audio_mp3' and not self.ffmpeg_available:
            raise FFmpegMissingError("MP3 conversion requires FFmpeg, which is not installed.")
        if quality == 'audio_best' and not self.ffmpeg_available:
            raise FFmpegMissingError("Audio extraction requires FFmpeg, which is not installed.")

        # Queue check
        self._check_queue_capacity()

        # Derive initial thumbnail if not supplied
        if not thumbnail:
            thumbnail = get_youtube_thumbnail(val['normalized'])

        job_id = str(uuid.uuid4())
        now = _now()

        with _db_write_lock:
            conn = get_db(self.db_path)
            conn.execute(
                """INSERT INTO jobs (id, batch_id, url, title, thumbnail, status, quality, format_type, retry_count, max_retries, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'QUEUED', ?, ?, 0, ?, ?, ?)""",
                (job_id, batch_id, val['normalized'], title, thumbnail, quality, format_type, self.max_retries, now, now)
            )

        # Submit to worker pool
        self._executor.submit(self._download_task, job_id)

        logger.info("Created job %s for %s [%s/%s]", job_id, val['normalized'], quality, format_type)

        return {
            'job_id': job_id,
            'status': 'QUEUED',
            'url': val['normalized'],
            'title': title,
            'thumbnail': thumbnail,
            'quality': quality,
            'format_type': format_type,
        }

    def get_job(self, job_id: str) -> dict | None:
        """Get job data by ID."""
        conn = get_db(self.db_path)
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_all_jobs(self, limit: int = 100) -> list:
        """Get recent jobs."""
        conn = get_db(self.db_path)
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_jobs_by_ids(self, job_ids: list) -> list:
        """Get jobs matching a specific list of IDs."""
        if not job_ids:
            return []
        conn = get_db(self.db_path)
        placeholders = ','.join(['?'] * len(job_ids))
        rows = conn.execute(
            f"SELECT * FROM jobs WHERE id IN ({placeholders}) ORDER BY created_at DESC",
            tuple(job_ids)
        ).fetchall()
        return [dict(r) for r in rows]

    def retry_job(self, job_id: str) -> dict:
        """Retry a failed job."""
        job = self.get_job(job_id)
        if job is None:
            raise JobNotFoundError(f"Job {job_id} not found.")
        if job['status'] != 'FAILED':
            raise InvalidStateError(f"Only FAILED jobs can be retried. Current status: {job['status']}")
        if job['retry_count'] >= job['max_retries']:
            raise RetryLimitError(f"Job has reached the maximum retry limit ({job['max_retries']}).")

        self._check_queue_capacity()

        now = _now()
        with _db_write_lock:
            conn = get_db(self.db_path)
            conn.execute(
                """UPDATE jobs SET status = 'QUEUED', error_message = NULL, progress_percent = NULL,
                   downloaded_bytes = NULL, total_bytes = NULL, speed = NULL, eta = NULL,
                   retry_count = retry_count + 1, updated_at = ?
                   WHERE id = ?""",
                (now, job_id)
            )

        self._executor.submit(self._download_task, job_id)

        logger.info("Retrying job %s (attempt %d)", job_id, job['retry_count'] + 1)
        return {'job_id': job_id, 'status': 'QUEUED'}

    # -----------------------------------------------------------------------
    # Batch Operations
    # -----------------------------------------------------------------------

    def create_batch(self, urls: list, quality: str = 'best', format_type: str = 'video',
                     max_size: int = None) -> dict:
        """Create a batch of download jobs."""
        if not urls or not isinstance(urls, list):
            raise InvalidOptionError("URLs list is required.")

        limit = max_size if max_size is not None else self.max_batch_size
        if len(urls) > limit:
            raise BatchTooLargeError(
                f"Batch size {len(urls)} exceeds limit of {limit}."
            )

        if not validate_quality(quality):
            raise InvalidOptionError(f"Invalid quality: {quality}")

        if not validate_format_type(format_type):
            raise InvalidOptionError(f"Invalid format type: {format_type}")

        # Validate and deduplicate
        valid_items = []
        errors = []
        seen = set()
        duplicates = 0

        for i, item in enumerate(urls):
            if isinstance(item, dict):
                raw_url = str(item.get('url', '')).strip()
                item_title = item.get('title')
                item_thumb = item.get('thumbnail')
            else:
                raw_url = str(item).strip()
                item_title = None
                item_thumb = None

            if not raw_url:
                continue

            val = validate_url(raw_url)
            if not val['valid']:
                errors.append({'line': i + 1, 'url': raw_url[:200], 'error': val['error']})
                continue

            normalized = val['normalized']
            if normalized in seen:
                duplicates += 1
                continue

            seen.add(normalized)
            valid_items.append({
                'url': normalized,
                'title': item_title,
                'thumbnail': item_thumb or get_youtube_thumbnail(normalized),
            })

        if not valid_items:
            raise InvalidURLError("No valid URLs found in the batch.")

        # Queue check for entire batch
        self._check_queue_capacity(len(valid_items))

        batch_id = str(uuid.uuid4())
        now = _now()

        # Create batch record
        with _db_write_lock:
            conn = get_db(self.db_path)
            conn.execute(
                """INSERT INTO batches (id, status, total_items, quality, format_type, created_at, updated_at)
                   VALUES (?, 'QUEUED', ?, ?, ?, ?, ?)""",
                (batch_id, len(valid_items), quality, format_type, now, now)
            )

        # Create individual jobs
        jobs = []
        for v in valid_items:
            try:
                job_data = self.create_job(
                    v['url'], quality, format_type, batch_id=batch_id,
                    title=v['title'], thumbnail=v['thumbnail']
                )
                jobs.append(job_data)
            except Exception as e:
                errors.append({'url': v['url'][:200], 'error': str(e)})

        # Update batch status
        if jobs:
            with _db_write_lock:
                conn = get_db(self.db_path)
                conn.execute(
                    "UPDATE batches SET status = 'RUNNING', updated_at = ? WHERE id = ?",
                    (_now(), batch_id)
                )

        return {
            'batch_id': batch_id,
            'jobs': jobs,
            'total': len(jobs),
            'errors': errors,
            'duplicates_removed': duplicates,
        }

    def get_batch(self, batch_id: str) -> dict | None:
        """Get batch data with job summaries."""
        conn = get_db(self.db_path)
        batch_row = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
        if batch_row is None:
            return None

        batch = dict(batch_row)

        jobs = conn.execute(
            "SELECT * FROM jobs WHERE batch_id = ? ORDER BY created_at ASC", (batch_id,)
        ).fetchall()
        jobs_list = [dict(j) for j in jobs]

        # Compute status counts
        status_counts = {'QUEUED': 0, 'RUNNING': 0, 'COMPLETED': 0, 'FAILED': 0, 'CANCELLED': 0}
        for j in jobs_list:
            status_counts[j['status']] = status_counts.get(j['status'], 0) + 1

        batch['jobs'] = jobs_list
        batch['completed'] = status_counts['COMPLETED']
        batch['failed'] = status_counts['FAILED']
        batch['running'] = status_counts['RUNNING']
        batch['queued'] = status_counts['QUEUED']

        # Update batch status
        if status_counts['QUEUED'] == 0 and status_counts['RUNNING'] == 0:
            new_status = 'COMPLETED' if status_counts['FAILED'] == 0 else 'FAILED'
            if batch['status'] != new_status:
                conn.execute(
                    "UPDATE batches SET status = ?, updated_at = ? WHERE id = ?",
                    (new_status, _now(), batch_id)
                )
                conn.commit()
                batch['status'] = new_status

        return batch

    def _apply_common_ydl_opts(self, ydl_opts: dict):
        """Add android client fallback and optional cookies to reduce bot checks in cloud environments."""
        ydl_opts.setdefault('extractor_args', {})
        ydl_opts['extractor_args']['youtube'] = {
            'player_client': ['android', 'web']
        }
        cookie_path = os.getenv('YTDL_COOKIES_PATH')
        cookie_text = os.getenv('YTDL_COOKIES_TEXT')
        if cookie_path and os.path.isfile(cookie_path):
            ydl_opts['cookiefile'] = cookie_path
        elif cookie_text:
            tmp_cookies = os.path.join(self.download_dir, 'cookies.txt')
            try:
                if not os.path.exists(tmp_cookies):
                    with open(tmp_cookies, 'w', encoding='utf-8') as f:
                        f.write(cookie_text)
                ydl_opts['cookiefile'] = tmp_cookies
            except Exception as e:
                logger.warning("Could not write cookies.txt: %s", e)

    # -----------------------------------------------------------------------
    # Playlist Handling
    # -----------------------------------------------------------------------

    def extract_playlist(self, url: str) -> dict:
        """Extract playlist info without downloading."""
        val = validate_url(url)
        if not val['valid']:
            raise InvalidURLError(val['error'])

        if val.get('is_mix'):
            raise InvalidOptionError("YouTube Mix playlists (RD...) are auto-generated dynamic queues and cannot be downloaded as full playlists. You can download individual songs/videos instead.")

        target_url = val['normalized']
        if val.get('playlist_id'):
            target_url = f"https://www.youtube.com/playlist?list={val['playlist_id']}"

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'playlistend': self.max_playlist_items,
            'ignoreerrors': True,
            'allowed_extractors': ['youtube', 'youtube:tab', 'youtube:playlist'],
        }
        self._apply_common_ydl_opts(ydl_opts)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_url, download=False)
                if info is None:
                    raise DownloadError("Could not extract playlist information. The playlist may be unviewable, private, or deleted.")

                entries = info.get('entries', [])
                items = []
                for entry in entries:
                    if entry is None:
                        continue
                    entry_id = entry.get('id')
                    video_url = entry.get('url') or entry.get('webpage_url')
                    if not video_url and entry_id:
                        video_url = f"https://www.youtube.com/watch?v={entry_id}"
                    if video_url:
                        # Ensure full URL
                        if not video_url.startswith('http'):
                            video_url = f"https://www.youtube.com/watch?v={entry_id or video_url}"
                        entry_thumb = entry.get('thumbnail') or (f"https://i.ytimg.com/vi/{entry_id}/mqdefault.jpg" if entry_id else get_youtube_thumbnail(video_url))
                        items.append({
                            'url': video_url,
                            'title': entry.get('title', 'Unknown'),
                            'duration': entry.get('duration'),
                            'thumbnail': entry_thumb,
                        })

                return {
                    'title': info.get('title', 'Unknown Playlist'),
                    'uploader': info.get('uploader', 'Unknown'),
                    'item_count': len(items),
                    'items': items[:self.max_playlist_items],
                    'truncated': len(entries) > self.max_playlist_items,
                }
        except yt_dlp.utils.DownloadError as e:
            raw_err = str(e)
            if "unviewable" in raw_err.lower():
                raise DownloadError("YouTube reported this playlist type is unviewable or private.")
            raise DownloadError(f"Could not extract playlist: {_sanitize_error(raw_err)}")
        except Exception as e:
            logger.error("Playlist extraction error: %s", e)
            if isinstance(e, DownloaderError):
                raise
            raise DownloadError("An unexpected error occurred during playlist extraction.")

    # -----------------------------------------------------------------------
    # Metadata Extraction
    # -----------------------------------------------------------------------

    def extract_metadata(self, url: str) -> dict:
        """Extract video metadata without downloading."""
        val = validate_url(url)
        if not val['valid']:
            raise InvalidURLError(val['error'])

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'noplaylist': True,
            'socket_timeout': 30,
            'allowed_extractors': ['youtube', 'youtube:tab', 'youtube:playlist'],
        }
        self._apply_common_ydl_opts(ydl_opts)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(val['normalized'], download=False)
                if info is None:
                    raise DownloadError("Could not extract video information.")

                # Determine available qualities
                formats_available = ['best']
                if info.get('formats'):
                    heights = set()
                    for f in info['formats']:
                        h = f.get('height')
                        if h:
                            heights.add(h)
                    if any(h >= 1080 for h in heights):
                        formats_available.append('1080p')
                    if any(h >= 720 for h in heights):
                        formats_available.append('720p')
                    if any(h >= 480 for h in heights):
                        formats_available.append('480p')
                formats_available.extend(['audio_best', 'audio_mp3'])

                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration'),
                    'thumbnail': info.get('thumbnail'),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count'),
                    'upload_date': info.get('upload_date'),
                    'formats_available': formats_available,
                    'url_type': val['url_type'],
                    'has_playlist': val.get('has_playlist', False),
                    'playlist_id': val.get('playlist_id'),
                }

        except yt_dlp.utils.DownloadError as e:
            raise DownloadError(f"Could not extract metadata: {_sanitize_error(str(e))}")
        except Exception as e:
            logger.error("Metadata extraction error: %s", e)
            raise DownloadError("An unexpected error occurred during metadata extraction.")

    # -----------------------------------------------------------------------
    # Download Task (runs in worker thread)
    # -----------------------------------------------------------------------

    def _download_task(self, job_id: str):
        """Execute a download job. Runs in a worker thread."""
        conn = get_db(self.db_path)
        now = _now()

        try:
            # Mark as RUNNING
            with _db_write_lock:
                conn = get_db(self.db_path)
                conn.execute(
                    "UPDATE jobs SET status = 'RUNNING', updated_at = ? WHERE id = ?",
                    (now, job_id)
                )

            job = dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
            url = job['url']
            quality = job['quality']
            format_type = job['format_type']

            # Build yt-dlp options
            format_selector = QUALITY_PRESETS.get(quality, QUALITY_PRESETS['best'])

            # Generate safe filename
            safe_name = f"{job_id}"
            output_template = os.path.join(self.download_dir, f"{safe_name}.%(ext)s")

            ydl_opts = {
                'format': format_selector,
                'outtmpl': output_template,
                'quiet': True,
                'no_warnings': True,
                'noprogress': True,
                'noplaylist': True,
                'socket_timeout': 30,
                'retries': 3,
                'fragment_retries': 3,
                'allowed_extractors': ['youtube', 'youtube:tab', 'youtube:playlist'],
                'progress_hooks': [lambda d: self._progress_hook(job_id, d)],
                'postprocessor_hooks': [lambda d: self._postprocessor_hook(job_id, d)],
            }
            self._apply_common_ydl_opts(ydl_opts)

            # FFmpeg options — pass the full exe path so yt-dlp resolves the
            # versioned binary (e.g. ffmpeg-win-x86_64-v7.1.exe from imageio_ffmpeg).
            # yt-dlp's _determine_executables detects 'ffmpeg' in the filename and
            # sets paths['ffmpeg'] = location correctly.
            if self.ffmpeg_path:
                ydl_opts['ffmpeg_location'] = self.ffmpeg_path

            # Audio-specific options (both require FFmpeg — already validated above)
            if format_type == 'audio' or quality.startswith('audio_'):
                if quality == 'audio_mp3':
                    ydl_opts['postprocessors'] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }]
                else:
                    ydl_opts['postprocessors'] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'best',
                    }]

            # Download
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise DownloadError("Download returned no information.")

                title = info.get('title', 'Unknown')

                # Find the actual output file
                output_file = None
                # Check for the expected filename patterns
                for ext in ['mp4', 'mkv', 'webm', 'mp3', 'm4a', 'ogg', 'opus', 'flac', 'wav']:
                    candidate = os.path.join(self.download_dir, f"{safe_name}.{ext}")
                    if os.path.isfile(candidate):
                        output_file = candidate
                        break

                if output_file is None:
                    # Try to find any file starting with the job ID
                    for fname in os.listdir(self.download_dir):
                        if fname.startswith(safe_name):
                            output_file = os.path.join(self.download_dir, fname)
                            break

                if output_file is None:
                    raise DownloadError("Download completed but output file was not found.")

                filename = os.path.basename(output_file)
                file_size = os.path.getsize(output_file)

                thumbnail = info.get('thumbnail') or get_youtube_thumbnail(url)

                # Mark completed
                with _db_write_lock:
                    conn = get_db(self.db_path)
                    conn.execute(
                        """UPDATE jobs SET status = 'COMPLETED', title = ?, thumbnail = COALESCE(?, thumbnail),
                           filename = ?, file_size = ?, progress_percent = 100, updated_at = ? WHERE id = ?""",
                        (title, thumbnail, filename, file_size, _now(), job_id)
                    )

                logger.info("Job %s completed: %s (%d bytes)", job_id, filename, file_size)

        except Exception as e:
            error_msg = _sanitize_error(str(e))
            logger.error("Job %s failed: %s", job_id, error_msg)
            try:
                with _db_write_lock:
                    conn = get_db(self.db_path)
                    conn.execute(
                        "UPDATE jobs SET status = 'FAILED', error_message = ?, updated_at = ? WHERE id = ?",
                        (error_msg, _now(), job_id)
                    )
            except Exception as db_err:
                logger.error("Failed to update job %s status: %s", job_id, db_err)

        # Update batch status if this job belongs to a batch
        try:
            job = dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
            if job.get('batch_id'):
                self._update_batch_status(job['batch_id'])
        except Exception as e:
            logger.error("Error updating batch status: %s", e)

    def _progress_hook(self, job_id: str, data: dict):
        """Called by yt-dlp during download with progress data."""
        status = data.get('status')
        if status != 'downloading':
            return

        try:
            conn = get_db(self.db_path)

            downloaded = data.get('downloaded_bytes')
            total = data.get('total_bytes') or data.get('total_bytes_estimate')
            speed = data.get('speed')
            eta = data.get('eta')

            percent = None
            if downloaded and total and total > 0:
                percent = round((downloaded / total) * 100, 1)

            with _db_write_lock:
                conn = get_db(self.db_path)
                conn.execute(
                    """UPDATE jobs SET progress_percent = ?, downloaded_bytes = ?, total_bytes = ?,
                       speed = ?, eta = ?, updated_at = ? WHERE id = ?""",
                    (percent, downloaded, total, speed, eta, _now(), job_id)
                )
        except Exception as e:
            logger.debug("Progress hook error for %s: %s", job_id, e)

    def _postprocessor_hook(self, job_id: str, data: dict):
        """Called by yt-dlp during post-processing."""
        status = data.get('status')
        if status == 'started':
            try:
                with _db_write_lock:
                    conn = get_db(self.db_path)
                    conn.execute(
                        "UPDATE jobs SET progress_percent = NULL, updated_at = ? WHERE id = ?",
                        (_now(), job_id)
                    )
            except Exception:
                pass

    def _update_batch_status(self, batch_id: str):
        """Update batch status based on its jobs."""
        conn = get_db(self.db_path)
        rows = conn.execute(
            "SELECT status FROM jobs WHERE batch_id = ?", (batch_id,)
        ).fetchall()

        statuses = [r['status'] for r in rows]
        if not statuses:
            return

        if all(s in ('COMPLETED', 'FAILED', 'CANCELLED') for s in statuses):
            new_status = 'COMPLETED' if all(s == 'COMPLETED' for s in statuses) else 'FAILED'
        elif any(s == 'RUNNING' for s in statuses):
            new_status = 'RUNNING'
        else:
            new_status = 'QUEUED'

        with _db_write_lock:
            conn = get_db(self.db_path)
            conn.execute(
                "UPDATE batches SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, _now(), batch_id)
            )

    # -----------------------------------------------------------------------
    # File Serving
    # -----------------------------------------------------------------------

    def get_file_path(self, job_id: str) -> str | None:
        """Get the full path to a completed job's file, with safety checks."""
        job = self.get_job(job_id)
        if job is None:
            return None
        if job['status'] != 'COMPLETED':
            return None
        if not job.get('filename'):
            return None

        # Safe path construction — prevent traversal
        filename = os.path.basename(job['filename'])
        full_path = os.path.join(self.download_dir, filename)
        full_path = os.path.abspath(full_path)

        # Verify the file is within the download directory
        if not full_path.startswith(os.path.abspath(self.download_dir)):
            logger.warning("Path traversal attempt detected for job %s", job_id)
            return None

        if not os.path.isfile(full_path):
            return None

        return full_path

    # -----------------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------------

    def _cleanup_loop(self):
        """Periodically clean up old files and job records."""
        while not self._cleanup_event.is_set():
            if self._cleanup_event.wait(timeout=3600):
                break
            try:
                self._cleanup_old_files()
            except Exception as e:
                logger.error("Cleanup error: %s", e)

    def _cleanup_old_files(self):
        """Remove files and jobs older than retention period."""
        if self.file_retention_hours <= 0:
            return

        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.file_retention_hours)
        cutoff_str = cutoff.isoformat()

        conn = get_db(self.db_path)

        # Find old completed/failed jobs
        old_jobs = conn.execute(
            """SELECT id, filename FROM jobs
               WHERE status IN ('COMPLETED', 'FAILED', 'CANCELLED')
               AND updated_at < ?""",
            (cutoff_str,)
        ).fetchall()

        removed_count = 0
        for job in old_jobs:
            if job['filename']:
                filepath = os.path.join(self.download_dir, os.path.basename(job['filename']))
                if os.path.isfile(filepath):
                    try:
                        os.remove(filepath)
                        removed_count += 1
                    except OSError as e:
                        logger.error("Failed to remove file %s: %s", filepath, e)

        # Remove old job records
        with _db_write_lock:
            conn = get_db(self.db_path)
            conn.execute(
                """DELETE FROM jobs
                   WHERE status IN ('COMPLETED', 'FAILED', 'CANCELLED')
                   AND updated_at < ?""",
                (cutoff_str,)
            )

            # Remove empty batches
            conn.execute(
                """DELETE FROM batches
                   WHERE id NOT IN (SELECT DISTINCT batch_id FROM jobs WHERE batch_id IS NOT NULL)
                   AND updated_at < ?""",
                (cutoff_str,)
            )

        if removed_count > 0:
            logger.info("Cleanup: removed %d old files.", removed_count)

    # -----------------------------------------------------------------------
    # Stats
    # -----------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Get service statistics."""
        conn = get_db(self.db_path)
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status"
        ).fetchall()

        stats = {r['status']: r['cnt'] for r in rows}
        return {
            'active_jobs': stats.get('RUNNING', 0),
            'queued_jobs': stats.get('QUEUED', 0),
            'completed_jobs': stats.get('COMPLETED', 0),
            'failed_jobs': stats.get('FAILED', 0),
            'total_jobs': sum(stats.values()),
        }


# ---------------------------------------------------------------------------
# Error Helpers
# ---------------------------------------------------------------------------

def _sanitize_error(error_str: str) -> str:
    """Remove sensitive information from error messages."""
    # Remove filesystem paths
    sanitized = re.sub(r'[A-Za-z]:\\[^\s]+', '[path]', error_str)
    sanitized = re.sub(r'/[^\s]+/[^\s]+', '[path]', sanitized)
    # Remove potential secrets/tokens
    sanitized = re.sub(r'(key|token|secret|password|auth)\s*[:=]\s*\S+', r'\1=[redacted]', sanitized, flags=re.IGNORECASE)
    # Truncate long messages
    if len(sanitized) > 500:
        sanitized = sanitized[:497] + '...'
    return sanitized


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class DownloaderError(Exception):
    """Base exception for downloader errors."""
    status_code = 500
    error_code = 'INTERNAL_ERROR'


class InvalidURLError(DownloaderError):
    status_code = 400
    error_code = 'INVALID_URL'


class InvalidOptionError(DownloaderError):
    status_code = 400
    error_code = 'INVALID_OPTION'


class InvalidStateError(DownloaderError):
    status_code = 409
    error_code = 'INVALID_STATE'


class JobNotFoundError(DownloaderError):
    status_code = 404
    error_code = 'JOB_NOT_FOUND'


class QueueFullError(DownloaderError):
    status_code = 429
    error_code = 'QUEUE_FULL'


class BatchTooLargeError(DownloaderError):
    status_code = 413
    error_code = 'BATCH_TOO_LARGE'


class RetryLimitError(DownloaderError):
    status_code = 409
    error_code = 'RETRY_LIMIT'


class FFmpegMissingError(DownloaderError):
    status_code = 400
    error_code = 'FFMPEG_MISSING'


class DownloadError(DownloaderError):
    status_code = 400
    error_code = 'DOWNLOAD_ERROR'
