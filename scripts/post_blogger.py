import os, sys, time, html, textwrap, urllib.parse
import requests
import feedparser

# 환경변수
CLIENT_ID      = os.environ["GCP_CLIENT_ID"]
CLIENT_SECRET  = os.environ["GCP_CLIENT_SECRET"]
REFRESH_TOKEN  = os.environ["GCP_REFRESH_TOKEN"]
BLOG_ID        = os.environ["BLOG_ID"] # (blogger) blog id

# 콘텐츠 소스
RSS_URL        = os.environ.get("RSS_URL", "https://rss.blog.naver.com/do_run_.xml")
MAX_POSTS      = int(os.environ.get("MAX_POSTS", "1"))  # 한번에 올릴 개수(기본 1개)
DRY_RUN        = os.environ.get("DRY_RUN", "false").lower() == "true"  # true면 실제 업로드 X

# google gcp 관련
TOKEN_URL = "https://oauth2.googleapis.com/token"
BLOGGER_API = "https://www.googleapis.com/blogger/v3"

def log(*args):
    print(*args, flush=True)

def get_access_token():
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }
    r = requests.post(TOKEN_URL, data=data, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"[token] fail {r.status_code} {r.text}")
    return r.json()["access_token"]

def auth_headers(access_token):
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=utf-8"}

def blogger_get(url, access_token, params=None):
    r = requests.get(url, headers=auth_headers(access_token), params=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"[GET] {url} -> {r.status_code} {r.text}")
    return r.json()

def blogger_post(url, access_token, json):
    r = requests.post(url, headers=auth_headers(access_token), json=json, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"[POST] {url} -> {r.status_code} {r.text}")
    return r.json()

def already_posted(access_token, blog_id, source_link):
    """
    중복 방지: 원문 링크가 이미 올라간 적 있는지 검색 API로 확인
    참고: posts/search는 모든 필드를 완벽히 검색하진 않지만, 링크 텍스트가 본문에 포함되면 잘 잡힘
    """
    q = f'"{source_link}"'  # 정확도 높이기 위해 따옴표 검색
    url = f"{BLOGGER_API}/blogs/{blog_id}/posts/search"
    js = blogger_get(url, access_token, params={"q": q})
    items = js.get("items", []) or []
    return len(items) > 0

def summarize(text, limit=300):
    t = (text or "").strip()
    t = html.unescape(t)
    # 너무 길면 잘라서 ...
    if len(t) > limit:
        t = t[:limit].rstrip() + "…"
    return t

def render_content(title, link, summary):
    # Blogger 본문용 간단 템플릿 (요약 + 원문 링크)
    return textwrap.dedent(f"""
        <p><strong>{html.escape(title)}</strong></p>
        <p>{html.escape(summary)}</p>
        <p>👉 <a href="{html.escape(link)}" rel="nofollow noopener" target="_blank">원문 보기(네이버 블로그)</a></p>
        <hr/>
        <p style="color:#888;font-size:0.9em">
          본 포스트는 RSS 자동화로 발행되었습니다.
        </p>
    """).strip()

def fetch_feed(rss_url):
    feed = feedparser.parse(rss_url)
    if feed.bozo:
        log("[warn] RSS parse error:", feed.bozo_exception)
    return feed.entries

def main():
    access_token = get_access_token()
    log("[ok] access_token issued")

    entries = fetch_feed(RSS_URL)
    if not entries:
        log("[info] no entries in RSS")
        return

    # 최신순으로 상위 N개만
    to_publish = entries[:MAX_POSTS]
    posted = 0

    for e in to_publish:
        title = e.get("title") or "(제목 없음)"
        link  = e.get("link")  or ""
        summary_raw = e.get("summary") or e.get("description") or ""
        summary = summarize(summary_raw, 400)

        if not link:
            log(f"[skip] no link for '{title}'")
            continue

        # 중복 체크
        if already_posted(access_token, BLOG_ID, link):
            log(f"[skip] already posted: {link}")
            continue

        body = {
            "kind": "blogger#post",
            "title": title,
            "content": render_content(title, link, summary),
            # 라벨(카테고리) 사용하고 싶으면 여기 추가
            # "labels": ["네이버요약", "자동포스팅"]
        }

        if DRY_RUN:
            log("[dry-run] would create post:", title)
            posted += 1
        else:
            url = f"{BLOGGER_API}/blogs/{BLOG_ID}/posts/"
            res = blogger_post(url, access_token, body)
            log(f"[created] {res.get('url')}")
            posted += 1

    log(f"[done] posted={posted}, checked={len(to_publish)}")

if __name__ == "__main__":
    # 필수 env 체크
    missing = [k for k in ["GCP_CLIENT_ID","GCP_CLIENT_SECRET","GCP_REFRESH_TOKEN","BLOG_ID"] if not os.environ.get(k)]
    if missing:
        raise SystemExit("Missing env: " + ", ".join(missing))
    main()