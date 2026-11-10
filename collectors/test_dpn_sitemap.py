
import requests
import xml.etree.ElementTree as ET

from collections import Counter
from datetime import datetime, date
from urllib.parse import urlparse

SITEMAP_URL = "https://diarioparaguayo.com/sitemap.xml"

START_DATE = date(2026, 11, 4)
END_DATE = date(2026, 11, 6)


def parse_date(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        ).date()
    except ValueError:
        return None


def main():
    response = requests.get(
        SITEMAP_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )

    response.raise_for_status()

    root = ET.fromstring(response.content)

    articles = []
    counts = Counter()

    missing_dates = 0

    for entry in root:
        loc = entry.find("{*}loc")
        lastmod = entry.find("{*}lastmod")

        if loc is None or not loc.text:
            continue

        url = loc.text.strip()
        path = urlparse(url).path

        if not path.startswith("/noticia/"):
            continue

        modified = parse_date(
            lastmod.text if lastmod is not None else None
        )

        if modified is None:
            missing_dates += 1
            continue

        counts[modified] += 1

        if START_DATE <= modified <= END_DATE:
            articles.append({
                "url": url,
                "lastmod": modified,
            })

    print("\nTOTAL ARTICLE ENTRIES:", sum(counts.values()) + missing_dates)
    print("ARTICLES WITHOUT LASTMOD:", missing_dates)

    print("\nSITEMAP ENTRIES BY LASTMOD DATE")

    for day, count in sorted(counts.items()):
        if date(2026, 11, 1) <= day <= date(2026, 11, 9):
            print(day, count)

    print("\nCANDIDATES NOV 4-6:", len(articles))

    print("\nSAMPLE ARTICLES")

    for article in articles[:15]:
        print(article["lastmod"], article["url"])


if __name__ == "__main__":
    main()
