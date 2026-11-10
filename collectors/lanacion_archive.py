
import time
import requests

from collections import Counter
from datetime import date
from urllib.parse import urljoin, urlparse

BASE_URL = "https://www.lanacion.com.py"

API_URL = (
    BASE_URL
    + "/pf/api/v3/content/fetch/content-search-feed-sp"
)

SEARCH_TERMS = [
    "Paraguay",
    "política",
    "economía",
    "nacionales",
    "salud",
    "educación",
    "seguridad",
    "deportes",
    "Asunción",
]

session = requests.Session()

session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Referer": BASE_URL + "/buscar/",
})


def article_date_from_url(url):
    parts = urlparse(url).path.strip("/").split("/")

    if len(parts) < 5:
        return None

    try:
        return date(
            int(parts[1]),
            int(parts[2]),
            int(parts[3]),
        )
    except (ValueError, IndexError):
        return None


def search_lanacion(query, offset=0, batchsize=50):
    import json

    params = {
        "query": json.dumps({
            "feedFrom": offset,
            "feedQuery": query,
            "feedSize": batchsize,
            "website": "lanacionpy",
        }),
        "d": "763",
        "mxId": "00000000",
        "_website": "lanacionpy",
    }

    response = session.get(
        API_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def discover_lanacion_historical(
    start_date,
    end_date,
    search_terms=None,
    max_pages_per_query=30,
    batchsize=50,
):
    terms = search_terms or SEARCH_TERMS

    discovered = {}

    for term in terms:
        print(f"\nSEARCH: {term}")

        offset = 0
        term_matches = 0

        for page_number in range(max_pages_per_query):
            try:
                data = search_lanacion(
                    query=term,
                    offset=offset,
                    batchsize=batchsize,
                )

            except Exception as exc:
                print("API error:", exc)
                break

            items = data.get("content_elements", [])

            if not items:
                break

            new_matches = 0

            for item in items:
                path = item.get("canonical_url")

                if not path:
                    continue

                url = urljoin(BASE_URL, path)

                published = article_date_from_url(url)

                if published is None:
                    continue

                if not start_date <= published <= end_date:
                    continue

                if url in discovered:
                    continue

                title = item.get("headlines", {}).get(
                    "basic"
                )

                discovered[url] = {
                    "source": "La Nación",
                    "title": title,
                    "url": url,
                }

                new_matches += 1
                term_matches += 1

            print(
                f"  Page {page_number + 1}: "
                f"{len(items)} results, "
                f"{new_matches} new matches"
            )

            if len(items) < batchsize:
                break

            offset += len(items)

            time.sleep(0.3)

        print(
            f"Found {term_matches} unique matching "
            f"articles for '{term}'"
        )

    print(
        f"\nTOTAL UNIQUE ARTICLES: {len(discovered)}"
    )

    counts = Counter(
        article_date_from_url(url)
        for url in discovered
    )

    print("\nARTICLES PER DATE")

    for day, count in sorted(counts.items()):
        print(day, count)

    return list(discovered.values())


if __name__ == "__main__":
    articles = discover_lanacion_historical(
        start_date=date(2026, 11, 4),
        end_date=date(2026, 11, 6),
    )

    print("\nSAMPLE ARTICLES")

    for article in articles[:10]:
        print(article["url"])
