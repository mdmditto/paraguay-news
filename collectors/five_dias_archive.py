
import json
import re
import time
from datetime import date, datetime
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://5dias.com.py"

SECTIONS = [
    "/",
    "/noticiasdeldia",
    "/especiales",
    "/5dteconecta",
    "/banca-y-finanzas",
    "/category/Negocios",
    "/category/Economía y Finanzas",
    "/subcategory/Internacional",
    "/5data",
    "/qeq",
    "/ueno",
]


def extract_articles(html):
    soup = BeautifulSoup(html, "html.parser")
    articles = {}

    for script in soup.find_all("script"):
        content = script.get_text()

        if "self.__next_f.push" not in content:
            continue

        matches = re.finditer(
            r'self\.__next_f\.push\(\[1,("(?:\\.|[^"\\])*")\]\)',
            content,
            re.DOTALL,
        )

        for match in matches:
            try:
                payload = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

            decoder = json.JSONDecoder()

            for obj_match in re.finditer(r'\{"_id":', payload):
                try:
                    obj, _ = decoder.raw_decode(
                        payload[obj_match.start():]
                    )
                except json.JSONDecodeError:
                    continue

                if not isinstance(obj, dict):
                    continue

                slug = obj.get("notice_url")
                published = obj.get("publish_date")

                if not slug or not published:
                    continue

                url = urljoin(BASE, "/article/" + slug)

                articles[url] = {
                    "url": url,
                    "title": obj.get("title"),
                    "publish_date": published,
                }

    return list(articles.values())


def discover_5dias_historical(
    start_date,
    end_date,
    delay=1.0,
):
    start = date.fromisoformat(str(start_date)[:10])
    end = date.fromisoformat(str(end_date)[:10])

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
    })

    discovered = {}

    for section in SECTIONS:
        url = BASE + quote(section, safe="/")

        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()

            articles = extract_articles(response.text)

            added = 0

            for article in articles:
                published = date.fromisoformat(
                    article["publish_date"][:10]
                )

                if start <= published <= end:
                    if article["url"] not in discovered:
                        discovered[article["url"]] = article
                        added += 1

            print(
                f"[5dias] {section}: "
                f"{len(articles)} found, "
                f"{added} new target articles"
            )

        except (requests.RequestException, ValueError) as exc:
            print(f"[5dias] ERROR {section}: {exc}")

        time.sleep(delay)

    print(
        f"[5dias] TOTAL: "
        f"{len(discovered)} target articles"
    )

    return list(discovered.values())
