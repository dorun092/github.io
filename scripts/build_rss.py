import os, pathlib, datetime, textwrap, re, urllib.parse
import feedparser
from html import escape

BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
RSS_URL = os.environ.get("RSS_URL", "https://rss.blog.naver.com/do_run_.xml")
SITE_TITLE = os.environ.get("SITE_TITLE", "네이버 블로그 최신 글")
SITE_DESC = os.environ.get("SITE_DESC", "네이버 블로그 최신 글 모음 (자동 갱신)")
SITE_META = os.environ.get("SITE_META", "")
MAX_ITEMS = int(os.environ.get("MAX_ITEMS", "40"))

OUT_DIR = pathlib.Path("dist")
POSTS_DIR = OUT_DIR / "posts"

def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text or "post"

def to_iso8601(dt_struct) -> str:
    """feedparser의 published_parsed 등을 ISO8601로 변환 (UTC로 표기)."""
    if not dt_struct:
        return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    dt = datetime.datetime(*dt_struct[:6], tzinfo=datetime.timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")

def render_index(entries, item_pages):
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lis = []
    for e, page_path in item_pages:
        title = escape(e.get("title", "제목 없음"))
        local_url = f"{BASE_URL}/{page_path}"
        published = e.get("published", "") or e.get("updated", "")
        lis.append(f'<li><a href="{local_url}">{title}</a>'
                   + (f' <span class="date">{escape(published)}</span>' if published else "")
                   + '</li>')
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
    link = escape(e.get("link", "#"))
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
      <link rel="canonical" href="{link}">
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
      <p><a class="btn" href="{link}">원문(네이버 블로그) 보기 →</a></p>
    </body>
    </html>
    """)

def build():
    feed = feedparser.parse(RSS_URL)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    POSTS_DIR.mkdir(parents=True, exist_ok=True)

    # 항목별 로컬 페이지 생성
    item_pages = []  # (entry, "posts/slug.html")
    seen_slugs = set()
    for e in feed.entries[:MAX_ITEMS]:
        # slug는 가능한 한 고유하게: title + id/link의 key 파라미터 등
        base = slugify(e.get("title") or "")
        # 링크에서 숫자 id 같은 게 있으면 붙여서 충돌 최소화
        link = e.get("link", "")
        q = urllib.parse.urlparse(link)
        id_hint = re.findall(r"\d{6,}", q.path + "?" + (q.query or ""))
        if id_hint:
            base = f"{base}-{id_hint[-1]}"
        slug = base or "post"
        # 중복 방지
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

    # robots.txt 생성 (sitemap 위치 알리기)
    if BASE_URL:
        (OUT_DIR / "robots.txt").write_text(f"Sitemap: {BASE_URL}/sitemap.xml\n", encoding="utf-8")

    # sitemap.xml 생성 (내 사이트의 페이지들만)
    url_elems = []
    # 루트(index)
    now_iso = datetime.datetime.utcnow().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    url_elems.append(f"<url><loc>{BASE_URL}/</loc><lastmod>{now_iso}</lastmod><changefreq>hourly</changefreq><priority>1.0</priority></url>")
    # 각 항목 페이지
    for e, page_path in item_pages:
        lastmod = to_iso8601(e.get("published_parsed") or e.get("updated_parsed"))
        loc = f"{BASE_URL}/{page_path}"
        url_elems.append(f"<url><loc>{loc}</loc><lastmod>{lastmod}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>")

    sitemap = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n" \
              "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n" \
              + "\n".join(url_elems) + "\n</urlset>\n"
    (OUT_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")

if __name__ == "__main__":
    assert BASE_URL, "BASE_URL 환경변수를 설정하세요. 예: https://dorun092.github.io"
    build()