"""
test_downloader.py — Comprehensive Unit Tests for Downloader Module

Tests for URL validation, SSRF defense, options, error sanitization,
job lifecycle, progress hooks, cleanup, and worker execution.
"""

import os
import shutil
import socket
import sqlite3
import tempfile
import time
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from downloader import (
    DownloaderService,
    validate_url,
    validate_quality,
    validate_format_type,
    check_ffmpeg,
    _sanitize_error,
    init_db,
    get_db,
    _now,
    DownloaderError,
    InvalidURLError,
    InvalidOptionError,
    InvalidStateError,
    JobNotFoundError,
    QueueFullError,
    BatchTooLargeError,
    RetryLimitError,
    FFmpegMissingError,
    DownloadError,
    ALLOWED_HOSTS,
    ALLOWED_QUALITIES,
    ALLOWED_FORMAT_TYPES,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def service_env(tmp_path):
    """Provides an isolated DownloaderService instance and directories."""
    db_path = str(tmp_path / "test_dl.db")
    dl_dir = str(tmp_path / "downloads")
    os.makedirs(dl_dir, exist_ok=True)

    config = {
        'DOWNLOAD_DIR': dl_dir,
        'DATABASE_PATH': db_path,
        'MAX_CONCURRENT_DOWNLOADS': '2',
        'MAX_BATCH_SIZE': '5',
        'MAX_PLAYLIST_ITEMS': '10',
        'MAX_QUEUE_DEPTH': '5',
        'DOWNLOAD_TIMEOUT': '60',
        'FILE_RETENTION_HOURS': '1',
        'MAX_RETRIES': '3',
        'FFMPEG_PATH': '',
    }

    # Patch submit to avoid background worker threads starting automatically during setup
    with patch.object(DownloaderService, '_recover_stale_jobs'):
        svc = DownloaderService(config)

    yield svc, db_path, dl_dir

    svc.shutdown()

    from downloader import _db_local
    if hasattr(_db_local, 'connections') and db_path in _db_local.connections:
        try:
            _db_local.connections[db_path].close()
            del _db_local.connections[db_path]
        except Exception:
            pass


# ===========================================================================
# URL Validation Tests
# ===========================================================================

class TestURLValidation:
    """Test URL parsing, format checks, and allowlists."""

    def test_valid_standard_watch_urls(self):
        urls = [
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            'https://youtube.com/watch?v=dQw4w9WgXcQ',
            'https://m.youtube.com/watch?v=dQw4w9WgXcQ',
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s',
        ]
        for u in urls:
            res = validate_url(u)
            assert res['valid'] is True, f"Failed for {u}: {res.get('error')}"
            assert res['url_type'] == 'video'

    def test_valid_short_urls(self):
        urls = [
            'https://youtu.be/dQw4w9WgXcQ',
            'http://youtu.be/dQw4w9WgXcQ',
        ]
        for u in urls:
            res = validate_url(u)
            assert res['valid'] is True
            assert res['url_type'] == 'video'
            assert res['normalized'].startswith('https://')

    def test_valid_shorts_and_embeds(self):
        urls = [
            'https://www.youtube.com/shorts/abcdef12345',
            'https://www.youtube.com/embed/abcdef12345',
            'https://www.youtube.com/v/abcdef12345',
        ]
        for u in urls:
            res = validate_url(u)
            assert res['valid'] is True
            assert res['url_type'] == 'video'

    def test_valid_playlist_urls(self):
        urls = [
            'https://www.youtube.com/playlist?list=PLrEnWoR732-DNX-Yk_Hnp9i4P_c_hHj9h',
            'https://www.youtube.com/watch?list=PLrEnWoR732-DNX-Yk_Hnp9i4P_c_hHj9h',
        ]
        for u in urls:
            res = validate_url(u)
            assert res['valid'] is True
            assert res['url_type'] == 'playlist'

    def test_http_normalized_to_https(self):
        res = validate_url('http://www.youtube.com/watch?v=abcdef12345')
        assert res['valid'] is True
        assert res['normalized'].startswith('https://')

    def test_empty_and_non_string_urls(self):
        assert validate_url('')['valid'] is False
        assert validate_url(None)['valid'] is False
        assert validate_url('   ')['valid'] is False
        assert validate_url(12345)['valid'] is False

    def test_url_too_long(self):
        long_url = 'https://www.youtube.com/watch?v=' + ('x' * 2050)
        res = validate_url(long_url)
        assert res['valid'] is False
        assert 'too long' in res['error'].lower()

    def test_non_http_schemes_rejected(self):
        schemes = [
            'file:///etc/passwd',
            'ftp://youtube.com/video',
            'gopher://youtube.com/',
            'javascript:alert(1)',
            'data:text/html,<h1>test</h1>',
        ]
        for s in schemes:
            res = validate_url(s)
            assert res['valid'] is False
            assert 'https' in res['error'].lower()

    def test_unsupported_domains_rejected(self):
        unsupported = [
            'https://www.vimeo.com/12345678',
            'https://www.dailymotion.com/video/x7tgad0',
            'https://tiktok.com/@user/video/1234',
            'https://malicious-youtube.com/watch?v=123',
            'https://youtube.com.attacker.com/watch?v=123',
        ]
        for u in unsupported:
            res = validate_url(u)
            assert res['valid'] is False
            assert 'unsupported host' in res['error'].lower()


# ===========================================================================
# SSRF Protection Tests
# ===========================================================================

class TestSSRFProtection:
    """Test IP resolution and SSRF defense."""

    def test_private_ip_resolution_rejected(self):
        with patch('socket.getaddrinfo') as mock_dns:
            # Simulate DNS resolving to 192.168.1.1
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.1.1', 443))
            ]
            res = validate_url('https://www.youtube.com/watch?v=test')
            assert res['valid'] is False
            assert 'restricted network' in res['error'].lower()

    def test_loopback_resolution_rejected(self):
        with patch('socket.getaddrinfo') as mock_dns:
            # Simulate DNS resolving to 127.0.0.1
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))
            ]
            res = validate_url('https://www.youtube.com/watch?v=test')
            assert res['valid'] is False
            assert 'restricted network' in res['error'].lower()

    def test_link_local_resolution_rejected(self):
        with patch('socket.getaddrinfo') as mock_dns:
            # 169.254.169.254 (Cloud metadata service)
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('169.254.169.254', 443))
            ]
            res = validate_url('https://www.youtube.com/watch?v=test')
            assert res['valid'] is False
            assert 'restricted network' in res['error'].lower()

    def test_dns_resolution_failure(self):
        with patch('socket.getaddrinfo', side_effect=socket.gaierror):
            res = validate_url('https://www.youtube.com/watch?v=test')
            assert res['valid'] is False
            assert 'could not resolve' in res['error'].lower()


# ===========================================================================
# Option Validation & Error Sanitization Tests
# ===========================================================================

class TestOptionsAndSanitization:
    """Test preset checking and error message sanitization."""

    def test_validate_quality(self):
        for q in ALLOWED_QUALITIES:
            assert validate_quality(q) is True
        assert validate_quality('4k') is False
        assert validate_quality('ultra') is False
        assert validate_quality('') is False

    def test_validate_format_type(self):
        for f in ALLOWED_FORMAT_TYPES:
            assert validate_format_type(f) is True
        assert validate_format_type('image') is False
        assert validate_format_type('text') is False
        assert validate_format_type('') is False

    def test_sanitize_windows_paths(self):
        err = "File not found: C:\\Users\\Administrator\\Downloads\\secret.mp4 failed."
        sanitized = _sanitize_error(err)
        assert "C:\\Users" not in sanitized
        assert "[path]" in sanitized

    def test_sanitize_unix_paths(self):
        err = "Permission denied: /var/www/ytdl/downloads/file.mp4"
        sanitized = _sanitize_error(err)
        assert "/var/www" not in sanitized
        assert "[path]" in sanitized

    def test_sanitize_tokens_and_secrets(self):
        err = "Request failed with token=secret12345auth and key: password999"
        sanitized = _sanitize_error(err)
        assert "secret12345auth" not in sanitized
        assert "password999" not in sanitized

    def test_sanitize_truncates_long_errors(self):
        long_err = "Error: " + ("A" * 600)
        sanitized = _sanitize_error(long_err)
        assert len(sanitized) <= 500
        assert sanitized.endswith("...")


# ===========================================================================
# DownloaderService Job Management Tests
# ===========================================================================

class TestJobLifecycle:
    """Test job CRUD, state transitions, retry limits, and queue depth."""

    def test_create_job_success(self, service_env):
        svc, db_path, _ = service_env
        with patch.object(svc._executor, 'submit') as mock_submit:
            res = svc.create_job(
                url='https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                quality='720p',
                format_type='video'
            )
            assert res['status'] == 'QUEUED'
            assert res['quality'] == '720p'
            assert res['format_type'] == 'video'
            mock_submit.assert_called_once()

            # Verify in DB
            job = svc.get_job(res['job_id'])
            assert job is not None
            assert job['status'] == 'QUEUED'
            assert job['retry_count'] == 0

    def test_queue_depth_limit(self, service_env):
        svc, _, _ = service_env
        svc.max_queue_depth = 2

        with patch.object(svc._executor, 'submit'):
            svc.create_job('https://www.youtube.com/watch?v=video1')
            svc.create_job('https://www.youtube.com/watch?v=video2')

            with pytest.raises(QueueFullError):
                svc.create_job('https://www.youtube.com/watch?v=video3')

    def test_retry_failed_job(self, service_env):
        svc, db_path, _ = service_env
        conn = get_db(db_path)
        job_id = str(uuid.uuid4())
        now = _now()

        # Insert a FAILED job
        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, error_message, retry_count, max_retries, created_at, updated_at)
               VALUES (?, 'https://www.youtube.com/watch?v=test', 'FAILED', 'best', 'video', 'Error', 0, 3, ?, ?)""",
            (job_id, now, now)
        )
        conn.commit()

        with patch.object(svc._executor, 'submit') as mock_submit:
            res = svc.retry_job(job_id)
            assert res['status'] == 'QUEUED'
            mock_submit.assert_called_once()

            updated = svc.get_job(job_id)
            assert updated['status'] == 'QUEUED'
            assert updated['retry_count'] == 1
            assert updated['error_message'] is None

    def test_retry_non_failed_job_raises(self, service_env):
        svc, db_path, _ = service_env
        conn = get_db(db_path)
        job_id = str(uuid.uuid4())
        now = _now()

        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, retry_count, max_retries, created_at, updated_at)
               VALUES (?, 'https://www.youtube.com/watch?v=test', 'COMPLETED', 'best', 'video', 0, 3, ?, ?)""",
            (job_id, now, now)
        )
        conn.commit()

        with pytest.raises(InvalidStateError):
            svc.retry_job(job_id)

    def test_retry_limit_exceeded_raises(self, service_env):
        svc, db_path, _ = service_env
        conn = get_db(db_path)
        job_id = str(uuid.uuid4())
        now = _now()

        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, retry_count, max_retries, created_at, updated_at)
               VALUES (?, 'https://www.youtube.com/watch?v=test', 'FAILED', 'best', 'video', 3, 3, ?, ?)""",
            (job_id, now, now)
        )
        conn.commit()

        with pytest.raises(RetryLimitError):
            svc.retry_job(job_id)

    def test_stale_job_recovery_on_startup(self, service_env):
        svc, db_path, _ = service_env
        conn = get_db(db_path)
        job_id = str(uuid.uuid4())
        now = _now()

        # Insert a job stuck in RUNNING
        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, created_at, updated_at)
               VALUES (?, 'https://www.youtube.com/watch?v=test', 'RUNNING', 'best', 'video', ?, ?)""",
            (job_id, now, now)
        )
        conn.commit()

        # Run recovery
        svc._recover_stale_jobs()

        job = svc.get_job(job_id)
        assert job['status'] == 'FAILED'
        assert 'restart' in job['error_message'].lower()


# ===========================================================================
# Batch Operations Tests
# ===========================================================================

class TestBatchOperations:
    """Test multi-URL batch creation, validation, and aggregation."""

    def test_create_batch_with_deduplication(self, service_env):
        svc, _, _ = service_env
        urls = [
            'https://www.youtube.com/watch?v=video1',
            'https://www.youtube.com/watch?v=video1',  # duplicate
            'https://www.youtube.com/watch?v=video2',
            'https://invalid.com/video',                # invalid
        ]

        with patch.object(svc._executor, 'submit'):
            res = svc.create_batch(urls, quality='720p', format_type='video')
            assert res['total'] == 2
            assert res['duplicates_removed'] == 1
            assert len(res['errors']) == 1
            assert res['errors'][0]['error'] is not None

            # Check batch record
            batch = svc.get_batch(res['batch_id'])
            assert batch is not None
            assert batch['total_items'] == 2

    def test_create_batch_too_large(self, service_env):
        svc, _, _ = service_env
        svc.max_batch_size = 2
        urls = [
            'https://www.youtube.com/watch?v=video1',
            'https://www.youtube.com/watch?v=video2',
            'https://www.youtube.com/watch?v=video3',
        ]
        with pytest.raises(BatchTooLargeError):
            svc.create_batch(urls)


# ===========================================================================
# Progress & Postprocessor Hooks Tests
# ===========================================================================

class TestProgressHooks:
    """Test yt-dlp progress callbacks and state updates."""

    def test_progress_hook_updates_db(self, service_env):
        svc, db_path, _ = service_env
        conn = get_db(db_path)
        job_id = str(uuid.uuid4())
        now = _now()

        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, created_at, updated_at)
               VALUES (?, 'https://www.youtube.com/watch?v=test', 'RUNNING', 'best', 'video', ?, ?)""",
            (job_id, now, now)
        )
        conn.commit()

        # Simulate hook call from yt-dlp
        progress_data = {
            'status': 'downloading',
            'downloaded_bytes': 5000000,
            'total_bytes': 10000000,
            'speed': 1048576,
            'eta': 5,
        }
        svc._progress_hook(job_id, progress_data)

        job = svc.get_job(job_id)
        assert job['progress_percent'] == 50.0
        assert job['downloaded_bytes'] == 5000000
        assert job['total_bytes'] == 10000000
        assert job['speed'] == 1048576
        assert job['eta'] == 5

    def test_postprocessor_hook_resets_progress(self, service_env):
        svc, db_path, _ = service_env
        conn = get_db(db_path)
        job_id = str(uuid.uuid4())
        now = _now()

        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, progress_percent, created_at, updated_at)
               VALUES (?, 'https://www.youtube.com/watch?v=test', 'RUNNING', 'best', 'video', 99.0, ?, ?)""",
            (job_id, now, now)
        )
        conn.commit()

        svc._postprocessor_hook(job_id, {'status': 'started'})

        job = svc.get_job(job_id)
        assert job['progress_percent'] is None


# ===========================================================================
# File Cleanup & Serving Tests
# ===========================================================================

class TestCleanupAndServing:
    """Test file retention cleanup and safe file resolution."""

    def test_cleanup_removes_old_files_and_jobs(self, service_env):
        svc, db_path, dl_dir = service_env
        conn = get_db(db_path)

        # Create a file on disk
        old_job_id = str(uuid.uuid4())
        old_filename = f"{old_job_id}.mp4"
        old_file_path = os.path.join(dl_dir, old_filename)
        with open(old_file_path, "wb") as f:
            f.write(b"dummy video content")

        # Set timestamp 2 hours in the past (retention is 1 hour)
        past_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, filename, file_size, created_at, updated_at)
               VALUES (?, 'https://www.youtube.com/watch?v=old', 'COMPLETED', 'best', 'video', ?, 19, ?, ?)""",
            (old_job_id, old_filename, past_time, past_time)
        )

        # Create a fresh completed job
        fresh_job_id = str(uuid.uuid4())
        fresh_filename = f"{fresh_job_id}.mp4"
        fresh_file_path = os.path.join(dl_dir, fresh_filename)
        with open(fresh_file_path, "wb") as f:
            f.write(b"new video content")

        now = _now()
        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, filename, file_size, created_at, updated_at)
               VALUES (?, 'https://www.youtube.com/watch?v=new', 'COMPLETED', 'best', 'video', ?, 17, ?, ?)""",
            (fresh_job_id, fresh_filename, now, now)
        )
        conn.commit()

        # Run cleanup
        svc._cleanup_old_files()

        # Old file should be deleted, new file should remain
        assert not os.path.exists(old_file_path)
        assert os.path.exists(fresh_file_path)

        # Old job record should be gone, new job record retained
        assert svc.get_job(old_job_id) is None
        assert svc.get_job(fresh_job_id) is not None

    def test_get_file_path_safe_and_traversal_proof(self, service_env):
        svc, db_path, dl_dir = service_env
        conn = get_db(db_path)
        job_id = str(uuid.uuid4())
        now = _now()

        # Valid file
        valid_filename = f"{job_id}.mp4"
        valid_path = os.path.join(dl_dir, valid_filename)
        with open(valid_path, "wb") as f:
            f.write(b"video data")

        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, filename, created_at, updated_at)
               VALUES (?, 'https://www.youtube.com/watch?v=test', 'COMPLETED', 'best', 'video', ?, ?, ?)""",
            (job_id, valid_filename, now, now)
        )
        conn.commit()

        resolved = svc.get_file_path(job_id)
        assert resolved == os.path.abspath(valid_path)

        # Traversal attempt
        conn.execute(
            "UPDATE jobs SET filename = ? WHERE id = ?",
            ("../../etc/passwd", job_id)
        )
        conn.commit()
        # basename strips directories, but file "passwd" doesn't exist in dl_dir
        assert svc.get_file_path(job_id) is None

    def test_stats_reporting(self, service_env):
        svc, db_path, _ = service_env
        conn = get_db(db_path)
        now = _now()

        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, created_at, updated_at)
               VALUES (?, 'https://www.youtube.com/watch?v=1', 'COMPLETED', 'best', 'video', ?, ?)""",
            (str(uuid.uuid4()), now, now)
        )
        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, created_at, updated_at)
               VALUES (?, 'https://www.youtube.com/watch?v=2', 'FAILED', 'best', 'video', ?, ?)""",
            (str(uuid.uuid4()), now, now)
        )
        conn.commit()

        stats = svc.get_stats()
        assert stats['completed_jobs'] == 1
        assert stats['failed_jobs'] == 1
        assert stats['total_jobs'] == 2


# ===========================================================================
# Metadata & Playlist Extraction Tests
# ===========================================================================

class TestMetadataExtraction:
    """Test metadata and playlist extraction using mocked YoutubeDL."""

    def test_extract_metadata_success(self, service_env):
        svc, _, _ = service_env
        fake_info = {
            'title': 'Mock Video Title',
            'duration': 180,
            'thumbnail': 'https://example.com/thumb.jpg',
            'uploader': 'Mock Channel',
            'view_count': 50000,
            'upload_date': '20260101',
            'formats': [
                {'height': 1080},
                {'height': 720},
                {'height': 480},
                {'height': 360},
            ]
        }

        with patch('yt_dlp.YoutubeDL') as mock_ydl_cls:
            mock_ydl = MagicMock()
            mock_ydl.__enter__.return_value = mock_ydl
            mock_ydl.extract_info.return_value = fake_info
            mock_ydl_cls.return_value = mock_ydl

            res = svc.extract_metadata('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
            assert res['title'] == 'Mock Video Title'
            assert res['duration'] == 180
            assert '1080p' in res['formats_available']
            assert '720p' in res['formats_available']
            assert '480p' in res['formats_available']
            assert res['url_type'] == 'video'

    def test_extract_metadata_download_error(self, service_env):
        svc, _, _ = service_env
        import yt_dlp.utils
        with patch('yt_dlp.YoutubeDL') as mock_ydl_cls:
            mock_ydl = MagicMock()
            mock_ydl.__enter__.return_value = mock_ydl
            mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError("Video unavailable")
            mock_ydl_cls.return_value = mock_ydl

            with pytest.raises(DownloadError) as exc_info:
                svc.extract_metadata('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
            assert 'video unavailable' in str(exc_info.value).lower()

    def test_extract_playlist_success(self, service_env):
        svc, _, _ = service_env
        fake_playlist = {
            'title': 'Test Playlist',
            'uploader': 'Test User',
            'entries': [
                {'url': 'https://www.youtube.com/watch?v=1', 'title': 'Entry 1', 'duration': 100},
                {'id': '2', 'title': 'Entry 2', 'duration': 200},  # ID without full URL
                None,  # Skipped entry
            ]
        }

        with patch('yt_dlp.YoutubeDL') as mock_ydl_cls:
            mock_ydl = MagicMock()
            mock_ydl.__enter__.return_value = mock_ydl
            mock_ydl.extract_info.return_value = fake_playlist
            mock_ydl_cls.return_value = mock_ydl

            res = svc.extract_playlist('https://www.youtube.com/playlist?list=PLrEnWoR732-DNX-Yk_Hnp9i4P_c_hHj9h')
            assert res['title'] == 'Test Playlist'
            assert res['item_count'] == 2
            assert res['items'][0]['title'] == 'Entry 1'
            assert res['items'][1]['url'] == 'https://www.youtube.com/watch?v=2'


# ===========================================================================
# Download Task Execution Tests
# ===========================================================================

class TestDownloadTaskExecution:
    """Test worker task execution, formatting options, and failure handling."""

    def test_download_task_success(self, service_env):
        svc, db_path, dl_dir = service_env
        conn = get_db(db_path)
        job_id = str(uuid.uuid4())
        now = _now()

        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, created_at, updated_at)
               VALUES (?, 'https://www.youtube.com/watch?v=test', 'QUEUED', 'best', 'video', ?, ?)""",
            (job_id, now, now)
        )
        conn.commit()

        # Simulate yt-dlp creating the output file
        def fake_extract_info(url, download=True):
            out_file = os.path.join(dl_dir, f"{job_id}.mp4")
            with open(out_file, "wb") as f:
                f.write(b"completed downloaded video data")
            return {'title': 'Downloaded Test Video'}

        with patch('yt_dlp.YoutubeDL') as mock_ydl_cls:
            mock_ydl = MagicMock()
            mock_ydl.__enter__.return_value = mock_ydl
            mock_ydl.extract_info.side_effect = fake_extract_info
            mock_ydl_cls.return_value = mock_ydl

            svc._download_task(job_id)

        job = svc.get_job(job_id)
        assert job['status'] == 'COMPLETED'
        assert job['title'] == 'Downloaded Test Video'
        assert job['filename'] == f"{job_id}.mp4"
        assert job['file_size'] > 0
        assert job['progress_percent'] == 100

    def test_download_task_failure(self, service_env):
        svc, db_path, _ = service_env
        conn = get_db(db_path)
        job_id = str(uuid.uuid4())
        now = _now()

        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, created_at, updated_at)
               VALUES (?, 'https://www.youtube.com/watch?v=test', 'QUEUED', 'best', 'video', ?, ?)""",
            (job_id, now, now)
        )
        conn.commit()

        with patch('yt_dlp.YoutubeDL') as mock_ydl_cls:
            mock_ydl = MagicMock()
            mock_ydl.__enter__.return_value = mock_ydl
            mock_ydl.extract_info.side_effect = Exception("YouTube error: Video unavailable in C:\\Windows\\temp")
            mock_ydl_cls.return_value = mock_ydl

            svc._download_task(job_id)

        job = svc.get_job(job_id)
        assert job['status'] == 'FAILED'
        assert 'unavailable' in job['error_message'].lower()
        # Path must be redacted
        assert "C:\\Windows" not in job['error_message']

    def test_create_job_mp3_without_ffmpeg_raises(self, service_env):
        svc, _, _ = service_env
        svc.ffmpeg_available = False
        with pytest.raises(FFmpegMissingError):
            svc.create_job('https://www.youtube.com/watch?v=test', quality='audio_mp3', format_type='audio')

    def test_create_job_audio_format_adjusts_quality(self, service_env):
        svc, _, _ = service_env
        with patch.object(svc._executor, 'submit'):
            # video quality with audio format -> auto adjusts to audio_best
            res = svc.create_job('https://www.youtube.com/watch?v=test', quality='720p', format_type='audio')
            assert res['quality'] == 'audio_best'
            assert res['format_type'] == 'audio'

    def test_get_jobs_by_ids(self, service_env):
        svc, db_path, _ = service_env
        assert svc.get_jobs_by_ids([]) == []

        # Create two jobs
        with patch.object(svc._executor, 'submit'):
            j1 = svc.create_job('https://www.youtube.com/watch?v=vid1', quality='best', format_type='video')
            j2 = svc.create_job('https://www.youtube.com/watch?v=vid2', quality='720p', format_type='video')

        res = svc.get_jobs_by_ids([j1['job_id'], j2['job_id']])
        assert len(res) == 2
        res_ids = {r['id'] for r in res}
        assert j1['job_id'] in res_ids
        assert j2['job_id'] in res_ids

        # Non-existent ID returns empty
        assert svc.get_jobs_by_ids([str(uuid.uuid4())]) == []

