"""
app.py — YT-DLP Web Downloader Flask Application

HTTP routing, request validation, error handling, and file serving.
"""

import atexit
import logging
import os
import re
import secrets
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask, jsonify, render_template, request, send_file, abort,
    Response, make_response, redirect, url_for
)

from downloader import (
    DownloaderService,
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
    validate_url,
    validate_quality,
    validate_format_type,
)

# ---------------------------------------------------------------------------
# Load environment
# ---------------------------------------------------------------------------

load_dotenv()

# ---------------------------------------------------------------------------
# Application Factory
# ---------------------------------------------------------------------------


def create_app(test_config: dict = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, static_folder='static', template_folder='templates')

    # Configuration
    if test_config:
        config = test_config
    else:
        config = {
            'FLASK_ENV': os.getenv('FLASK_ENV', 'development'),
            'SECRET_KEY': os.getenv('SECRET_KEY', secrets.token_hex(32)),
            'DOWNLOAD_DIR': os.getenv('DOWNLOAD_DIR', './downloads'),
            'DATABASE_PATH': os.getenv('DATABASE_PATH', './ytdl.db'),
            'MAX_CONCURRENT_DOWNLOADS': os.getenv('MAX_CONCURRENT_DOWNLOADS', '3'),
            'MAX_BATCH_SIZE': os.getenv('MAX_BATCH_SIZE', '20'),
            'MAX_PLAYLIST_ITEMS': os.getenv('MAX_PLAYLIST_ITEMS', '50'),
            'MAX_QUEUE_DEPTH': os.getenv('MAX_QUEUE_DEPTH', '50'),
            'DOWNLOAD_TIMEOUT': os.getenv('DOWNLOAD_TIMEOUT', '1800'),
            'FILE_RETENTION_HOURS': os.getenv('FILE_RETENTION_HOURS', '24'),
            'RATE_LIMIT_PER_MINUTE': os.getenv('RATE_LIMIT_PER_MINUTE', '30'),
            'MAX_CONTENT_LENGTH': os.getenv('MAX_CONTENT_LENGTH', '1048576'),
            'MAX_RETRIES': os.getenv('MAX_RETRIES', '3'),
            'FFMPEG_PATH': os.getenv('FFMPEG_PATH', ''),
        }

    app.config['SECRET_KEY'] = config.get('SECRET_KEY', secrets.token_hex(32))
    app.config['MAX_CONTENT_LENGTH'] = int(config.get('MAX_CONTENT_LENGTH', 1048576))
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    # Logging
    logging.basicConfig(
        level=logging.INFO if config.get('FLASK_ENV') != 'development' else logging.DEBUG,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Rate Limiting
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        rate_limit = f"{config.get('RATE_LIMIT_PER_MINUTE', '30')}/minute"
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=[rate_limit],
            storage_uri="memory://",
        )
    except ImportError:
        logger.warning("Flask-Limiter not installed. Rate limiting disabled.")
        limiter = None

    # Cross-Origin Resource Sharing (CORS) for frontend / GitHub Pages
    try:
        from flask_cors import CORS
        CORS(app, resources={r"/api/*": {"origins": "*"}}, expose_headers=["Content-Disposition"])
    except ImportError:
        logger.warning("Flask-Cors not installed. Relying on custom CORS headers.")

    # Initialize Downloader Service
    dl_service = DownloaderService(config)
    app.dl_service = dl_service  # For test access

    # Shutdown hook
    atexit.register(dl_service.shutdown)

    # -------------------------------------------------------------------
    # Error Handlers
    # -------------------------------------------------------------------

    @app.errorhandler(DownloaderError)
    def handle_downloader_error(e):
        return jsonify({
            'success': False,
            'error': {
                'code': e.error_code,
                'message': str(e),
            }
        }), e.status_code

    @app.errorhandler(400)
    def handle_400(e):
        return jsonify({
            'success': False,
            'error': {
                'code': 'BAD_REQUEST',
                'message': 'Invalid request.',
            }
        }), 400

    @app.errorhandler(404)
    def handle_404(e):
        return jsonify({
            'success': False,
            'error': {
                'code': 'NOT_FOUND',
                'message': 'Resource not found.',
            }
        }), 404

    @app.errorhandler(413)
    def handle_413(e):
        return jsonify({
            'success': False,
            'error': {
                'code': 'REQUEST_TOO_LARGE',
                'message': 'Request body too large.',
            }
        }), 413

    @app.errorhandler(429)
    def handle_429(e):
        return jsonify({
            'success': False,
            'error': {
                'code': 'RATE_LIMITED',
                'message': 'Too many requests. Please try again later.',
            }
        }), 429

    @app.errorhandler(500)
    def handle_500(e):
        logger.error("Internal error: %s", e)
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'An unexpected error occurred.',
            }
        }), 500

    # -------------------------------------------------------------------
    # Routes
    # -------------------------------------------------------------------

    # ---------------------------------------------------------------
    # Before-request: handle CORS preflight for /api/
    # ---------------------------------------------------------------

    @app.before_request
    def handle_options_preflight():
        if request.method == 'OPTIONS' and request.path.startswith('/api/'):
            response = make_response('', 204)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
            response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
            return response

    # ---------------------------------------------------------------
    # After-request: mark /api/ routes as noindex and ensure CORS
    # ---------------------------------------------------------------

    @app.after_request
    def add_headers_for_api(response):
        """Add X-Robots-Tag and CORS headers to all /api/ paths."""
        if request.path.startswith('/api/'):
            response.headers['X-Robots-Tag'] = 'noindex, nofollow'
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
            response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
        return response

    # ---------------------------------------------------------------
    # Core UI pages
    # ---------------------------------------------------------------
    # Core Canonical UI Pages
    # ---------------------------------------------------------------

    @app.route('/')
    def index():
        """Brand & Overview landing page ('Free YouTube Downloader, No Ads')."""
        return render_template('index.html')

    @app.route('/youtube-to-mp3')
    def youtube_to_mp3():
        """Dedicated YouTube to MP3 & audio extraction utility."""
        return render_template('youtube_to_mp3.html')

    @app.route('/youtube-video-downloader', endpoint='youtube_video_downloader')
    @app.route('/youtube-video-downloader', endpoint='video_downloader')
    def youtube_video_downloader():
        """Dedicated high-definition video downloader (4K/1080p)."""
        return render_template('video_downloader.html')

    @app.route('/bulk-youtube-to-mp3', endpoint='bulk_youtube_to_mp3')
    @app.route('/bulk-youtube-to-mp3', endpoint='bulk_audio')
    @app.route('/bulk-youtube-to-mp3', endpoint='bulk_youtube_downloader')
    def bulk_youtube_to_mp3():
        """Dedicated bulk YouTube to MP3 queue downloader."""
        return render_template('bulk_audio.html')

    @app.route('/bulk-youtube-video-downloader', endpoint='bulk_youtube_video_downloader')
    @app.route('/bulk-youtube-video-downloader', endpoint='bulk_video_downloader')
    @app.route('/bulk-youtube-video-downloader', endpoint='bulk_video')
    def bulk_youtube_video_downloader():
        """Dedicated bulk YouTube video downloader."""
        return render_template('bulk_video.html')

    @app.route('/youtube-playlist-downloader')
    def youtube_playlist_downloader():
        """Dedicated playlist downloader for up to 50 items."""
        return render_template('playlist_downloader.html')

    @app.route('/youtube-video-info')
    def youtube_video_info():
        """Inspect video metadata, codecs, and thumbnails before downloading."""
        return render_template('video_info.html')

    # ---------------------------------------------------------------
    # 301 Permanent Redirects for Duplicate & Legacy Slugs (Section 1)
    # ---------------------------------------------------------------

    @app.route('/shorts-downloader', endpoint='shorts_downloader')
    @app.route('/youtube-shorts-downloader', endpoint='youtube_shorts_downloader')
    def shorts_downloader_route():
        return redirect(url_for('youtube_video_downloader'), code=301)

    @app.route('/audio-downloader', endpoint='audio_downloader_legacy')
    def audio_downloader_legacy():
        return redirect(url_for('youtube_to_mp3'), code=301)

    @app.route('/video', endpoint='video_legacy')
    @app.route('/video-downloader', endpoint='video_downloader_legacy')
    def video_downloader_legacy():
        return redirect(url_for('youtube_video_downloader'), code=301)

    @app.route('/bulk-audio', endpoint='bulk_audio_legacy')
    @app.route('/bulk-audio-downloader', endpoint='bulk_audio_downloader_legacy')
    @app.route('/bulk-youtube-downloader', endpoint='bulk_youtube_downloader_legacy')
    def bulk_audio_legacy():
        return redirect(url_for('bulk_youtube_to_mp3'), code=301)

    @app.route('/bulk-video', endpoint='bulk_video_legacy')
    @app.route('/bulk-video-downloader', endpoint='bulk_video_downloader_legacy')
    def bulk_video_legacy():
        return redirect(url_for('bulk_youtube_video_downloader'), code=301)

    @app.route('/self-host', endpoint='self_host_legacy')
    def self_host_legacy():
        return redirect(url_for('self_hosted_youtube_downloader'), code=301)

    @app.route('/self-hosted-youtube-downloader', endpoint='self_hosted_youtube_downloader')
    @app.route('/self-hosted-youtube-downloader', endpoint='self_host')
    def self_hosted_youtube_downloader():
        return render_template('self_host.html')

    # ---------------------------------------------------------------
    # Format & Quality Converter Pages (Section 3A)
    # ---------------------------------------------------------------

    @app.route('/youtube-to-mp4')
    def youtube_to_mp4():
        return render_template('format_mp4.html')

    @app.route('/youtube-to-wav')
    def youtube_to_wav():
        return render_template('format_wav.html')

    @app.route('/youtube-to-m4a')
    def youtube_to_m4a():
        return render_template('format_m4a.html')

    @app.route('/youtube-to-flac')
    def youtube_to_flac():
        return render_template('format_flac.html')

    @app.route('/youtube-4k-downloader')
    def youtube_4k_downloader():
        return render_template('format_4k.html')

    # ---------------------------------------------------------------
    # Differentiator Pages (Section 3B)
    # ---------------------------------------------------------------

    @app.route('/ad-free-youtube-downloader')
    def ad_free_youtube_downloader():
        return render_template('ad_free.html')

    @app.route('/safe-youtube-downloader')
    def safe_youtube_downloader():
        return render_template('safe_downloader.html')

    @app.route('/yt-dlp-web-ui', endpoint='yt_dlp_web_ui')
    @app.route('/yt-dlp-web-ui', endpoint='ytdlp_web_ui')
    def yt_dlp_web_ui():
        return render_template('ytdlp_web_ui.html')

    @app.route('/supported-sites')
    def supported_sites():
        return render_template('supported_sites.html')

    @app.route('/changelog')
    def changelog():
        return render_template('changelog.html')

    @app.route('/how-it-works')
    def how_it_works():
        return render_template('how_it_works.html')

    # ---------------------------------------------------------------
    # Trust, Legal & Supporting Pages (Section 3D)
    # ---------------------------------------------------------------

    @app.route('/about')
    def about():
        return render_template('about.html')

    @app.route('/contact')
    def contact():
        return render_template('contact.html')

    @app.route('/privacy')
    def privacy():
        return render_template('privacy.html')

    @app.route('/terms')
    def terms():
        return render_template('terms.html')

    @app.route('/dmca')
    def dmca():
        return render_template('dmca.html')

    @app.route('/fair-use')
    def fair_use():
        return render_template('fair_use.html')

    @app.route('/site-map.html')
    def site_map():
        return render_template('site_map.html')

    @app.route('/faq')
    def faq():
        return render_template('faq.html')

    @app.route('/favicon.ico')
    def favicon():
        """Handle browser favicon request cleanly."""
        return '', 204

    # ---------------------------------------------------------------
    # Blog Hub & Individual Posts
    # ---------------------------------------------------------------

    @app.route('/blog')
    def blog_index():
        from blog_posts import get_all_posts
        return render_template('blog/index.html', posts=get_all_posts())

    @app.route('/blog/<slug>')
    def blog_post(slug):
        from blog_posts import get_post, get_all_posts
        post = get_post(slug)
        if post is None:
            abort(404)
        all_posts = get_all_posts()
        related = [p for p in all_posts if p['slug'] != slug][:3]
        return render_template('blog/post.html', post=post, related_posts=related)

    # ---------------------------------------------------------------
    # SEO Technical: sitemap.xml & robots.txt (Section 6 & 8)
    # ---------------------------------------------------------------

    @app.route('/sitemap.xml')
    def sitemap():
        """Generate XML sitemap containing only canonical URLs."""
        from blog_posts import get_all_posts
        base = os.environ.get('BASE_URL', 'https://yt-downlooader.netlify.app').rstrip('/')
        today = datetime.utcnow().strftime('%Y-%m-%d')

        canonical_pages = [
            ('/', '1.0', 'daily'),
            ('/youtube-to-mp3', '0.9', 'weekly'),
            ('/youtube-video-downloader', '0.9', 'weekly'),
            ('/bulk-youtube-to-mp3', '0.9', 'weekly'),
            ('/bulk-youtube-video-downloader', '0.9', 'weekly'),
            ('/youtube-playlist-downloader', '0.9', 'weekly'),
            ('/youtube-video-info', '0.8', 'weekly'),
            ('/youtube-to-mp4', '0.8', 'weekly'),
            ('/youtube-to-wav', '0.8', 'weekly'),
            ('/youtube-to-m4a', '0.8', 'weekly'),
            ('/youtube-to-flac', '0.8', 'weekly'),
            ('/youtube-4k-downloader', '0.8', 'weekly'),
            ('/ad-free-youtube-downloader', '0.8', 'weekly'),
            ('/safe-youtube-downloader', '0.8', 'weekly'),
            ('/self-hosted-youtube-downloader', '0.8', 'monthly'),
            ('/yt-dlp-web-ui', '0.8', 'monthly'),
            ('/supported-sites', '0.7', 'monthly'),
            ('/how-it-works', '0.8', 'monthly'),
            ('/changelog', '0.6', 'weekly'),
            ('/about', '0.6', 'monthly'),
            ('/faq', '0.8', 'monthly'),
            ('/fair-use', '0.7', 'monthly'),
            ('/contact', '0.5', 'monthly'),
            ('/privacy', '0.4', 'yearly'),
            ('/terms', '0.4', 'yearly'),
            ('/dmca', '0.4', 'yearly'),
            ('/site-map.html', '0.5', 'weekly'),
            ('/blog', '0.8', 'weekly'),
        ]

        urls_xml = []
        for path, priority, changefreq in canonical_pages:
            urls_xml.append(
                f'  <url>\n'
                f'    <loc>{base}{path}</loc>\n'
                f'    <lastmod>{today}</lastmod>\n'
                f'    <changefreq>{changefreq}</changefreq>\n'
                f'    <priority>{priority}</priority>\n'
                f'  </url>'
            )

        for post in get_all_posts():
            urls_xml.append(
                f'  <url>\n'
                f'    <loc>{base}/blog/{post["slug"]}</loc>\n'
                f'    <lastmod>{today}</lastmod>\n'
                f'    <changefreq>monthly</changefreq>\n'
                f'    <priority>0.7</priority>\n'
                f'  </url>'
            )

        sitemap_content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + '\n'.join(urls_xml)
            + '\n</urlset>'
        )
        return Response(sitemap_content, mimetype='application/xml')

    @app.route('/robots.txt')
    def robots():
        """Serve robots.txt allowing public content and AI search bots while shielding API/temp folders."""
        base = os.environ.get('BASE_URL', 'https://yt-downlooader.netlify.app').rstrip('/')
        content = (
            'User-agent: *\n'
            'Allow: /\n'
            'Disallow: /api/\n'
            'Disallow: /downloads/\n'
            'Disallow: /jobs/\n'
            'Disallow: /tmp/\n'
            'Disallow: /files/\n'
            '\n'
            '# AI and Search Bot specific rules\n'
            'User-agent: Googlebot\n'
            'Allow: /\n'
            '\n'
            'User-agent: Bingbot\n'
            'Allow: /\n'
            '\n'
            'User-agent: OAI-SearchBot\n'
            'Allow: /\n'
            '\n'
            'User-agent: GPTBot\n'
            'Allow: /\n'
            '\n'
            'User-agent: ChatGPT-User\n'
            'Allow: /\n'
            '\n'
            'User-agent: PerplexityBot\n'
            'Allow: /\n'
            '\n'
            'User-agent: Claude-SearchBot\n'
            'Allow: /\n'
            '\n'
            'User-agent: Applebot\n'
            'Allow: /\n'
            '\n'
            'User-agent: Amazonbot\n'
            'Allow: /\n'
            '\n'
            f'Sitemap: {base}/sitemap.xml\n'
        )
        return Response(content, mimetype='text/plain')

    @app.route('/api/health', methods=['GET'])
    def health():
        """Return application health and dependency status."""
        stats = dl_service.get_stats()
        return jsonify({
            'success': True,
            'data': {
                'status': 'healthy',
                'ffmpeg_available': dl_service.ffmpeg_available,
                'active_jobs': stats['active_jobs'],
                'queued_jobs': stats['queued_jobs'],
                'max_batch_size': dl_service.max_batch_size,
                'max_queue_depth': dl_service.max_queue_depth,
                'version': '1.0.6',
                'cookie_env_keys': [k for k in os.environ if 'cookie' in k.lower()],
                'has_rendered_cookies': os.path.isfile('/etc/secrets/cookies.txt'),
                'download_cookie': os.path.isfile(os.path.join(dl_service.download_dir, 'cookies.txt')),
                'deno_available': bool(
                    shutil.which('deno')
                    or os.path.isfile('/opt/deno/bin/deno')
                    or os.path.isfile(os.path.expanduser('~/.deno/bin/deno'))
                ),
                'deno_path': (
                    shutil.which('deno')
                    or ('/opt/deno/bin/deno' if os.path.isfile('/opt/deno/bin/deno') else None)
                    or (os.path.expanduser('~/.deno/bin/deno') if os.path.isfile(os.path.expanduser('~/.deno/bin/deno')) else None)
                ),
                'node_available': bool(shutil.which('node')),
            }
        })

    @app.route('/api/stream-url', methods=['POST'])
    def stream_url():
        """
        Extract a direct YouTube CDN audio stream URL.
        The browser downloads straight from YouTube at full speed —
        no file ever touches this server.
        """
        data = _get_json()
        url = data.get('url', '').strip()
        fmt = data.get('format', 'audio_best').strip()   # 'audio_best' or 'audio_mp3'

        if not url:
            raise InvalidURLError("URL is required.")

        val = validate_url(url)
        if not val['valid']:
            raise InvalidURLError(val['error'])

        result = dl_service.get_stream_url(val['normalized'], fmt)
        return jsonify({'success': True, 'data': result})

    @app.route('/api/metadata', methods=['POST'])
    def metadata():
        """Extract video or playlist metadata without downloading."""
        data = _get_json()
        url = data.get('url', '').strip()
        request_type = data.get('type')  # optional: 'playlist' or 'video'

        if not url:
            raise InvalidURLError("URL is required.")

        val = validate_url(url)
        if not val['valid']:
            raise InvalidURLError(val['error'])

        # YouTube Mixes (RD...) cannot be extracted as playlists; always extract the video
        if not val.get('is_mix') and (request_type == 'playlist' or val['url_type'] == 'playlist'):
            result = dl_service.extract_playlist(url)
            result['url_type'] = 'playlist'
        else:
            result = dl_service.extract_metadata(url)
            result['url_type'] = 'video'
            if val.get('has_playlist'):
                result['has_playlist'] = True
                result['playlist_id'] = val.get('playlist_id')
            if val.get('is_mix'):
                result['is_mix'] = True
                result['playlist_id'] = val.get('playlist_id')

        return jsonify({'success': True, 'data': result})

    @app.route('/api/downloads', methods=['POST'])
    def create_download():
        """Submit a single-video or playlist download job."""
        data = _get_json()
        url = data.get('url', '').strip()
        quality = data.get('quality', 'best').strip()
        format_type = data.get('format_type', 'video').strip()
        download_type = data.get('download_type', 'auto').strip()

        if not url:
            raise InvalidURLError("URL is required.")

        val = validate_url(url)
        if not val['valid']:
            raise InvalidURLError(val['error'])

        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(url).query)
        video_id = qs.get('v', [None])[0]

        is_playlist = (download_type == 'playlist') or (val.get('url_type') == 'playlist' and download_type != 'video')

        if is_playlist:
            # Check if this is an auto-generated YouTube Mix (RD...)
            pid = val.get('playlist_id') or ''
            if val.get('is_mix') or pid.startswith('RD') or pid in ('LL', 'WL', 'LM'):
                if video_id:
                    logger.info("Playlist %s is a dynamic YouTube Mix. Queuing single video %s.", pid, video_id)
                    clean_url = f"https://www.youtube.com/watch?v={video_id}"
                    result = dl_service.create_job(clean_url, quality, format_type, title=data.get('title'), thumbnail=data.get('thumbnail'))
                    result['notice'] = "YouTube Mixes cannot be downloaded as a full playlist; queued this video instead."
                    return jsonify({'success': True, 'data': result}), 202
                else:
                    raise InvalidOptionError("YouTube Mix playlists (RD...) are algorithmic queues and cannot be downloaded as full playlists.")

            try:
                # Extract playlist and create batch
                playlist_info = dl_service.extract_playlist(url)
                playlist_items = playlist_info.get('items', [])
                if not playlist_items:
                    raise DownloadError("Playlist appears to be empty or unavailable.")
                result = dl_service.create_batch(
                    playlist_items, quality, format_type, max_size=dl_service.max_playlist_items
                )
                result['playlist_title'] = playlist_info.get('title', 'Unknown Playlist')
                result['is_playlist'] = True
                return jsonify({'success': True, 'data': result}), 202
            except (DownloaderError, DownloadError) as pe:
                # If playlist extraction fails but URL has a video ID, fall back to single video
                if video_id:
                    logger.warning("Playlist extraction failed (%s), falling back to video %s", pe, video_id)
                    clean_url = f"https://www.youtube.com/watch?v={video_id}"
                    result = dl_service.create_job(clean_url, quality, format_type, title=data.get('title'), thumbnail=data.get('thumbnail'))
                    result['notice'] = f"Playlist unavailable ({str(pe)}). Queued this video instead."
                    return jsonify({'success': True, 'data': result}), 202
                raise pe

        title = data.get('title')
        thumbnail = data.get('thumbnail')
        result = dl_service.create_job(url, quality, format_type, title=title, thumbnail=thumbnail)
        return jsonify({'success': True, 'data': result}), 202

    @app.route('/api/batches', methods=['POST'])
    def create_batch():
        """Submit a batch of URLs for download."""
        data = _get_json()
        urls = data.get('urls', [])
        quality = data.get('quality', 'best').strip()
        format_type = data.get('format_type', 'video').strip()

        if not urls or not isinstance(urls, list):
            raise InvalidOptionError("A list of URLs is required.")

        result = dl_service.create_batch(urls, quality, format_type)
        return jsonify({'success': True, 'data': result}), 202

    @app.route('/api/jobs', methods=['GET'])
    def list_jobs():
        """List recent jobs, optionally filtered by comma-separated IDs."""
        ids_param = request.args.get('ids', '').strip()
        if ids_param:
            job_ids = [j.strip() for j in ids_param.split(',') if j.strip()]
            valid_ids = []
            for jid in job_ids[:200]:
                try:
                    uuid.UUID(jid)
                    valid_ids.append(jid)
                except ValueError:
                    continue
            jobs = dl_service.get_jobs_by_ids(valid_ids)
            return jsonify({'success': True, 'data': {'jobs': jobs}})

        limit = min(int(request.args.get('limit', 50)), 200)
        jobs = dl_service.get_all_jobs(limit=limit)
        return jsonify({'success': True, 'data': {'jobs': jobs}})

    @app.route('/api/jobs/<job_id>', methods=['GET'])
    def get_job(job_id):
        """Get the status of a specific job."""
        _validate_uuid(job_id)
        job = dl_service.get_job(job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found.")
        return jsonify({'success': True, 'data': job})

    @app.route('/api/jobs/<job_id>/file', methods=['GET'])
    @app.route('/api/jobs/<job_id>/file/<path:filename>', methods=['GET'])
    def get_file(job_id, filename=None):
        """Serve a completed job's file."""
        _validate_uuid(job_id)
        job = dl_service.get_job(job_id)
        if job is None:
            raise JobNotFoundError("Job not found.")

        if job['status'] != 'COMPLETED':
            return jsonify({
                'success': False,
                'error': {
                    'code': 'NOT_READY',
                    'message': f"Job is not completed. Current status: {job['status']}",
                }
            }), 409

        file_path = dl_service.get_file_path(job_id)
        if file_path is None:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'FILE_NOT_FOUND',
                    'message': 'Download file is no longer available.',
                }
            }), 404

        # Generate a user-friendly download name
        ext = os.path.splitext(file_path)[1]
        if not ext:
            ext = '.mp3' if job.get('format_type') == 'audio' else '.mp4'

        title = job.get('title', 'download') or 'download'
        # Sanitize title for filename
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = re.sub(r'\s+', ' ', safe_title).strip('. ')
        if not safe_title:
            safe_title = 'download'
        download_name = f"{safe_title}{ext}"

        # If a valid clean filename was requested in the URL path, use it
        if filename:
            clean_req = "".join(c for c in os.path.basename(filename) if c.isalnum() or c in (' ', '-', '_', '.')).strip()
            if clean_req:
                if not clean_req.endswith(ext):
                    clean_req = f"{clean_req}{ext}"
                download_name = clean_req

        # Explicit MIME type for media downloads
        mimetypes_map = {
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.mkv': 'video/x-matroska',
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/mp4',
            '.aac': 'audio/aac',
            '.opus': 'audio/opus',
            '.ogg': 'audio/ogg',
            '.flac': 'audio/flac',
            '.wav': 'audio/wav',
        }
        mimetype = mimetypes_map.get(ext.lower(), 'application/octet-stream')

        return send_file(
            file_path,
            as_attachment=True,
            download_name=download_name,
            mimetype=mimetype,
        )

    @app.route('/api/jobs/<job_id>/retry', methods=['POST'])
    def retry_job(job_id):
        """Retry a failed job."""
        _validate_uuid(job_id)
        result = dl_service.retry_job(job_id)
        return jsonify({'success': True, 'data': result}), 202

    @app.route('/api/batches/<batch_id>', methods=['GET'])
    def get_batch(batch_id):
        """Get batch status and job summaries."""
        _validate_uuid(batch_id)
        batch = dl_service.get_batch(batch_id)
        if batch is None:
            raise JobNotFoundError("Batch not found.")
        return jsonify({'success': True, 'data': batch})

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    def _get_json() -> dict:
        """Safely parse JSON request body."""
        if not request.is_json:
            raise InvalidOptionError("Request must be JSON (Content-Type: application/json).")
        data = request.get_json(silent=True)
        if data is None:
            raise InvalidOptionError("Invalid JSON body.")
        return data

    def _validate_uuid(value: str):
        """Basic UUID format validation."""
        import re
        if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', value):
            raise InvalidOptionError("Invalid job ID format.")

    return app


# ---------------------------------------------------------------------------
# Module instance & Main Entry Point
# ---------------------------------------------------------------------------

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n  YT Downloader starting on http://0.0.0.0:{port}\n")
    app.run(host='0.0.0.0', port=port, debug=False)

