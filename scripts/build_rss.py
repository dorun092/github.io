import os, pathlib, datetime, textwrap, re, urllib.parse
import feedparser
from html import escape

BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
RSS_URL = os.environ.get("RSS_URL", "https://rss.blog.naver.com/do_run_.xml")
SITE_TITLE = os.environ.get("SITE_TITLE", "네이버 블로그 최신 글")
SITE_DESC = os.environ.get("SITE_DESC", "네이버 블로그 최신 글 모음 (자동 갱신)")
SITE_META = os.environ.get("SITE_META", "")
MAX_ITEMS = int(os.environ.get("MAX_ITEMS", "40"))

# index 링크 대상: naver(기본) | local
INDEX_LINK_TARGET = os.environ.get("INDEX_LINK_TARGET", "naver").lower()

OUT_DIR = pathlib.Path("dist")
POSTS_DIR = OUT_DIR / "posts"

# ---------- helpers ----------

def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text or "post"

def to_iso8601(dt_struct) -> str:
    """feedparser의 *_parsed 를 ISO8601Z로 변환."""
    if not dt_struct:
        return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    dt = datetime.datetime(*dt_struct[:6], tzinfo=datetime.timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")

def to_mobile_naver_url(url: str) -> str:
    """
    네이버 블로그 링크를 모바일 정규화:
    - https://blog.naver.com/do_run_/223... -> https://m.blog.naver.com/do_run_/223...
    - https://blog.naver.com/PostView.nhn?blogId=do_run_&logNo=223... -> https://m.blog.naver.com/do_run_/223...
    - 이미 m.blog.naver.com 이면 그대로 유지
    """
    if not url:
        return url
    parsed = urllib.parse.urlparse(url)

    # 이미 모바일이면 그대로
    if parsed.netloc.startswith("m.blog.naver.com"):
        return url

    # 일반 형식: /{blogId}/{logNo}
    m1 = re.match(r"^/([^/]+)/(\d+)$", parsed.path)
    if parsed.netloc.startswith("blog.naver.com") and m1:
        blog_id, log_no = m1.groups()
        return f"https://m.blog.naver.com/{blog_id}/{log_no}"

    # PostView.nhn 형식
    if parsed.netloc.startswith("blog.naver.com") and parsed.path.lower().endswith("postview.nhn"):
        qs = urllib.parse.parse_qs(parsed.query or "")
        blog_id = (qs.get("blogId") or qs.get("blogid") or [""])[0]
        log_no  = (qs.get("logNo")  or qs.get("logno")  or [""])[0]
        if blog_id and log_no:
            return f"https://m.blog.naver.com/{blog_id}/{log_no}"

    # 그 외는 netloc만 m.으로 바꿔 시도
    if parsed.netloc.startswith("blog.naver.com"):
        return urllib.parse.urlunparse(parsed._replace(netloc="m.blog.naver.com"))

    return url

# ---------- renderers ----------

def render_index(entries, item_pages):
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lis = []
    for e, page_path in item_pages:
        title = escape(e.get("title", "제목 없음"))
        naver_link = to_mobile_naver_url(e.get("link", ""))
        local_url = f"{BASE_URL}/{page_path}"
        published = e.get("published", "") or e.get("updated", "")
        href = naver_link if INDEX_LINK_TARGET == "naver" else local_url
        lis.append(
            f'<li><a href="{href}">{title}</a>'
            + (f' <span class="date">{escape(published)}</span>' if published else "")
            + (' <span style="color:#999;">·</span> '
               f'<a href="{local_url}" style="font-size:.9em;">mirror</a>' if INDEX_LINK_TARGET=="naver" else
               f' <span style="color:#999;">·</span> <a href="{naver_link}" style="font-size:.9em;">원문</a>')
            + '</li>'
        )
    return textwrap.dedent(f"""\
    <!doctype html>
    <html lang="ko">
    <head>
      <meta charset="utf-8">
      {SITE_META}
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>{escape(SITE_TITLE)}</title>
      <meta name="description" content="{escape(SITE_DESC)}">
      <style>
        body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:2rem;line-height:1.6}}
        h1{{margin-bottom:.25rem}}
        .sub{{color:#666;margin-bottom:1.5rem}}
        ul{{padding-left:1.2rem}}
        li{{margin:.4rem 0}}
        .date{{color:#888;font-size:.9em}}
        footer{{margin-top:2rem;color:#888;font-size:.9em}}
      </style>
    </head>
    <body>
      <h1>{escape(SITE_TITLE)}</h1>
      <div class="sub">{escape(SITE_DESC)}</div>
      <ul>
        {''.join(lis) if lis else '<li>피드 항목이 없습니다.</li>'}
      </ul>
      <footer>Last build: {now} · Source RSS: <a href="{escape(RSS_URL)}">{escape(RSS_URL)}</a></footer>
    </body>
    </html>
    """)

def render_item_page(e):
    title = escape(e.get("title", "제목 없음"))
    naver_link = to_mobile_naver_url(e.get("link", "#"))
    summary = e.get("summary", "") or e.get("description", "") or ""
    summary = escape(summary)
    published = e.get("published", "") or e.get("updated", "")

    return textwrap.dedent(f"""\
    <!doctype html>
    <html lang="ko">
    <head>
      <meta charset="utf-8">
      {SITE_META}
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>{title}</title>
      <!-- 정본: 네이버 모바일 버전 -->
      <link rel="canonical" href="{naver_link}">
      <meta name="robots" content="index,follow">
      <meta name="description" content="{title}">
      <style>
        body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:2rem;line-height:1.7}}
        .meta{{color:#666;margin:.25rem 0 1rem}}
        a.btn{{display:inline-block;margin-top:1rem;text-decoration:none;padding:.6rem .9rem;border:1px solid #ccc;border-radius:.5rem}}
      </style>
    </head>
    <body>
      <h1>{title}</h1>
      <div class="meta">{escape(published)}</div>
      <div class="content">{summary or "요약 없음"}</div>
      <p><a class="btn" href="{naver_link}">원문(네이버 블로그, 모바일) 보기 →</a></p>
    </body>
    </html>
    """)

# ---------- build ----------

def build():
    assert BASE_URL, "BASE_URL 환경변수를 설정하세요. 예: https://dorun092.github.io"
    feed = feedparser.parse(RSS_URL)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    POSTS_DIR.mkdir(parents=True, exist_ok=True)

    # 항목별 로컬 페이지 생성
    item_pages = []  # (entry, "posts/slug.html")
    seen_slugs = set()
    for e in feed.entries[:MAX_ITEMS]:
        base = slugify(e.get("title") or "")
        link = e.get("link", "")
        q = urllib.parse.urlparse(link)
        id_hint = re.findall(r"\d{6,}", q.path + "?" + (q.query or ""))
        if id_hint:
            base = f"{base}-{id_hint[-1]}"
        slug = base or "post"
        i = 2
        while slug in seen_slugs:
            slug = f"{base}-{i}"
            i += 1
        seen_slugs.add(slug)

        page_rel_path = f"posts/{slug}.html"
        (OUT_DIR / page_rel_path).write_text(render_item_page(e), encoding="utf-8")
        item_pages.append((e, page_rel_path))

    # index.html 생성
    (OUT_DIR / "index.html").write_text(render_index(feed.entries, item_pages), encoding="utf-8")

    # robots.txt 생성 (sitemap 위치 알리기만)
    (OUT_DIR / "robots.txt").write_text(f"Sitemap: {BASE_URL}/sitemap.xml\n", encoding="utf-8")

    # sitemap.xml 생성 (내 사이트의 페이지들만)
    now_iso = datetime.datetime.utcnow().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    url_elems = [f"<url><loc>{BASE_URL}/</loc><lastmod>{now_iso}</lastmod><changefreq>hourly</changefreq><priority>1.0</priority></url>"]
    for e, page_path in item_pages:
        lastmod = to_iso8601(e.get("published_parsed") or e.get("updated_parsed"))
        loc = f"{BASE_URL}/{page_path}"
        url_elems.append(f"<url><loc>{loc}</loc><lastmod>{lastmod}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>")
    sitemap = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n" \
              "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n" \
              + "\n".join(url_elems) + "\n</urlset>\n"
    (OUT_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    (OUT_DIR / "sitemap.html").write_text(textwrap.dedent(f"""\
        <!doctype html><html><head>
        <meta http-equiv="refresh" content="0; url={BASE_URL}/sitemap.xml">
        <title>Sitemap Redirect</title>
        </head><body>Redirecting to <a href="{BASE_URL}/sitemap.xml">sitemap.xml</a>...</body></html>
    """), encoding="utf-8")

if __name__ == "__main__":
    build()