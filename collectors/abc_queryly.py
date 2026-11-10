import json
import time
import requests

from datetime import date
from urllib.parse import urljoin, urlparse

from collectors.abc import is_article_url


API_URL = "https://api.queryly.com/json.aspx"
BASE_URL = "https://www.abc.com.py"

QUERYLY_KEY = "33530b56c6aa4c20"
CALLBACK = "searchPage.resultcallback("

SEARCH_TERMS = [
    "Paraguay",
    "Santiago Peña",
    "política",
    "economía",
    "nacionales",
    "policía",
    "salud",
    "educación",
    "deportes",
    "fútbol",
    "internacional",
    "Asunción",
]

session = requests.Session()

session.headers.update({
    "User-Agent": "Mozilla/5.0",
})


def queryly_search(query, offset=0, batchsize=100):

    params = {
        "queryly_key": QUERYLY_KEY,
        "query": query,
        "endindex": offset,
        "batchsize": batchsize,
        "callback": "searchPage.resultcallback",
        "showfaceted": "false",
        "timezoneoffset": 240,
    }

    response = session.get(
        API_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    body = response.text

    pos = body.find(CALLBACK)

    if pos == -1:
        raise ValueError(
            f"Unexpected Queryly response: {body[:300]}"
        )

    decoder = json.JSONDecoder()

    data, _ = decoder.raw_decode(
        body[pos + len(CALLBACK):].lstrip()
    )

    return data


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


def discover_abc_historical(
    start_date,
    end_date,
    search_terms=None,
    max_pages_per_query=15,
    batchsize=100,
):

    terms = search_terms or SEARCH_TERMS

    discovered = {}

    for term in terms:

        print(f"\nSEARCH: {term}")

        offset = 0
        term_matches = 0

        for page_number in range(max_pages_per_query):

            try:
                data = queryly_search(
                    term,
                    offset=offset,
                    batchsize=batchsize,
                )

            except Exception as exc:
                print(f"Queryly error: {exc}")
                break

            items = data.get("items", [])

            if not items:
                break

            for item in items:

                link = item.get("link")

                if not link:
                    continue

                url = urljoin(BASE_URL, link)

                if not is_article_url(url):
                    continue

                published = article_date_from_url(url)

                if published is None:
                    continue

                if not start_date <= published <= end_date:
                    continue

                if url in discovered:
                    continue

                discovered[url] = {
                    "source": "ABC Color",
                    "title": item.get("title"),
                    "url": url,
                }

                term_matches += 1

            next_offset = data.get(
                "metadata", {}
            ).get("endindex")

            print(
                f"  Page {page_number + 1}: "
                f"{len(items)} results, "
                f"{term_matches} matching articles"
            )

            if (
                next_offset is None
                or next_offset <= offset
            ):
                break

            offset = next_offset

            time.sleep(0.5)

        print(
            f"Found {term_matches} new matching "
            f"articles for '{term}'"
        )

    print(
        f"\nTOTAL UNIQUE ARTICLES: {len(discovered)}"
    )

    return list(discovered.values())
