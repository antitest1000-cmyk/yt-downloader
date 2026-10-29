"""
build_docs.py — Generate static site for Netlify and GitHub Pages in ./docs
Renders Flask Jinja2 templates to static HTML and copies static assets,
including robots.txt, sitemap.xml, and all canonical SEO routes.
"""

import os
import shutil
import re
from app import create_app
from blog_posts import get_all_posts

def build():
    # Set BASE_URL environment variable to the production domain
    os.environ['BASE_URL'] = 'https://yt-downlooader.netlify.app'
    app = create_app()
    app.config['SERVER_NAME'] = 'localhost'
    
    root_dir = os.path.dirname(os.path.abspath(__file__))
    docs_dir = os.path.join(root_dir, 'docs')
    if os.path.exists(docs_dir):
        shutil.rmtree(docs_dir)
    os.makedirs(docs_dir, exist_ok=True)
    os.makedirs(os.path.join(docs_dir, 'blog'), exist_ok=True)
    
    # Copy static assets
    static_src = os.path.join(root_dir, 'static')
    static_dst = os.path.join(docs_dir, 'static')
    shutil.copytree(static_src, static_dst)
    
    # Also copy favicon to docs root for direct /favicon.svg / /favicon.ico queries
    if os.path.exists(os.path.join(static_src, 'favicon.svg')):
        shutil.copyfile(os.path.join(static_src, 'favicon.svg'), os.path.join(docs_dir, 'favicon.svg'))
    
    # List of routes to export
    routes = [
        ('/', 'index.html'),
        ('/youtube-to-mp3', 'youtube_to_mp3.html'),
        ('/youtube-video-downloader', 'youtube_video_downloader.html'),
        ('/bulk-youtube-to-mp3', 'bulk_youtube_to_mp3.html'),
        ('/bulk-youtube-video-downloader', 'bulk_youtube_video_downloader.html'),
        ('/youtube-playlist-downloader', 'youtube_playlist_downloader.html'),
        ('/youtube-video-info', 'youtube_video_info.html'),
        ('/youtube-to-mp4', 'format_mp4.html'),
        ('/youtube-to-mp4', 'youtube_to_mp4.html'),
        ('/youtube-to-wav', 'format_wav.html'),
        ('/youtube-to-wav', 'youtube_to_wav.html'),
        ('/youtube-to-m4a', 'format_m4a.html'),
        ('/youtube-to-m4a', 'youtube_to_m4a.html'),
        ('/youtube-to-flac', 'format_flac.html'),
        ('/youtube-to-flac', 'youtube_to_flac.html'),
        ('/youtube-4k-downloader', 'format_4k.html'),
        ('/youtube-4k-downloader', 'youtube_4k_downloader.html'),
        ('/ad-free-youtube-downloader', 'ad_free.html'),
        ('/ad-free-youtube-downloader', 'ad_free_youtube_downloader.html'),
        ('/safe-youtube-downloader', 'safe_downloader.html'),
        ('/safe-youtube-downloader', 'safe_youtube_downloader.html'),
        ('/self-hosted-youtube-downloader', 'self_hosted_youtube_downloader.html'),
        ('/yt-dlp-web-ui', 'ytdlp_web_ui.html'),
        ('/yt-dlp-web-ui', 'yt_dlp_web_ui.html'),
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
    
    # Add all blog posts
    for post in get_all_posts():
        slug = post['slug']
        routes.append((f'/blog/{slug}', f'blog/{slug}.html'))
        routes.append((f'/blog/{slug}', f'blog_{slug}.html'))
    
    with app.app_context(), app.test_request_context():
        client = app.test_client()
        for route, filename in routes:
            res = client.get(route)
            if res.status_code == 200:
                html = res.data.decode('utf-8')
                # Adjust root-relative links for subfolder or static hosting
                is_subfolder = '/' in filename and not filename.startswith('/')
                prefix = '../' if is_subfolder else './'
                
                html = re.sub(r'href="/static/', f'href="{prefix}static/', html)
                html = re.sub(r'src="/static/', f'src="{prefix}static/', html)
                html = re.sub(r'href="/"', f'href="{prefix}"', html)
                html = re.sub(r'href="/([a-zA-Z0-9_\-]+)"', rf'href="{prefix}\1.html"', html)
                
                out_path = os.path.join(docs_dir, filename)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"Rendered: {route} -> docs/{filename}")
            else:
                print(f"Skipped {route}: status {res.status_code}")
                
        # Export sitemap.xml
        res_sitemap = client.get('/sitemap.xml')
        if res_sitemap.status_code == 200:
            sitemap_xml = res_sitemap.data.decode('utf-8')
            for dest in [docs_dir, root_dir, os.path.join(root_dir, 'templates')]:
                os.makedirs(dest, exist_ok=True)
                with open(os.path.join(dest, 'sitemap.xml'), 'w', encoding='utf-8') as f:
                    f.write(sitemap_xml)
            print("Rendered: /sitemap.xml -> docs/sitemap.xml & root & templates")
        
        # Export robots.txt
        res_robots = client.get('/robots.txt')
        if res_robots.status_code == 200:
            robots_txt = res_robots.data.decode('utf-8')
            for dest in [docs_dir, root_dir, os.path.join(root_dir, 'templates')]:
                os.makedirs(dest, exist_ok=True)
                with open(os.path.join(dest, 'robots.txt'), 'w', encoding='utf-8') as f:
                    f.write(robots_txt)
            print("Rendered: /robots.txt -> docs/robots.txt & root & templates")

    # Create .nojekyll in docs so GitHub Pages / static hosts don't ignore folders
    with open(os.path.join(docs_dir, '.nojekyll'), 'w') as f:
        f.write('')
        
    # Also copy the rendered index.html to root_dir/index.html so if Netlify is deployed at root,
    # it immediately serves the rendered HTML rather than templates/
    shutil.copyfile(os.path.join(docs_dir, 'index.html'), os.path.join(root_dir, 'index.html'))
    print("Copied rendered index.html to project root index.html")
    
    print("Static build complete for Netlify & GitHub Pages!")

if __name__ == '__main__':
    build()
