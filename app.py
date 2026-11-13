from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
import feedparser
import requests
import datetime
import re
import socket
import ipaddress
from urllib.parse import urlparse, urljoin
from html import unescape as html_unescape
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

def _attrs(tag):
    out = {}
    for k, v1, v2 in re.findall(r"([a-zA-Z][\w:-]*)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", tag):
        out[k.lower()] = v1 or v2
    return out

def get_og_image(url):
    """سحب صورة المقال: og:image ثم twitter:image ثم image_src ثم JSON-LD"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=7, allow_redirects=True)
        if r.status_code >= 400:
            return None
        html = r.text[:300000]
        base = r.url
        metas = {}
        for tag in re.findall(r"<meta\b[^>]*>", html, re.I):
            a = _attrs(tag)
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content"):
                metas.setdefault(key, a["content"])
        cands = []
        for k in ("og:image", "og:image:secure_url", "og:image:url", "twitter:image", "twitter:image:src"):
            if metas.get(k):
                cands.append(metas[k])
        m = re.search(r"<link\b[^>]*rel=[\"']image_src[\"'][^>]*>", html, re.I)
        if m and _attrs(m.group(0)).get("href"):
            cands.append(_attrs(m.group(0))["href"])
        m = re.search(r'"image"\s*:\s*(?:\[\s*)?(?:\{[^}]*?"url"\s*:\s*)?"([^"]+)"', html)
        if m:
            cands.append(m.group(1).replace("\\/", "/"))
        for c in cands:
            img = urljoin(base, html_unescape(c.strip()))
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

def is_public_host(url):
    """حماية: منسمحش بالوصول لعناوين داخلية"""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return False
        for info in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        return True
    except Exception:
        return False

@app.route("/img-proxy")
def img_proxy():
    """بيمرّر الصورة من عندنا عشان الكانفس يقدر يصدّر PNG/فيديو بدون CORS"""
    url = request.args.get("url", "")
    ref = request.args.get("ref", "")
    if not is_public_host(url):
        return jsonify({"error": "bad url"}), 400
    pu = urlparse(url)
    refs = []
    if ref.startswith("http"):
        refs.append(ref)
    refs.append(pu.scheme + "://" + pu.netloc + "/")
    refs.append(None)
    for rf in refs:
        try:
            h = dict(HEADERS)
            h["Accept"] = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
            if rf:
                h["Referer"] = rf
            r = requests.get(url, headers=h, timeout=8, stream=True)
            if r.status_code >= 400:
                continue
            ctype = r.headers.get("Content-Type", "")
            if not (ctype.startswith("image/") or ctype.startswith("application/octet-stream")):
                continue
            data = r.raw.read(8 * 1024 * 1024 + 1, decode_content=True)
            if len(data) > 8 * 1024 * 1024:
                return jsonify({"error": "too large"}), 413
            return Response(data, content_type=ctype, headers={"Cache-Control": "public, max-age=3600"})
        except Exception:
            continue
    return jsonify({"error": "fetch failed"}), 502

@app.route("/debug")
def debug():
    return jsonify([{k: v for k, v in r.items() if k != "items"} for r in fetch_all()])
