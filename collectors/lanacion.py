import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin


BASE_URL = "https://www.lanacion.com.py"
POLITICS_URL = f"{BASE_URL}/category/politica/"

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
    Discover political articles from La Nación.

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

        # Keep only political articles
        if "/politica/" not in full_url:
            continue

        # Ignore politics landing page
        if full_url.rstrip("/") == POLITICS_URL.rstrip("/"):
            continue

        title = link.get_text(
            " ",
            strip=True,
        )

        if not title:
            continue

        if len(title) < 15:
            continue

        articles[full_url] = {
            "source": "La Nación",
            "title": title,
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
