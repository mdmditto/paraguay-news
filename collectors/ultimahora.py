import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin


BASE_URL = "https://www.ultimahora.com"
POLITICS_URL = f"{BASE_URL}/politica"

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
    Discover political articles from Última Hora.

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

    for link in soup.select(
        "div.PagePromo-title a.Link"
    ):

        href = link.get("href")

        if not href:
            continue

        title = link.get_text(
            " ",
            strip=True,
        )

        if not title:
            continue

        full_url = urljoin(
            BASE_URL,
            href,
        )

        articles[full_url] = {
            "source": "Última Hora",
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
