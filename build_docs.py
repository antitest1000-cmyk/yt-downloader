"""
build_docs.py — Generate static site for GitHub Pages in ./docs
Renders Flask Jinja2 templates to static HTML and copies static assets.
"""

import os
import shutil
import re
from app import create_app

def build():
    app = create_app()
    app.config['SERVER_NAME'] = 'localhost'
    
    docs_dir = os.path.join(os.path.dirname(__file__), 'docs')
    if os.path.exists(docs_dir):
        shutil.rmtree(docs_dir)
    os.makedirs(docs_dir, exist_ok=True)
    
    # Copy static assets
    static_src = os.path.join(os.path.dirname(__file__), 'static')
    static_dst = os.path.join(docs_dir, 'static')
    shutil.copytree(static_src, static_dst)
    
    # List of routes to export
    routes = [
        ('/', 'index.html'),
        ('/youtube-to-mp3', 'youtube_to_mp3.html'),
        ('/youtube-video-downloader', 'youtube_video_downloader.html'),
        ('/bulk-youtube-to-mp3', 'bulk_youtube_to_mp3.html'),
        ('/bulk-youtube-video-downloader', 'bulk_youtube_video_downloader.html'),
        ('/youtube-playlist-downloader', 'youtube_playlist_downloader.html'),
        ('/youtube-video-info', 'youtube_video_info.html'),
        ('/self-hosted-youtube-downloader', 'self_hosted_youtube_downloader.html'),
        ('/supported-sites', 'supported_sites.html'),
        ('/how-it-works', 'how_it_works.html'),
        ('/faq', 'faq.html'),
        ('/about', 'about.html'),
        ('/contact', 'contact.html'),
        ('/privacy', 'privacy.html'),
        ('/terms', 'terms.html'),
        ('/dmca', 'dmca.html'),
        ('/fair-use', 'fair_use.html'),
        ('/changelog', 'changelog.html'),
        ('/site-map.html', 'site_map.html'),
        ('/blog', 'blog.html'),
    ]
    
    with app.app_context(), app.test_request_context():
        client = app.test_client()
        for route, filename in routes:
            res = client.get(route)
            if res.status_code == 200:
                html = res.data.decode('utf-8')
                # Adjust root-relative links to relative links for GitHub Pages subdirectory compatibility
                # e.g. /static/ -> static/ or ./static/
                html = re.sub(r'href="/static/', 'href="./static/', html)
                html = re.sub(r'src="/static/', 'src="./static/', html)
                html = re.sub(r'href="/"', 'href="./"', html)
                html = re.sub(r'href="/([a-zA-Z0-9_\-]+)"', r'href="./\1.html"', html)
                
                out_path = os.path.join(docs_dir, filename)
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"Rendered: {route} -> docs/{filename}")
            else:
                print(f"Skipped {route}: status {res.status_code}")
                
    # Create .nojekyll in docs so GitHub Pages doesn't ignore folders or process underscores
    with open(os.path.join(docs_dir, '.nojekyll'), 'w') as f:
        f.write('')
    print("Static build complete in ./docs for GitHub Pages!")

if __name__ == '__main__':
    build()
