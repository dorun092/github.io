import os, html, textwrap, sys
import requests, feedparser
from urllib.parse import urlparse, urlunparse
from datetime import datetime, timezone
from dateutil import parser as dtparse
import argparse
import time

# 사용법
#
# # 1) 가장 오래된 글부터 5개 백필
# python backfill_blogger.py --max 5 --oldest-first
#
# # 2) 최신글 10개는 건너뛰고 그 다음 20개 백필
# python backfill_blogger.py --skip 10 --max 20 --oldest-first
#
# # 3) 날짜 범위로 백필 (예: 2024-01-01 ~ 2024-12-31)
# python backfill_blogger.py --since 2024-01-01 --until 2024-12-31 --oldest-first
#
# # 4) 이미 올린 글이라도 강제로 다시 올리기
# python backfill_blogger.py --max 3 --force
#
# # 5) 리허설(실제 업로드 X)
# python backfill_blogger.py --max 10 --dry-run


# ===== 필수 환경변수 =====
CLIENT_ID      = os.environ["GCP_CLIENT_ID"]
CLIENT_SECRET  = os.environ["GCP_CLIENT_SECRET"]
REFRESH_TOKEN  = os.environ["GCP_REFRESH_TOKEN"]
BLOG_ID        = os.environ["BLOG_ID"]

# ===== 설정 =====
RSS_URL        = os.environ.get("RSS_URL", "https://rss.blog.naver.com/do_run_.xml")

TOKEN_URL   = "https://oauth2.googleapis.com/token"
BLOGGER_API = "https://www.googleapis.com/blogger/v3"

def log(*a): print(*a, flush=True)

def get_access_token():
    r = requests.post(TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]

def auth_headers(at):
    return {"Authorization": f"Bearer {at}", "Content-Type":"application/json; charset=utf-8"}

def blogger_get(url, at, params=None):
    r = requests.get(url, headers=auth_headers(at), params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def blogger_post(url, at, json):
    r = requests.post(url, headers=auth_headers(at), json=json, timeout=30)
    r.raise_for_status()
    return r.json()

def normalize_link(u: str) -> str:
    if not u: return u
    p = urlparse(u)
    p = p._replace(query="", fragment="")
    return urlunparse(p)

def entry_dt(e) -> datetime:
    # feedparser의 published_parsed/updated_parsed → datetime(UTC)
    for k in ("published_parsed","updated_parsed"):
        t = e.get(k)
        if t: return datetime(*t[:6], tzinfo=timezone.utc)
    # 폴백: 문자열 파싱
    for k in ("published","updated"):
        s = e.get(k)
        if s:
            try: return dtparse.parse(s).astimezone(timezone.utc)
            except: pass
    return None

def fetch_entries(rss_url):
    feed = feedparser.parse(rss_url)
    if feed.bozo:
        log("[warn] RSS parse error:", feed.bozo_exception)
    return feed.entries or []

def summarize(text, limit=400):
    if not text: return ""
    t = html.unescape(text).strip()
    return (t[:limit].rstrip() + "…") if len(t) > limit else t

def source_marker(link: str) -> str:
    # 네이버 글ID를 추출해 숨김 마커 생성
    base = normalize_link(link)
    post_id = base.split("/")[-1] if "/" in base else base
    return f"source:nblog:{post_id}"

def already_posted(at, blog_id, link):
    # 1차: 마커 검색
    marker = source_marker(link)
    url = f"{BLOGGER_API}/blogs/{blog_id}/posts/search"
    js = blogger_get(url, at, params={"q": f'"{marker}"'})
    if js.get("items"): return True
    # 2차: 링크 문자열 검색
    js = blogger_get(url, at, params={"q": f'"{normalize_link(link)}"'})
    return bool(js.get("items"))

def render_content(title, link, summary):
    marker = source_marker(link)
    link_n = normalize_link(link)
    return textwrap.dedent(f"""
        <!-- {marker} -->
        <p><strong>{html.escape(title)}</strong></p>
        <p>{html.escape(summary)}</p>
        <p>👉 <a href="{html.escape(link_n)}" rel="nofollow noopener" target="_blank">원문 보기(네이버 블로그)</a></p>
        <hr/>
        <p style="color:#888;font-size:0.9em">본 포스트는 RSS 자동화로 발행되었습니다.</p>
    """).strip()

def backfill(args):
    at = get_access_token()
    log("[ok] access_token issued")

    entries = fetch_entries(RSS_URL)
    if not entries:
        log("[info] no entries")
        return

    # 기본: RSS는 보통 최신순. 오래된 것부터 올리려면 뒤집기
    if args.oldest_first:
        entries = list(reversed(entries))

    # 날짜 필터
    def in_window(e):
        d = entry_dt(e)
        if not d: return True
        ok = True
        if args.since:
            ok = ok and (d >= args.since.replace(tzinfo=timezone.utc))
        if args.until:
            ok = ok and (d <= args.until.replace(tzinfo=timezone.utc))
        return ok

    entries = [e for e in entries if in_window(e)]

    # 앞쪽 skip
    if args.skip > 0:
        entries = entries[args.skip:]

    # 개수 제한
    if args.max:
        entries = entries[:args.max]

    log(f"[plan] candidates={len(entries)}")

    posted = 0
    for e in entries:
        title = e.get("title") or "(제목 없음)"
        link  = e.get("link")  or ""
        if not link:
            log(f"[skip] no link: {title}")
            continue

        if not args.force and already_posted(at, BLOG_ID, link):
            log(f"[skip] exists: {normalize_link(link)}")
            continue

        content = render_content(title, link, summarize(e.get("summary") or e.get("description") or ""))

        body = {"kind":"blogger#post", "title": title, "content": content, "labels": ["from-naver"]}
        if args.dry_run:
            log(f"[dry-run] would post: {title}")
        else:
            res = blogger_post(f"{BLOGGER_API}/blogs/{BLOG_ID}/posts/", at, body)
            log(f"[created] {res.get('url')}")
            posted += 1
            time.sleep(2.0)

    log(f"[done] posted={posted}")

def parse_args():
    p = argparse.ArgumentParser(description="Backfill old posts from Naver RSS to Blogger")
    p.add_argument("--max", type=int, default=None, help="올릴 최대 개수")
    p.add_argument("--skip", type=int, default=0, help="앞에서 N개 건너뛰기")
    p.add_argument("--since", type=lambda s: dtparse.parse(s), help="이 날짜(포함) 이후 (YYYY-MM-DD)")
    p.add_argument("--until", type=lambda s: dtparse.parse(s), help="이 날짜(포함) 이전 (YYYY-MM-DD)")
    p.add_argument("--oldest-first", action="store_true", help="오래된 것부터 업로드")
    p.add_argument("--force", action="store_true", help="이미 올린 글이라도 다시 업로드")
    p.add_argument("--dry-run", action="store_true", help="실제 업로드 없이 계획만")
    return p.parse_args()

if __name__ == "__main__":
    missing = [k for k in ["GCP_CLIENT_ID","GCP_CLIENT_SECRET","GCP_REFRESH_TOKEN","BLOG_ID"] if not os.environ.get(k)]
    if missing:
        raise SystemExit("Missing env: " + ", ".join(missing))
    args = parse_args()
    backfill(args)