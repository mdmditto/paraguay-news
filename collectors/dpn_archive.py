
import json
import time
import requests

from bs4 import BeautifulSoup
from collections import Counter
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

BASE_URL = "https://diarioparaguayo.com"

CATEGORIES = [
    "politica",
    "economia",
    "deportes",
    "tecnologia",
    "nacionales",
    "internacionales",
    "sociedad",
    "entretenimiento",
    "salud",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
})


def parse_date(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        ).date()
    except ValueError:
        return None


def get_article_metadata(url):
    response = session.get(url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):
        try:
            data = json.loads(
                script.string or script.get_text()
            )
        except (ValueError, TypeError):
            continue

        objects = data if isinstance(data, list) else [data]

        for obj in objects:
            if not isinstance(obj, dict):
                continue

            if obj.get("@type") != "NewsArticle":
                continue

            return {
                "url": url,
                "title": obj.get("headline"),
                "published": parse_date(
                    obj.get("datePublished")
                ),
            }

    return {
        "url": url,
        "title": None,
        "published": None,
    }


def get_category_urls(category, page):
    url = (
        f"{BASE_URL}/categoria/{category}"
        f"?page={page}"
    )

    response = session.get(url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    urls = []

    for a in soup.find_all("a", href=True):
        href = urljoin(response.url, a["href"])

        parsed = urlparse(href)

        if parsed.netloc not in (
            "diarioparaguayo.com",
            "www.diarioparaguayo.com",
        ):
            continue

        if not parsed.path.startswith("/noticia/"):
            continue

        clean_url = (
            f"{parsed.scheme}://{parsed.netloc}"
            f"{parsed.path}"
        )

        urls.append(clean_url)

    return list(dict.fromkeys(urls))


def discover_dpn_historical(
    start_date,
    end_date,
    max_pages_per_category=50,
):
    discovered = {}
    metadata_cache = {}

    for category in CATEGORIES:
        print(f"\nCATEGORY: {category}")

        category_matches = 0
        previous_urls = None

        for page in range(
            1,
            max_pages_per_category + 1
        ):
            try:
                urls = get_category_urls(
                    category,
                    page
                )
            except Exception as exc:
                print("Category error:", exc)
                break

            if not urls:
                print("No articles. Stopping.")
                break

            if urls == previous_urls:
                print("Repeated page. Stopping.")
                break

            previous_urls = urls

            page_dates = []
            new_matches = 0

            for url in urls:
                if url not in metadata_cache:
                    try:
                        metadata_cache[url] = (
                            get_article_metadata(url)
                        )
                        time.sleep(0.1)
                    except Exception as exc:
                        print("Article error:", url, exc)
                        continue

                article = metadata_cache.get(url)

                if not article:
                    continue

                published = article["published"]

                if published is None:
                    continue

                page_dates.append(published)

                if not (
                    start_date <= published <= end_date
                ):
                    continue

                if url in discovered:
                    continue

                discovered[url] = {
                    "source": "Diario Paraguayo",
                    "title": article["title"],
                    "url": url,
                }

                new_matches += 1
                category_matches += 1

            print(
                f"  Page {page}: "
                f"{len(urls)} URLs, "
                f"{new_matches} new matches"
            )

            # Category pages appear to be sorted
            # from newest to oldest.
            if page_dates and max(page_dates) < start_date:
                print(
                    "All dated articles on this page "
                    "are older than requested range."
                )
                break

            time.sleep(0.2)

        print(
            f"Found {category_matches} unique "
            f"matching articles for {category}"
        )

    print("\n" + "=" * 60)
    print("DPN HISTORICAL DISCOVERY SUMMARY")
    print("=" * 60)

    print("TOTAL UNIQUE ARTICLES:", len(discovered))

    counts = Counter(
        metadata_cache[url]["published"]
        for url in discovered
    )

    print("\nARTICLES PER DATE")

    for day, count in sorted(counts.items()):
        print(day, count)

    return list(discovered.values())


if __name__ == "__main__":
    articles = discover_dpn_historical(
        start_date=date(2026, 11, 4),
        end_date=date(2026, 11, 6),
        max_pages_per_category=50,
    )

    print("\nSAMPLE ARTICLES")

    for article in articles[:15]:
        print(article["url"])
