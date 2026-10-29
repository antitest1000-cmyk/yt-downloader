"""
build_docs.py — Generate static site for Netlify and GitHub Pages in ./docs and ./templates
Renders Flask Jinja2 templates to complete static HTML and copies all CSS, JS,
static assets, robots.txt, and sitemap.xml into both ./docs and ./templates.
Generates BOTH hyphenated and underscored HTML files so links never 404!
"""

import os
import shutil
import re
from blog_posts import get_all_posts

def build():
    os.environ['BASE_URL'] = 'https://yt-downlooader.netlify.app'
    
    root_dir = os.path.dirname(os.path.abspath(__file__))
    docs_dir = os.path.join(root_dir, 'docs')
    templates_dir = os.path.join(root_dir, 'templates')
    static_src = os.path.join(root_dir, 'static')
    
    # 1. Ensure templates_jinja has the pristine Jinja source files
    jinja_dir = os.path.join(root_dir, 'templates_jinja')
    if not os.path.exists(jinja_dir):
        shutil.copytree(templates_dir, jinja_dir)
        print("Backed up Jinja templates to ./templates_jinja")
    
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
    
    # Copy favicon to docs root
    if os.path.exists(os.path.join(static_src, 'favicon.svg')):
        shutil.copyfile(os.path.join(static_src, 'favicon.svg'), os.path.join(docs_dir, 'favicon.svg'))
    
    # Multi-alias route mappings (both hyphenated and underscored)
    route_mappings = [
        ('/', ['index.html']),
        ('/youtube-to-mp3', ['youtube-to-mp3.html', 'youtube_to_mp3.html', 'youtube to mp3.html']),
        ('/youtube-video-downloader', ['youtube-video-downloader.html', 'youtube_video_downloader.html', 'video_downloader.html', 'youtube video downloader.html']),
        ('/bulk-youtube-to-mp3', ['bulk-youtube-to-mp3.html', 'bulk_youtube_to_mp3.html', 'bulk_audio.html', 'bulk youtube to mp3.html']),
        ('/bulk-youtube-video-downloader', ['bulk-youtube-video-downloader.html', 'bulk_youtube_video_downloader.html', 'bulk_video.html', 'bulk youtube video downloader.html']),
        ('/youtube-playlist-downloader', ['youtube-playlist-downloader.html', 'youtube_playlist_downloader.html', 'playlist_downloader.html', 'youtube playlist downloader.html']),
        ('/youtube-video-info', ['youtube-video-info.html', 'youtube_video_info.html', 'video_info.html', 'youtube video info.html']),
        ('/youtube-to-mp4', ['youtube-to-mp4.html', 'youtube_to_mp4.html', 'format_mp4.html', 'youtube to mp4.html']),
        ('/youtube-to-wav', ['youtube-to-wav.html', 'youtube_to_wav.html', 'format_wav.html', 'youtube to wav.html']),
        ('/youtube-to-m4a', ['youtube-to-m4a.html', 'youtube_to_m4a.html', 'format_m4a.html', 'youtube to m4a.html']),
        ('/youtube-to-flac', ['youtube-to-flac.html', 'youtube_to_flac.html', 'format_flac.html', 'youtube to flac.html']),
        ('/youtube-4k-downloader', ['youtube-4k-downloader.html', 'youtube_4k_downloader.html', 'format_4k.html', 'youtube 4k downloader.html']),
        ('/ad-free-youtube-downloader', ['ad-free-youtube-downloader.html', 'ad_free_youtube_downloader.html', 'ad_free.html']),
        ('/safe-youtube-downloader', ['safe-youtube-downloader.html', 'safe_youtube_downloader.html', 'safe_downloader.html']),
        ('/self-hosted-youtube-downloader', ['self-hosted-youtube-downloader.html', 'self_hosted_youtube_downloader.html', 'self_host.html']),
        ('/yt-dlp-web-ui', ['yt-dlp-web-ui.html', 'yt_dlp_web_ui.html', 'ytdlp_web_ui.html']),
        ('/supported-sites', ['supported-sites.html', 'supported_sites.html']),
        ('/how-it-works', ['how-it-works.html', 'how_it_works.html']),
        ('/faq', ['faq.html']),
        ('/about', ['about.html']),
        ('/contact', ['contact.html']),
        ('/privacy', ['privacy.html']),
        ('/terms', ['terms.html']),
        ('/dmca', ['dmca.html']),
        ('/fair-use', ['fair-use.html', 'fair_use.html']),
        ('/changelog', ['changelog.html']),
        ('/site-map.html', ['site-map.html', 'site_map.html']),
        ('/blog', ['blog.html']),
    ]
    
    # Add blog posts
    for post in get_all_posts():
        slug = post['slug']
        route_mappings.append((f'/blog/{slug}', [f'blog/{slug}.html', f'blog_{slug}.html', f'blog-{slug}.html']))
    
    # Flatten into route -> filename pairs
    routes = []
    for r, fnames in route_mappings:
        for fn in fnames:
            routes.append((r, fn))
    
    with app.app_context(), app.test_request_context():
        client = app.test_client()
        for route, filename in routes:
            res = client.get(route)
            if res.status_code == 200:
                html = res.data.decode('utf-8')
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
    print("Exported sitemap.xml & robots.txt")

    # Create .nojekyll in docs
    with open(os.path.join(docs_dir, '.nojekyll'), 'w') as f:
        f.write('')
        
    # Copy rendered index.html to root_dir
    shutil.copyfile(os.path.join(docs_dir, 'index.html'), os.path.join(root_dir, 'index.html'))
    
    # -------------------------------------------------------------
    # SYNC ALL FILES TO TEMPLATES
    # -------------------------------------------------------------
    print("Syncing all assets and both hyphenated & underscored HTML to ./templates ...")
    
    templates_static = os.path.join(templates_dir, 'static')
    if os.path.exists(templates_static):
        shutil.rmtree(templates_static)
    shutil.copytree(static_src, templates_static)
    
    templates_css = os.path.join(templates_dir, 'css')
    if os.path.exists(templates_css):
        shutil.rmtree(templates_css)
    shutil.copytree(os.path.join(static_src, 'css'), templates_css)
    
    templates_js = os.path.join(templates_dir, 'js')
    if os.path.exists(templates_js):
        shutil.rmtree(templates_js)
    shutil.copytree(os.path.join(static_src, 'js'), templates_js)
    
    if os.path.exists(os.path.join(static_src, 'favicon.svg')):
        shutil.copyfile(os.path.join(static_src, 'favicon.svg'), os.path.join(templates_dir, 'favicon.svg'))
        
    for item in os.listdir(docs_dir):
        src_item = os.path.join(docs_dir, item)
        dst_item = os.path.join(templates_dir, item)
        if os.path.isfile(src_item):
            shutil.copyfile(src_item, dst_item)
        elif os.path.isdir(src_item) and item not in ('static', 'css', 'js'):
            if os.path.exists(dst_item):
                shutil.rmtree(dst_item)
            shutil.copytree(src_item, dst_item)
            
    # Comprehensive Netlify Redirects for all spelling / hyphen / underscore / space variations
    redirects_content = """# Netlify Redirects
/youtube-to-mp3.html /youtube-to-mp3.html 200
/youtube_to_mp3.html /youtube-to-mp3.html 200
/youtube%20to%20mp3.html /youtube-to-mp3.html 200
/youtube%20to%20mp3 /youtube-to-mp3.html 200
/youtube-to-mp3 /youtube-to-mp3.html 200

/youtube-video-downloader.html /youtube-video-downloader.html 200
/youtube_video_downloader.html /youtube-video-downloader.html 200
/video_downloader.html /youtube-video-downloader.html 200
/youtube%20video%20downloader.html /youtube-video-downloader.html 200
/youtube-video-downloader /youtube-video-downloader.html 200

/bulk-youtube-to-mp3.html /bulk-youtube-to-mp3.html 200
/bulk_youtube_to_mp3.html /bulk-youtube-to-mp3.html 200
/bulk_audio.html /bulk-youtube-to-mp3.html 200
/bulk%20youtube%20to%20mp3.html /bulk-youtube-to-mp3.html 200
/bulk-youtube-to-mp3 /bulk-youtube-to-mp3.html 200

/bulk-youtube-video-downloader.html /bulk-youtube-video-downloader.html 200
/bulk_youtube_video_downloader.html /bulk-youtube-video-downloader.html 200
/bulk_video.html /bulk-youtube-video-downloader.html 200
/bulk-youtube-video-downloader /bulk-youtube-video-downloader.html 200

/youtube-playlist-downloader.html /youtube-playlist-downloader.html 200
/youtube_playlist_downloader.html /youtube-playlist-downloader.html 200
/playlist_downloader.html /youtube-playlist-downloader.html 200
/youtube-playlist-downloader /youtube-playlist-downloader.html 200

/youtube-video-info.html /youtube-video-info.html 200
/youtube_video_info.html /youtube-video-info.html 200
/video_info.html /youtube-video-info.html 200
/youtube-video-info /youtube-video-info.html 200

/youtube-to-mp4.html /youtube-to-mp4.html 200
/youtube_to_mp4.html /youtube-to-mp4.html 200
/format_mp4.html /youtube-to-mp4.html 200
/youtube-to-mp4 /youtube-to-mp4.html 200

/youtube-to-wav.html /youtube-to-wav.html 200
/youtube_to_wav.html /youtube-to-wav.html 200
/format_wav.html /youtube-to-wav.html 200
/youtube-to-wav /youtube-to-wav.html 200

/youtube-to-m4a.html /youtube-to-m4a.html 200
/youtube_to_m4a.html /youtube-to-m4a.html 200
/format_m4a.html /youtube-to-m4a.html 200
/youtube-to-m4a /youtube-to-m4a.html 200

/youtube-to-flac.html /youtube-to-flac.html 200
/youtube_to_flac.html /youtube-to-flac.html 200
/format_flac.html /youtube-to-flac.html 200
/youtube-to-flac /youtube-to-flac.html 200

/youtube-4k-downloader.html /youtube-4k-downloader.html 200
/youtube_4k_downloader.html /youtube-4k-downloader.html 200
/format_4k.html /youtube-4k-downloader.html 200
/youtube-4k-downloader /youtube-4k-downloader.html 200

/ad-free-youtube-downloader.html /ad-free-youtube-downloader.html 200
/ad_free_youtube_downloader.html /ad-free-youtube-downloader.html 200
/ad_free.html /ad-free-youtube-downloader.html 200
/ad-free-youtube-downloader /ad-free-youtube-downloader.html 200

/safe-youtube-downloader.html /safe-youtube-downloader.html 200
/safe_youtube_downloader.html /safe-youtube-downloader.html 200
/safe_downloader.html /safe-youtube-downloader.html 200
/safe-youtube-downloader /safe-youtube-downloader.html 200

/self-hosted-youtube-downloader.html /self-hosted-youtube-downloader.html 200
/self_hosted_youtube_downloader.html /self-hosted-youtube-downloader.html 200
/self_host.html /self-hosted-youtube-downloader.html 200
/self-hosted-youtube-downloader /self-hosted-youtube-downloader.html 200

/yt-dlp-web-ui.html /yt-dlp-web-ui.html 200
/yt_dlp_web_ui.html /yt-dlp-web-ui.html 200
/ytdlp_web_ui.html /yt-dlp-web-ui.html 200
/yt-dlp-web-ui /yt-dlp-web-ui.html 200

/supported-sites.html /supported-sites.html 200
/supported_sites.html /supported-sites.html 200
/supported-sites /supported-sites.html 200

/how-it-works.html /how-it-works.html 200
/how_it_works.html /how-it-works.html 200
/how-it-works /how-it-works.html 200

/faq.html /faq.html 200
/faq /faq.html 200

/about.html /about.html 200
/about /about.html 200

/contact.html /contact.html 200
/contact /contact.html 200

/privacy.html /privacy.html 200
/privacy /privacy.html 200

/terms.html /terms.html 200
/terms /terms.html 200

/dmca.html /dmca.html 200
/dmca /dmca.html 200

/fair-use.html /fair-use.html 200
/fair_use.html /fair-use.html 200
/fair-use /fair-use.html 200

/changelog.html /changelog.html 200
/changelog /changelog.html 200

/site-map.html /site-map.html 200
/site_map.html /site-map.html 200

/blog.html /blog.html 200
/blog /blog.html 200

/blog/:slug /blog/:slug.html 200

/api/* https://yt-downloader-backend-n68l.onrender.com/api/:splat 200!
"""
    # Write _redirects to templates, docs, and root
    for dest in [templates_dir, docs_dir, root_dir]:
        with open(os.path.join(dest, '_redirects'), 'w', encoding='utf-8') as f:
            f.write(redirects_content)
        
    with open(os.path.join(templates_dir, 'netlify.toml'), 'w', encoding='utf-8') as f:
        with open(os.path.join(root_dir, 'netlify.toml'), 'r', encoding='utf-8') as rf:
            f.write(rf.read().replace('publish = "templates"', 'publish = "."'))
            
    with open(os.path.join(templates_dir, '.nojekyll'), 'w', encoding='utf-8') as f:
        f.write('')
        
    # Also mirror docs into templates/docs
    templates_docs = os.path.join(templates_dir, 'docs')
    if os.path.exists(templates_docs):
        shutil.rmtree(templates_docs)
    shutil.copytree(docs_dir, templates_docs)

    print("SUCCESS: All hyphen, underscore, and space variations generated and synced!")

if __name__ == '__main__':
    build()
