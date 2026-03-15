from flask import Flask, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re

app = Flask(__name__)
CORS(app)  # Allow all origins so your dashboard can call this

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

VALID_REGIONS = {
    "worldwide": "worldwide",
    "united-states": "united-states",
    "united-kingdom": "united-kingdom",
    "nigeria": "nigeria",
    "canada": "canada",
    "australia": "australia",
    "south-africa": "south-africa",
    "ghana": "ghana",
}

@app.route("/")
def index():
    return jsonify({
        "status": "Salem Intel Backend is running",
        "endpoints": {
            "/trends/x?region=worldwide": "Live X trends from Trends24",
            "/trends/google?geo=US": "Live Google Trends RSS",
            "/health": "Health check"
        },
        "built_for": "Salem — @web3_Salem"
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})

@app.route("/trends/x")
def x_trends():
    from flask import request
    region = request.args.get("region", "worldwide")

    # Sanitize region
    region = VALID_REGIONS.get(region.lower(), "worldwide")

    url = f"https://trends24.in/{region}/"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        trends = []
        seen = set()

        # Trends24 stores trends in ol.trend-card elements
        trend_cards = soup.find_all("ol", class_="trend-card")

        for card in trend_cards[:3]:  # First 3 cards = most recent hours
            items = card.find_all("li")
            for item in items:
                link = item.find("a")
                if link:
                    topic = link.get_text(strip=True)
                    href = link.get("href", "")
                    tweet_count = ""

                    # Try to get tweet count
                    count_el = item.find(class_=re.compile(r"count|num|tweet", re.I))
                    if count_el:
                        tweet_count = count_el.get_text(strip=True)

                    if topic and topic not in seen and len(topic) > 1:
                        seen.add(topic)
                        trends.append({
                            "topic": topic,
                            "tweet_count": tweet_count,
                            "url": f"https://x.com/search?q={requests.utils.quote(topic)}&src=trend_click"
                        })

                if len(trends) >= 20:
                    break
            if len(trends) >= 20:
                break

        # Fallback: grab any trend links if cards not found
        if len(trends) < 5:
            all_links = soup.find_all("a", href=True)
            for link in all_links:
                href = link.get("href", "")
                topic = link.get_text(strip=True)
                if (topic.startswith("#") or len(topic) < 40) and topic not in seen and len(topic) > 2:
                    seen.add(topic)
                    trends.append({
                        "topic": topic,
                        "tweet_count": "",
                        "url": f"https://x.com/search?q={requests.utils.quote(topic)}"
                    })
                if len(trends) >= 20:
                    break

        if not trends:
            return jsonify({"error": "No trends found — Trends24 may have changed its HTML structure"}), 500

        return jsonify({
            "source": "trends24.in",
            "region": region,
            "fetched_at": datetime.utcnow().isoformat(),
            "count": len(trends),
            "trends": trends
        })

    except requests.exceptions.Timeout:
        return jsonify({"error": "Trends24 request timed out"}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Failed to fetch Trends24: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": f"Parsing error: {str(e)}"}), 500


@app.route("/trends/google")
def google_trends():
    from flask import request
    geo = request.args.get("geo", "US").upper()

    # Whitelist geos
    allowed_geos = ["US", "GB", "NG", "CA", "AU", "ZA", "GH", "GLOBAL"]
    if geo not in allowed_geos:
        geo = "US"

    rss_url = f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={geo}"

    try:
        resp = requests.get(rss_url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "xml")

        items = soup.find_all("item")
        trends = []

        for item in items[:15]:
            title_el = item.find("title")
            traffic_el = item.find("ht:approx_traffic")
            pub_el = item.find("pubDate")
            news_items = item.find_all("ht:news_item")

            news = []
            for n in news_items[:2]:
                n_title = n.find("ht:news_item_title")
                n_source = n.find("ht:news_item_source")
                n_url = n.find("ht:news_item_url")
                if n_title:
                    news.append({
                        "title": n_title.get_text(strip=True),
                        "source": n_source.get_text(strip=True) if n_source else "",
                        "url": n_url.get_text(strip=True) if n_url else ""
                    })

            if title_el:
                trends.append({
                    "topic": title_el.get_text(strip=True),
                    "traffic": traffic_el.get_text(strip=True) if traffic_el else "",
                    "pub_date": pub_el.get_text(strip=True) if pub_el else "",
                    "news": news
                })

        if not trends:
            return jsonify({"error": "No Google Trends found"}), 500

        return jsonify({
            "source": "Google Trends",
            "geo": geo,
            "fetched_at": datetime.utcnow().isoformat(),
            "count": len(trends),
            "trends": trends
        })

    except Exception as e:
        return jsonify({"error": f"Google Trends fetch failed: {str(e)}"}), 502


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
