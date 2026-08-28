import re
import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


BASE_URL = "https://www.ip.gov.py"
POLITICS_URL = f"{BASE_URL}/ip/politica/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    )
}


# Matches:
# /ip/2026/07/31/article-slug/
ARTICLE_PATTERN = re.compile(
    r"^/ip/\d{4}/\d{2}/\d{2}/[^/]+/?$"
)


def discover_articles():
    """
    Discover political articles from Agencia IP.

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

        parsed = urlparse(
            full_url
        )

        # Only Agencia IP links
        if parsed.netloc not in {
            "ip.gov.py",
            "www.ip.gov.py",
        }:
            continue

        # Only actual article URLs
        if not ARTICLE_PATTERN.match(
            parsed.path
        ):
            continue

        title = link.get_text(
            " ",
            strip=True,
        )

        # Some cards may have image-only links.
        # We can still keep the URL because
        # Trafilatura will obtain the real title.
        articles[full_url] = {
            "source": "Agencia IP",
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
