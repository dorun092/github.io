import os, pathlib, datetime, textwrap
import feedparser
from html import escape

RSS_URL = os.environ.get("RSS_URL", "https://rss.blog.naver.com/네이버아이디.xml")
SITE_TITLE = os.environ.get("SITE_TITLE", "네이버 블로그 최신 글")
SITE_DESC = os.environ.get("SITE_DESC", "네이버 블로그 최신 글 모음 (자동 갱신)")
MAX_ITEMS = int(os.environ.get("MAX_ITEMS", "30"))

def render_html(entries):
    list_items = []
    for e in entries[:MAX_ITEMS]:
        title = escape(e.get("title", "제목 없음"))
        link = escape(e.get("link", "#"))
        published = e.get("published", "") or e.get("updated", "")
        li = f'<li><a href="{link}">{title}</a>' + (f' <span class="date">{escape(published)}</span>' if published else "") + "</li>"
        list_items.append(li)

    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return textwrap.dedent(f"""\
    <!doctype html>
    <html lang="ko">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>{escape(SITE_TITLE)}</title>
      <meta name="description" content="{escape(SITE_DESC)}">
      <style>
        body{{font-family:system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin:2rem; line-height:1.6}}
        h1{{margin-bottom:.25rem}}
        .sub{{color:#666; margin-bottom:1.5rem}}
        ul{{padding-left:1.2rem}}
        li{{margin:.4rem 0}}
        .date{{color:#888; font-size:.9em}}
        footer{{margin-top:2rem; color:#888; font-size:.9em}}
      </style>
    </head>
    <body>
      <h1>{escape(SITE_TITLE)}</h1>
      <div class="sub">{escape(SITE_DESC)}</div>
      <ul>
        {"".join(list_items) if list_items else "<li>피드 항목이 없습니다.</li>"}
      </ul>
      <footer>Last build: {now} · Source RSS: <a href="{escape(RSS_URL)}">{escape(RSS_URL)}</a></footer>
    </body>
    </html>
    """)

def main():
    feed = feedparser.parse(RSS_URL)
    out_dir = pathlib.Path("dist")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(render_html(feed.entries), encoding="utf-8")

if __name__ == "__main__":
    main()