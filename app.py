from flask import Flask, jsonify
from flask_cors import CORS
from concurrent.futures import ThreadPoolExecutor
import feedparser
import requests
import datetime

app = Flask(__name__)
CORS(app)

FEEDS = [
    {"url": "https://www.filgoal.com/rss/", "cat": "football", "source": "FilGoal"},
    {"url": "https://www.yallakora.com/rss/", "cat": "football", "source": "Yalla Kora"},
    {"url": "https://arabic.goal.com/ar/rss/news/", "cat": "football", "source": "Goal عربي"},
    {"url": "https://www.masrawy.com/rss/news", "cat": "politics", "source": "مصراوي"},
    {"url": "https://www.youm7.com/rss/Section/1/0", "cat": "politics", "source": "اليوم السابع"},
    {"url": "https://gate.ahram.org.eg/rss/RssFeeds.aspx?feedName=1", "cat": "politics", "source": "الأهرام"},
    {"url": "https://www.amwalalghad.com/feed/", "cat": "economy", "source": "أموال الغد"},
    {"url": "https://www.youm7.com/rss/Section/97/0", "cat": "economy", "source": "اليوم السابع اقتصاد"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "ar,en;q=0.8",
}

def parse_date(entry):
    if getattr(entry, "published_parsed", None):
        return datetime.datetime(*entry.published_parsed[:6]).isoformat()
    return datetime.datetime.utcnow().isoformat()

def fetch_feed(feed):
    try:
        r = requests.get(feed["url"], headers=HEADERS, timeout=6)
        parsed = feedparser.parse(r.content)
        items = [{
            "title": e.get("title", ""),
            "link": e.get("link", ""),
            "date": parse_date(e),
            "cat": feed["cat"],
            "source": feed["source"],
        } for e in parsed.entries[:10]]
        return {"source": feed["source"], "status": r.status_code, "count": len(items), "items": items}
    except Exception as ex:
        return {"source": feed["source"], "status": "error: " + str(ex)[:80], "count": 0, "items": []}

def fetch_all():
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(fetch_feed, FEEDS))

@app.route("/")
def index():
    return "Cairo Buzz 24 API is running"

@app.route("/news")
@app.route("/api/news")
def news():
    items = []
    for res in fetch_all():
        items.extend(res["items"])
    items.sort(key=lambda x: x["date"], reverse=True)
    return jsonify(items)

@app.route("/debug")
def debug():
    return jsonify([{k: v for k, v in r.items() if k != "items"} for r in fetch_all()])
