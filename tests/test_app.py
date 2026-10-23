"""
test_app.py — Flask Application Tests

Tests for API routes, request validation, error handling, and file serving.
"""

import json
import os
import sqlite3
import tempfile
import uuid

import pytest

# Ensure the project root is importable
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from downloader import init_db


@pytest.fixture
def app_setup(tmp_path):
    """Create a test Flask app with isolated database and download dir."""
    db_path = str(tmp_path / 'test.db')
    dl_dir = str(tmp_path / 'downloads')
    os.makedirs(dl_dir, exist_ok=True)

    config = {
        'FLASK_ENV': 'testing',
        'SECRET_KEY': 'test-secret',
        'DOWNLOAD_DIR': dl_dir,
        'DATABASE_PATH': db_path,
        'MAX_CONCURRENT_DOWNLOADS': '2',
        'MAX_BATCH_SIZE': '5',
        'MAX_PLAYLIST_ITEMS': '10',
        'MAX_QUEUE_DEPTH': '10',
        'DOWNLOAD_TIMEOUT': '60',
        'FILE_RETENTION_HOURS': '1',
        'RATE_LIMIT_PER_MINUTE': '1000',  # High limit for tests
        'MAX_CONTENT_LENGTH': '1048576',
        'MAX_RETRIES': '3',
        'FFMPEG_PATH': '',
    }

    app = create_app(test_config=config)
    app.config['TESTING'] = True

    from unittest.mock import patch
    patcher = patch.object(app.dl_service, '_download_task')
    patcher.start()

    yield app, db_path, dl_dir

    patcher.stop()
    # Cleanup
    app.dl_service.shutdown()


@pytest.fixture
def client(app_setup):
    """Test client."""
    app, _, _ = app_setup
    return app.test_client()


@pytest.fixture
def dl_service(app_setup):
    """Access the downloader service."""
    app, _, _ = app_setup
    return app.dl_service


# ===========================================================================
# Dashboard Tests
# ===========================================================================

class TestDashboard:
    def test_index_returns_html(self, client):
        """GET / should return the dashboard HTML page."""
        resp = client.get('/')
        assert resp.status_code == 200
        assert b'YT Downloader' in resp.data
        assert b'text/html' in resp.content_type.encode()

    def test_index_contains_key_elements(self, client):
        """Dashboard should contain essential UI elements."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'url-input' in html
        assert 'bulk-input' in html
        assert 'quality-select' in html
        assert 'jobs-list' in html
        assert 'toggle-history-storage' in html
        assert 'storage-status-badge' in html
        assert 'btn-clear-history' in html
        assert 'history-storage-info' in html


# ===========================================================================
# Health Endpoint Tests
# ===========================================================================

class TestHealth:
    def test_health_returns_status(self, client):
        """GET /api/health should return health data."""
        resp = client.get('/api/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'status' in data['data']
        assert 'ffmpeg_available' in data['data']
        assert 'active_jobs' in data['data']

    def test_health_does_not_expose_secrets(self, client):
        """Health endpoint should not expose sensitive configuration."""
        resp = client.get('/api/health')
        data_str = json.dumps(resp.get_json())
        assert 'secret' not in data_str.lower()
        assert 'password' not in data_str.lower()


# ===========================================================================
# Metadata Endpoint Tests
# ===========================================================================

class TestMetadataRoute:
    def test_metadata_empty_url(self, client):
        """Should reject empty URL for metadata."""
        resp = client.post('/api/metadata', json={'url': ''}, content_type='application/json')
        assert resp.status_code == 400
        assert resp.get_json()['error']['code'] == 'INVALID_URL'

    def test_metadata_invalid_host(self, client):
        """Should reject non-YouTube URLs."""
        resp = client.post('/api/metadata', json={'url': 'https://evil.com/video'}, content_type='application/json')
        assert resp.status_code == 400

    def test_metadata_video_success(self, client, dl_service):
        """Should return metadata for a valid video URL."""
        from unittest.mock import patch
        mock_meta = {
            'title': 'Test Video',
            'duration': 120,
            'thumbnail': 'https://img.youtube.com/vi/test/0.jpg',
            'uploader': 'Test Channel',
            'view_count': 1000,
            'upload_date': '20260101',
            'formats_available': ['best', '1080p', '720p', 'audio_best', 'audio_mp3'],
        }
        with patch.object(dl_service, 'extract_metadata', return_value=mock_meta):
            resp = client.post('/api/metadata',
                               json={'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
                               content_type='application/json')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert data['data']['title'] == 'Test Video'
            assert data['data']['url_type'] == 'video'

    def test_metadata_playlist_success(self, client, dl_service):
        """Should return playlist items for a valid playlist URL."""
        from unittest.mock import patch
        mock_playlist = {
            'title': 'My Playlist',
            'uploader': 'Test Channel',
            'item_count': 2,
            'items': [
                {'url': 'https://www.youtube.com/watch?v=1', 'title': 'Vid 1', 'duration': 60},
                {'url': 'https://www.youtube.com/watch?v=2', 'title': 'Vid 2', 'duration': 90},
            ],
            'truncated': False,
        }
        with patch.object(dl_service, 'extract_playlist', return_value=mock_playlist):
            resp = client.post('/api/metadata',
                               json={'url': 'https://www.youtube.com/playlist?list=PLrEnWoR732-DNX-Yk_Hnp9i4P_c_hHj9h'},
                               content_type='application/json')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert data['data']['title'] == 'My Playlist'
            assert data['data']['url_type'] == 'playlist'


# ===========================================================================
# URL Validation Tests
# ===========================================================================

class TestURLValidation:
    """Test URL validation through the download endpoint."""

    def test_valid_youtube_watch_url(self, client):
        """Should accept standard YouTube watch URLs."""
        resp = client.post('/api/downloads',
                          json={'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
                          content_type='application/json')
        assert resp.status_code == 202
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['status'] == 'QUEUED'

    def test_valid_youtu_be_url(self, client):
        """Should accept short youtu.be URLs."""
        resp = client.post('/api/downloads',
                          json={'url': 'https://youtu.be/dQw4w9WgXcQ'},
                          content_type='application/json')
        assert resp.status_code == 202
        data = resp.get_json()
        assert data['success'] is True

    def test_invalid_url_empty(self, client):
        """Should reject empty URLs."""
        resp = client.post('/api/downloads',
                          json={'url': ''},
                          content_type='application/json')
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False

    def test_invalid_url_not_youtube(self, client):
        """Should reject non-YouTube URLs."""
        resp = client.post('/api/downloads',
                          json={'url': 'https://www.example.com/video'},
                          content_type='application/json')
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'INVALID_URL' == data['error']['code']

    def test_invalid_url_local_file(self, client):
        """Should reject file:// URLs."""
        resp = client.post('/api/downloads',
                          json={'url': 'file:///etc/passwd'},
                          content_type='application/json')
        assert resp.status_code == 400

    def test_invalid_url_ftp(self, client):
        """Should reject FTP URLs."""
        resp = client.post('/api/downloads',
                          json={'url': 'ftp://youtube.com/video'},
                          content_type='application/json')
        assert resp.status_code == 400

    def test_invalid_url_javascript(self, client):
        """Should reject javascript: URLs."""
        resp = client.post('/api/downloads',
                          json={'url': 'javascript:alert(1)'},
                          content_type='application/json')
        assert resp.status_code == 400

    def test_missing_url_field(self, client):
        """Should reject requests without URL field."""
        resp = client.post('/api/downloads',
                          json={'quality': 'best'},
                          content_type='application/json')
        assert resp.status_code == 400

    def test_invalid_json(self, client):
        """Should reject malformed JSON."""
        resp = client.post('/api/downloads',
                          data='not json',
                          content_type='application/json')
        assert resp.status_code == 400


# ===========================================================================
# Quality & Format Validation Tests
# ===========================================================================

class TestOptionValidation:
    def test_invalid_quality(self, client):
        """Should reject unsupported quality presets."""
        resp = client.post('/api/downloads',
                          json={'url': 'https://www.youtube.com/watch?v=test', 'quality': 'ultra_hd_8k'},
                          content_type='application/json')
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['error']['code'] == 'INVALID_OPTION'

    def test_invalid_format_type(self, client):
        """Should reject unsupported format types."""
        resp = client.post('/api/downloads',
                          json={'url': 'https://www.youtube.com/watch?v=test', 'format_type': 'gif'},
                          content_type='application/json')
        assert resp.status_code == 400


# ===========================================================================
# Batch Download Tests
# ===========================================================================

class TestBatches:
    def test_batch_empty_urls(self, client):
        """Should reject empty URL lists."""
        resp = client.post('/api/batches',
                          json={'urls': []},
                          content_type='application/json')
        assert resp.status_code == 400

    def test_batch_no_urls_field(self, client):
        """Should reject requests without urls field."""
        resp = client.post('/api/batches',
                          json={'quality': 'best'},
                          content_type='application/json')
        assert resp.status_code == 400

    def test_batch_too_large(self, client):
        """Should reject batches exceeding the size limit (5 in test config)."""
        urls = [f'https://www.youtube.com/watch?v=test{i}' for i in range(10)]
        resp = client.post('/api/batches',
                          json={'urls': urls},
                          content_type='application/json')
        assert resp.status_code == 413
        data = resp.get_json()
        assert data['error']['code'] == 'BATCH_TOO_LARGE'

    def test_batch_all_invalid_urls(self, client):
        """Should reject batch with all invalid URLs."""
        resp = client.post('/api/batches',
                          json={'urls': ['not-a-url', 'also-bad']},
                          content_type='application/json')
        assert resp.status_code == 400

    def test_batch_mixed_urls(self, client):
        """Should accept batch with valid URLs and report invalid ones."""
        resp = client.post('/api/batches',
                          json={
                              'urls': [
                                  'https://www.youtube.com/watch?v=test1',
                                  'https://example.com/bad',
                                  'https://www.youtube.com/watch?v=test2',
                              ]
                          },
                          content_type='application/json')
        # Should accept the valid ones
        assert resp.status_code == 202
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['data']['errors']) > 0  # The invalid URL

    def test_batch_duplicates_removed(self, client):
        """Should remove duplicate URLs from batch."""
        resp = client.post('/api/batches',
                          json={
                              'urls': [
                                  'https://www.youtube.com/watch?v=same',
                                  'https://www.youtube.com/watch?v=same',
                                  'https://www.youtube.com/watch?v=diff',
                              ]
                          },
                          content_type='application/json')
        if resp.status_code == 202:
            data = resp.get_json()
            assert data['data']['duplicates_removed'] == 1


# ===========================================================================
# Job Status Tests
# ===========================================================================

class TestJobStatus:
    def test_unknown_job_id(self, client):
        """Should return 404 for unknown job IDs."""
        fake_id = str(uuid.uuid4())
        resp = client.get(f'/api/jobs/{fake_id}')
        assert resp.status_code == 404

    def test_invalid_job_id_format(self, client):
        """Should reject invalid job ID formats."""
        resp = client.get('/api/jobs/not-a-uuid')
        assert resp.status_code == 400

    def test_job_list(self, client):
        """Should return a list of jobs."""
        resp = client.get('/api/jobs')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'jobs' in data['data']

    def test_job_list_filtered_by_ids(self, client, dl_service):
        """Should return only requested jobs when ids param is passed."""
        j1 = dl_service.create_job('https://www.youtube.com/watch?v=vid1', 'best', 'video')
        j2 = dl_service.create_job('https://www.youtube.com/watch?v=vid2', '720p', 'video')

        resp = client.get(f"/api/jobs?ids={j1['job_id']}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        jobs = data['data']['jobs']
        assert len(jobs) == 1
        assert jobs[0]['id'] == j1['job_id']

        # Mixed valid and non-uuid IDs
        resp2 = client.get(f"/api/jobs?ids={j1['job_id']},not-a-uuid,{j2['job_id']}")
        assert resp2.status_code == 200
        jobs2 = resp2.get_json()['data']['jobs']
        assert len(jobs2) == 2


# ===========================================================================
# File Serving Tests
# ===========================================================================

class TestFileServing:
    def test_file_unknown_job(self, client):
        """Should return 404 for file request on unknown job."""
        fake_id = str(uuid.uuid4())
        resp = client.get(f'/api/jobs/{fake_id}/file')
        assert resp.status_code == 404

    def test_file_not_completed(self, client, dl_service):
        """Should return 409 when job is not completed."""
        # Create a job in QUEUED state manually
        from downloader import get_db, _now
        conn = get_db(dl_service.db_path)
        job_id = str(uuid.uuid4())
        now = _now()
        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, created_at, updated_at)
               VALUES (?, ?, 'QUEUED', 'best', 'video', ?, ?)""",
            (job_id, 'https://www.youtube.com/watch?v=test', now, now)
        )
        conn.commit()

        resp = client.get(f'/api/jobs/{job_id}/file')
        assert resp.status_code == 409

    def test_file_path_traversal_prevention(self, client, dl_service):
        """Should prevent path traversal in file requests."""
        from downloader import get_db, _now
        conn = get_db(dl_service.db_path)
        job_id = str(uuid.uuid4())
        now = _now()

        # Attempt path traversal in filename
        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, filename, created_at, updated_at)
               VALUES (?, ?, 'COMPLETED', 'best', 'video', ?, ?, ?)""",
            (job_id, 'https://www.youtube.com/watch?v=test', '../../../etc/passwd', now, now)
        )
        conn.commit()

        resp = client.get(f'/api/jobs/{job_id}/file')
        assert resp.status_code == 404

    def test_file_serving_success(self, client, dl_service):
        """Should serve completed file as attachment with sanitized download name."""
        from downloader import get_db, _now
        conn = get_db(dl_service.db_path)
        job_id = str(uuid.uuid4())
        filename = f"{job_id}.mp4"
        file_path = os.path.join(dl_service.download_dir, filename)

        # Write actual file content
        with open(file_path, "wb") as f:
            f.write(b"video bytes test")

        now = _now()
        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, title, filename, file_size, created_at, updated_at)
               VALUES (?, 'https://www.youtube.com/watch?v=test', 'COMPLETED', 'best', 'video', 'My Cool Video!', ?, 16, ?, ?)""",
            (job_id, filename, now, now)
        )
        conn.commit()

        resp = client.get(f'/api/jobs/{job_id}/file')
        assert resp.status_code == 200
        assert resp.data == b"video bytes test"
        assert 'attachment' in resp.headers.get('Content-Disposition', '')
        assert 'My Cool Video.mp4' in resp.headers.get('Content-Disposition', '')

    def test_file_serving_with_filename_in_path(self, client, dl_service):
        """Should serve completed file via URL with filename in path and set proper mimetype."""
        from downloader import get_db, _now
        conn = get_db(dl_service.db_path)
        job_id = str(uuid.uuid4())
        filename = f"{job_id}.mp4"
        file_path = os.path.join(dl_service.download_dir, filename)

        with open(file_path, "wb") as f:
            f.write(b"video bytes test")

        now = _now()
        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, title, filename, file_size, created_at, updated_at)
               VALUES (?, 'https://www.youtube.com/watch?v=test', 'COMPLETED', 'best', 'video', 'Custom Video Title', ?, 16, ?, ?)""",
            (job_id, filename, now, now)
        )
        conn.commit()

        resp = client.get(f'/api/jobs/{job_id}/file/Custom Video Title.mp4')
        assert resp.status_code == 200
        assert resp.data == b"video bytes test"
        assert resp.content_type.startswith('video/mp4')
        assert 'attachment' in resp.headers.get('Content-Disposition', '')
        assert 'Custom Video Title.mp4' in resp.headers.get('Content-Disposition', '')

    def test_file_serving_file_missing_on_disk(self, client, dl_service):
        """Should return 404 if DB says completed but file removed from disk."""
        from downloader import get_db, _now
        conn = get_db(dl_service.db_path)
        job_id = str(uuid.uuid4())
        now = _now()

        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, title, filename, file_size, created_at, updated_at)
               VALUES (?, 'https://www.youtube.com/watch?v=test', 'COMPLETED', 'best', 'video', 'Test', 'ghost.mp4', 100, ?, ?)""",
            (job_id, now, now)
        )
        conn.commit()

        resp = client.get(f'/api/jobs/{job_id}/file')
        assert resp.status_code == 404
        assert resp.get_json()['error']['code'] == 'FILE_NOT_FOUND'


# ===========================================================================
# Retry Tests
# ===========================================================================

class TestRetry:
    def test_retry_unknown_job(self, client):
        """Should return 404 for retry on unknown job."""
        fake_id = str(uuid.uuid4())
        resp = client.post(f'/api/jobs/{fake_id}/retry')
        assert resp.status_code == 404

    def test_retry_non_failed_job(self, client, dl_service):
        """Should reject retry on non-FAILED jobs."""
        from downloader import get_db, _now
        conn = get_db(dl_service.db_path)
        job_id = str(uuid.uuid4())
        now = _now()
        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, created_at, updated_at)
               VALUES (?, ?, 'QUEUED', 'best', 'video', ?, ?)""",
            (job_id, 'https://www.youtube.com/watch?v=test', now, now)
        )
        conn.commit()

        resp = client.post(f'/api/jobs/{job_id}/retry')
        assert resp.status_code == 409

    def test_retry_limit_exceeded(self, client, dl_service):
        """Should reject retry when max retries reached."""
        from downloader import get_db, _now
        conn = get_db(dl_service.db_path)
        job_id = str(uuid.uuid4())
        now = _now()
        conn.execute(
            """INSERT INTO jobs (id, url, status, quality, format_type, retry_count, max_retries, created_at, updated_at)
               VALUES (?, ?, 'FAILED', 'best', 'video', 3, 3, ?, ?)""",
            (job_id, 'https://www.youtube.com/watch?v=test', now, now)
        )
        conn.commit()

        resp = client.post(f'/api/jobs/{job_id}/retry')
        assert resp.status_code == 409


# ===========================================================================
# Error Handling Tests
# ===========================================================================

class TestErrorHandling:
    def test_404_returns_json(self, client):
        """404 errors should return JSON."""
        resp = client.get('/api/nonexistent')
        assert resp.status_code == 404
        data = resp.get_json()
        assert data['success'] is False

    def test_no_stack_traces_in_errors(self, client):
        """Error responses should not contain stack traces."""
        resp = client.post('/api/downloads',
                          json={'url': 'https://www.youtube.com/watch?v=test', 'quality': 'invalid!'},
                          content_type='application/json')
        if resp.status_code >= 400:
            body = resp.data.decode()
            assert 'Traceback' not in body
            assert 'File "' not in body

    def test_non_json_content_type_rejected(self, client):
        """Should reject non-JSON content type for API endpoints."""
        resp = client.post('/api/downloads',
                          data='url=test',
                          content_type='application/x-www-form-urlencoded')
        assert resp.status_code == 400


# ===========================================================================
# Batch Status Tests
# ===========================================================================

class TestBatchStatus:
    def test_unknown_batch_id(self, client):
        """Should return 404 for unknown batch IDs."""
        fake_id = str(uuid.uuid4())
        resp = client.get(f'/api/batches/{fake_id}')
        assert resp.status_code == 404

    def test_invalid_batch_id_format(self, client):
        """Should reject invalid batch ID formats."""
        resp = client.get('/api/batches/bad-id')
        assert resp.status_code == 400


# ===========================================================================
# Rate Limiting Tests (P7-010)
# ===========================================================================

class TestRateLimiting:
    def test_rate_limit_exceeded(self, tmp_path):
        """Should return 429 when rate limit is exceeded."""
        db_path = str(tmp_path / 'rate_test.db')
        dl_dir = str(tmp_path / 'rate_downloads')
        os.makedirs(dl_dir, exist_ok=True)

        config = {
            'FLASK_ENV': 'testing',
            'SECRET_KEY': 'test-secret',
            'DOWNLOAD_DIR': dl_dir,
            'DATABASE_PATH': db_path,
            'MAX_CONCURRENT_DOWNLOADS': '2',
            'MAX_BATCH_SIZE': '5',
            'MAX_PLAYLIST_ITEMS': '10',
            'MAX_QUEUE_DEPTH': '10',
            'DOWNLOAD_TIMEOUT': '60',
            'FILE_RETENTION_HOURS': '1',
            'RATE_LIMIT_PER_MINUTE': '2',  # Limit to 2 per minute
            'MAX_CONTENT_LENGTH': '1048576',
            'MAX_RETRIES': '3',
            'FFMPEG_PATH': '',
        }

        app = create_app(test_config=config)
        app.config['TESTING'] = True
        client = app.test_client()

        try:
            # First request: OK
            r1 = client.get('/api/health')
            assert r1.status_code == 200

            # Second request: OK
            r2 = client.get('/api/health')
            assert r2.status_code == 200

            # Third request: Should be rate limited (429)
            r3 = client.get('/api/health')
            assert r3.status_code == 429
            data = r3.get_json()
            assert data['success'] is False
            assert data['error']['code'] == 'RATE_LIMITED'
        finally:
            app.dl_service.shutdown()


class TestPlaylistHandlingAndFallbacks:
    """Test playlist error handling, YouTube Mix detection, and single-video fallbacks."""

    def test_youtube_mix_with_video_queues_single_video(self, client):
        """A video URL with a YouTube Mix playlist (RD...) should queue the single video instead of erroring."""
        url = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RDflQgOwg4jLI'
        resp = client.post('/api/downloads',
                           json={'url': url, 'download_type': 'playlist'},
                           content_type='application/json')
        assert resp.status_code == 202
        data = resp.get_json()
        assert data['success'] is True
        assert 'notice' in data['data']
        assert 'Mix' in data['data']['notice']

    def test_pure_youtube_mix_returns_400_not_500(self, client):
        """A pure YouTube Mix playlist URL without a video ID should return 400 with a helpful error, not 500."""
        url = 'https://www.youtube.com/playlist?list=RDflQgOwg4jLI'
        resp = client.post('/api/downloads',
                           json={'url': url, 'download_type': 'playlist'},
                           content_type='application/json')
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert data['error']['code'] in ('INVALID_OPTION', 'DOWNLOAD_ERROR')


