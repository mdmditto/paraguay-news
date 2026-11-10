
import time
import requests
import xml.etree.ElementTree as ET

from collections import Counter
from datetime import date
from urllib.parse import urlparse

BASE_URL = "https://www.rdn.com.py"
SITEMAP_URL = BASE_URL + "/sitemap.xml"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0"
})


def extract_date(url):
    """
    RDN article URL format:
    /2026/11/04/article-slug/
    """
    parts = urlparse(url).path.strip("/").split("/")

    if len(parts) < 4:
        return None

    try:
        return date(
            int(parts[0]),
            int(parts[1]),
            int(parts[2]),
        )
    except (ValueError, IndexError):
        return None


def fetch_sitemap(url):
    response = session.get(url, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.content)

    entries = []

    for element in root:
        loc = element.find("{*}loc")

        if loc is not None and loc.text:
            entries.append(loc.text.strip())

    return root.tag, entries


def discover_rdn_historical(
    start_date,
    end_date,
    max_sitemaps=100,
):
    discovered = {}

    print("Fetching RDN sitemap index...")

    root_tag, sitemap_urls = fetch_sitemap(
        SITEMAP_URL
    )

    print("Sitemap root:", root_tag)
    print("Sitemaps found:", len(sitemap_urls))

    if not root_tag.endswith("sitemapindex"):
        raise ValueError(
            "Expected sitemap index, got " + root_tag
        )

    for index, sitemap_url in enumerate(
        sitemap_urls[:max_sitemaps],
        start=1,
    ):
        print(
            f"\nSITEMAP {index}/{min(len(sitemap_urls), max_sitemaps)}"
        )
        print(sitemap_url)

        try:
            child_tag, urls = fetch_sitemap(
                sitemap_url
            )
        except Exception as exc:
            print("ERROR:", exc)
            continue

        if not child_tag.endswith("urlset"):
            print("Unexpected sitemap type:", child_tag)
            continue

        matches = 0

        for url in urls:
            published = extract_date(url)

            if published is None:
                continue

            if not start_date <= published <= end_date:
                continue

            if url in discovered:
                continue

            discovered[url] = {
                "source": "Resumen de Noticias",
                "title": None,
                "url": url,
            }

            matches += 1

        print("URLs in sitemap:", len(urls))
        print("New matching articles:", matches)

        time.sleep(0.2)

    print("\n" + "=" * 60)
    print("RDN HISTORICAL DISCOVERY SUMMARY")
    print("=" * 60)

    print("TOTAL UNIQUE ARTICLES:", len(discovered))

    counts = Counter(
        extract_date(url)
        for url in discovered
    )

    print("\nARTICLES PER DATE")

    for day, count in sorted(counts.items()):
        print(day, count)

    return list(discovered.values())


if __name__ == "__main__":
    articles = discover_rdn_historical(
        start_date=date(2026, 11, 4),
        end_date=date(2026, 11, 6),
    )

    print("\nSAMPLE ARTICLES")

    for article in articles[:15]:
        print(article["url"])
