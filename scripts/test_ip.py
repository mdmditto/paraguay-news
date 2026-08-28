import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin


BASE_URL = "https://www.ip.gov.py"
POLITICS_URL = f"{BASE_URL}/ip/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    )
}


def discover_articles():
    """
    Discover political articles from HOY.

    Returns:
        list[dict]
    """

    response = requests.get(
        POLITICS_URL,
        headers=HEADERS,
        timeout=20,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    articles = {}

    for link in soup.find_all(
        "a",
        href=True,
    ):

        href = link.get("href")

        if not href:
            continue

        full_url = urljoin(
            BASE_URL,
            href,
        )

        if "/politica/" not in full_url:
            continue

        # Ignore the section page itself
        if full_url.rstrip("/") == POLITICS_URL.rstrip("/"):
            continue

        title = link.get_text(
            " ",
            strip=True,
        )

        # Deduplicate by URL
        articles[full_url] = {
            "source": "HOY",
            "title": title or None,
            "url": full_url,
            "section": "politica",
        }

    return list(
        articles.values()
    )


if __name__ == "__main__":

    articles = discover_articles()

    print(
        f"Found {len(articles)} articles\n"
    )

    for article in articles:
        print(article["title"])
        print(article["url"])
        print()
