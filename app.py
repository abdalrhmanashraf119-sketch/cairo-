from flask import Flask, jsonify
from flask_cors import CORS
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
import feedparser
import requests
import datetime
import re

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

def get_og_image(url):
    """سحب og:image من صفحة الخبر"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=5, allow_redirects=True)
        # ابحث عن og:image في الـ HTML
        match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']', r.text, re.IGNORECASE)
        if not match:
            # جرب الترتيب العكسي (content قبل property)
            match = re.search(r'<meta[^>]+content=["\'](https?://[^"\']+)["\'][^>]+property=["\']og:image["\']', r.text, re.IGNORECASE)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None

def fetch_image_for_item(item):
    """إضافة الصورة لخبر واحد"""
    item["image"] = get_og_image(item["link"])
    return item

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

@app.route("/news-with-images")
@app.route("/api/news-with-images")
def news_with_images():
    """نفس /news بس بيضيف og:image لكل خبر"""
    seen, items = set(), []
    for res in fetch_all():
        for it in res["items"]:
            key = it["title"].strip()
            if key and key not in seen:
                seen.add(key)
                items.append(it)
    items.sort(key=lambda x: x["date"], reverse=True)

    # سحب الصور بالتوازي (max 10 workers عشان متضغطش على الـ servers)
    with ThreadPoolExecutor(max_workers=10) as pool:
        items = list(pool.map(fetch_image_for_item, items))

    return jsonify(items)

@app.route("/debug")
def debug():
    return jsonify([{k: v for k, v in r.items() if k != "items"} for r in fetch_all()])
