from flask import Flask, jsonify
from flask_cors import CORS
import feedparser
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

def parse_date(entry):
    if getattr(entry, "published_parsed", None):
        return datetime.datetime(*entry.published_parsed[:6]).isoformat()
    return datetime.datetime.utcnow().isoformat()

@app.route("/")
def index():
    return "Cairo Buzz 24 API is running"

@app.route("/news")
@app.route("/api/news")
def news():
    items = []
    for feed in FEEDS:
        try:
            parsed = feedparser.parse(feed["url"])
            for e in parsed.entries[:10]:
                items.append({
                    "title": e.get("title", ""),
                    "link": e.get("link", ""),
                    "date": parse_date(e),
                    "cat": feed["cat"],
                    "source": feed["source"],
                })
        except Exception as ex:
            print("feed error", feed["source"], ex)
    items.sort(key=lambda x: x["date"], reverse=True)
    return jsonify(items)
