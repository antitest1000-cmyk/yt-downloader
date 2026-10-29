"""
build_docs.py — Generate static site for Netlify and GitHub Pages in ./docs and ./templates
Renders Flask Jinja2 templates to complete static HTML and copies all CSS, JS,
static assets, robots.txt, and sitemap.xml into both ./docs and ./templates
so that deploying EITHER folder to Netlify works instantly with full styling!
"""

import os
import shutil
import re
from blog_posts import get_all_posts

def build():
    # Set BASE_URL environment variable to the production domain
    os.environ['BASE_URL'] = 'https://yt-downlooader.netlify.app'
    
    root_dir = os.path.dirname(os.path.abspath(__file__))
    docs_dir = os.path.join(root_dir, 'docs')
    templates_dir = os.path.join(root_dir, 'templates')
    static_src = os.path.join(root_dir, 'static')
    
    # 1. First ensure templates_jinja has the pristine Jinja source files to render from
    jinja_dir = os.path.join(root_dir, 'templates_jinja')
    if not os.path.exists(jinja_dir):
        shutil.copytree(templates_dir, jinja_dir)
        print("Backed up Jinja templates to ./templates_jinja")
    
    # Use templates_jinja for creating the Flask app so rendering uses the pure Jinja files
    from app import create_app
    app = create_app()
    app.template_folder = jinja_dir
    app.jinja_loader.searchpath = [jinja_dir]
    app.config['SERVER_NAME'] = 'localhost'
    
    if os.path.exists(docs_dir):
        shutil.rmtree(docs_dir)
    os.makedirs(docs_dir, exist_ok=True)
    os.makedirs(os.path.join(docs_dir, 'blog'), exist_ok=True)
    
    # Copy static assets to docs
    static_dst = os.path.join(docs_dir, 'static')
    shutil.copytree(static_src, static_dst)
    
    # Also copy favicon to docs root
    if os.path.exists(os.path.join(static_src, 'favicon.svg')):
        shutil.copyfile(os.path.join(static_src, 'favicon.svg'), os.path.join(docs_dir, 'favicon.svg'))
    
    # List of routes to export
    routes = [
        ('/', 'index.html'),
        ('/youtube-to-mp3', 'youtube_to_mp3.html'),
        ('/youtube-video-downloader', 'youtube_video_downloader.html'),
        ('/youtube-video-downloader', 'video_downloader.html'),
        ('/bulk-youtube-to-mp3', 'bulk_youtube_to_mp3.html'),
        ('/bulk-youtube-to-mp3', 'bulk_audio.html'),
        ('/bulk-youtube-video-downloader', 'bulk_youtube_video_downloader.html'),
        ('/bulk-youtube-video-downloader', 'bulk_video.html'),
        ('/youtube-playlist-downloader', 'youtube_playlist_downloader.html'),
        ('/youtube-playlist-downloader', 'playlist_downloader.html'),
        ('/youtube-video-info', 'youtube_video_info.html'),
        ('/youtube-video-info', 'video_info.html'),
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
        ('/self-hosted-youtube-downloader', 'self_host.html'),
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
        sitemap_xml = res_sitemap.data.decode('utf-8') if res_sitemap.status_code == 200 else ''
        
        # Export robots.txt
        res_robots = client.get('/robots.txt')
        robots_txt = res_robots.data.decode('utf-8') if res_robots.status_code == 200 else ''

    # Save sitemap & robots in docs, root, and templates
    for dest in [docs_dir, root_dir, templates_dir]:
        os.makedirs(dest, exist_ok=True)
        if sitemap_xml:
            with open(os.path.join(dest, 'sitemap.xml'), 'w', encoding='utf-8') as f:
                f.write(sitemap_xml)
        if robots_txt:
            with open(os.path.join(dest, 'robots.txt'), 'w', encoding='utf-8') as f:
                f.write(robots_txt)
    print("Exported sitemap.xml & robots.txt to ./docs, ./templates, and ./")

    # Create .nojekyll in docs
    with open(os.path.join(docs_dir, '.nojekyll'), 'w') as f:
        f.write('')
        
    # Copy rendered index.html to root_dir/index.html
    shutil.copyfile(os.path.join(docs_dir, 'index.html'), os.path.join(root_dir, 'index.html'))
    print("Copied rendered index.html to project root index.html")
    
    # -------------------------------------------------------------
    # CRITICAL: SYNC ALL CSS, JS, ASSETS & RENDERED HTML TO TEMPLATES
    # -------------------------------------------------------------
    print("Syncing all CSS, JS, images, and pre-rendered HTML into ./templates ...")
    
    # 1. Copy static/ to templates/static/
    templates_static = os.path.join(templates_dir, 'static')
    if os.path.exists(templates_static):
        shutil.rmtree(templates_static)
    shutil.copytree(static_src, templates_static)
    
    # 2. Also copy css/ and js/ directly into templates/css/ and templates/js/
    templates_css = os.path.join(templates_dir, 'css')
    if os.path.exists(templates_css):
        shutil.rmtree(templates_css)
    shutil.copytree(os.path.join(static_src, 'css'), templates_css)
    
    templates_js = os.path.join(templates_dir, 'js')
    if os.path.exists(templates_js):
        shutil.rmtree(templates_js)
    shutil.copytree(os.path.join(static_src, 'js'), templates_js)
    
    # 3. Copy favicon.svg to templates/favicon.svg
    if os.path.exists(os.path.join(static_src, 'favicon.svg')):
        shutil.copyfile(os.path.join(static_src, 'favicon.svg'), os.path.join(templates_dir, 'favicon.svg'))
        
    # 4. Copy all rendered HTML pages into templates/
    for item in os.listdir(docs_dir):
        src_item = os.path.join(docs_dir, item)
        dst_item = os.path.join(templates_dir, item)
        if os.path.isfile(src_item) and item.endswith('.html'):
            shutil.copyfile(src_item, dst_item)
        elif os.path.isdir(src_item) and item not in ('static', 'css', 'js'):
            if os.path.exists(dst_item):
                shutil.rmtree(dst_item)
            shutil.copytree(src_item, dst_item)
            
    # 5. Create Netlify _redirects and netlify.toml inside templates/
    redirects_content = """# Netlify Redirects for templates publish folder
/youtube-to-mp3 /youtube_to_mp3.html 200
/youtube-video-downloader /video_downloader.html 200
/bulk-youtube-to-mp3 /bulk_audio.html 200
/bulk-youtube-video-downloader /bulk_video.html 200
/youtube-playlist-downloader /playlist_downloader.html 200
/youtube-video-info /video_info.html 200
/youtube-to-mp4 /format_mp4.html 200
/youtube-to-wav /format_wav.html 200
/youtube-to-m4a /format_m4a.html 200
/youtube-to-flac /format_flac.html 200
/youtube-4k-downloader /format_4k.html 200
/ad-free-youtube-downloader /ad_free.html 200
/safe-youtube-downloader /safe_downloader.html 200
/self-hosted-youtube-downloader /self_host.html 200
/yt-dlp-web-ui /ytdlp_web_ui.html 200
/supported-sites /supported_sites.html 200
/how-it-works /how_it_works.html 200
/faq /faq.html 200
/about /about.html 200
/contact /contact.html 200
/privacy /privacy.html 200
/terms /terms.html 200
/dmca /dmca.html 200
/fair-use /fair_use.html 200
/changelog /changelog.html 200
/site-map.html /site_map.html 200
/blog /blog.html 200
/blog/:slug /blog/:slug.html 200
/api/* https://yt-downloader-backend-n68l.onrender.com/api/:splat 200!
"""
    with open(os.path.join(templates_dir, '_redirects'), 'w', encoding='utf-8') as f:
        f.write(redirects_content)
        
    shutil.copyfile(os.path.join(root_dir, 'netlify.toml'), os.path.join(templates_dir, 'netlify.toml'))
    with open(os.path.join(templates_dir, '.nojekyll'), 'w', encoding='utf-8') as f:
        f.write('')

    print("SUCCESS: templates/ folder is now fully self-contained with all CSS, JS, assets, and compiled HTML ready for instant Netlify push!")

if __name__ == '__main__':
    build()
