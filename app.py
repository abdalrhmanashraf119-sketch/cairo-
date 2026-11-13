from flask import Flask, jsonify, request
from flask_cors import CORS
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
import feedparser
import requests
import datetime
import re
from googlenewsdecoder import gnewsdecoder

app = Flask(__name__)
CORS(app)

def gnews(query):
    return "https://news.google.com/rss/search?q=" + quote(query + " when:1d") + "&hl=ar&gl=EG&ceid=EG:ar"

FEEDS = [
    {"url": gnews("كرة القدم"), "cat": "football"},
    {"url": gnews("الدوري المصري"), "cat": "football"},
    {"url": gnews("الأهلي الزمالك"), "cat": "football"},
    {"url": gnews("سياسة مصر"), "cat": "politics"},
    {"url": gnews("أخبار مصر عاجل"), "cat": "politics"},
    {"url": gnews("اقتصاد مصر"), "cat": "economy"},
    {"url": gnews("البورصة المصرية الدولار"), "cat": "economy"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "ar,en;q=0.8",
}

def parse_date(entry):
    if getattr(entry, "published_parsed", None):
        return datetime.datetime(*entry.published_parsed[:6]).isoformat()
    return datetime.datetime.utcnow().isoformat()

def fetch_feed(feed):
    try:
        r = requests.get(feed["url"], headers=HEADERS, timeout=7)
        parsed = feedparser.parse(r.content)
        items = []
        for e in parsed.entries[:15]:
            title = e.get("title", "")
            src = ""
            try:
                src = e.source.title
            except Exception:
                pass
            if src and title.endswith(" - " + src):
                title = title[: -len(" - " + src)]
            items.append({
                "title": title,
                "link": e.get("link", ""),
                "date": parse_date(e),
                "cat": feed["cat"],
                "source": src or "Google News",
            })
        return {"cat": feed["cat"], "status": r.status_code, "count": len(items), "items": items}
    except Exception as ex:
        return {"cat": feed["cat"], "status": "error: " + str(ex)[:80], "count": 0, "items": []}

def fetch_all():
    with ThreadPoolExecutor(max_workers=7) as pool:
        return list(pool.map(fetch_feed, FEEDS))

def resolve_url(url):
    """لينكات Google News بتحوّل لصفحة وسيطة، لازم نفك اللينك للمقال الأصلي الأول"""
    if "news.google.com" not in url:
        return url
    try:
        res = gnewsdecoder(url, timeout=8)
        if res.get("success") and res.get("decoded_url"):
            return res["decoded_url"]
    except Exception:
        pass
    return None

def get_og_image(url):
    """سحب og:image من صفحة المقال الأصلي"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=6, allow_redirects=True)
        html = r.text[:200000]
        for pat in (
            r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        ):
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                img = m.group(1).replace("&amp;", "&")
                if img.startswith("//"):
                    img = "https:" + img
                if img.startswith("http") and "googleusercontent.com" not in img:
                    return img
    except Exception:
        pass
    return None

@app.route("/")
def index():
    return "Cairo Buzz 24 API is running"

@app.route("/news")
@app.route("/api/news")
def news():
    seen, items = set(), []
    for res in fetch_all():
        for it in res["items"]:
            key = it["title"].strip()
            if key and key not in seen:
                seen.add(key)
                items.append(it)
    items.sort(key=lambda x: x["date"], reverse=True)
    return jsonify(items)

@app.route("/image")
def image():
    """بيرجّع صورة خبر واحد (بيتندهي لما تضغط استوديو بس)"""
    link = request.args.get("url", "")
    if not link.startswith("http"):
        return jsonify({"image": None, "error": "bad url"}), 400
    real = resolve_url(link)
    img = get_og_image(real) if real else None
    return jsonify({"image": img, "article": real})

@app.route("/image-test")
def image_test():
    """اختبار سريع: بياخد أول 4 أخبار ويجرب يجيب صورهم"""
    items = []
    for res in fetch_all():
        items.extend(res["items"])
    items = items[:4]
    out = []
    for it in items:
        real = resolve_url(it["link"])
        out.append({"title": it["title"], "article": real, "image": get_og_image(real) if real else None})
    return jsonify(out)

@app.route("/debug")
def debug():
    return jsonify([{k: v for k, v in r.items() if k != "items"} for r in fetch_all()])
