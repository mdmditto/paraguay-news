import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


BASE_URL = "https://www.telefuturo.com.py"
NEWS_URL = f"{BASE_URL}/noticias"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    )
}


EXCLUDED_PATHS = {
    "",
    "/",
    "/noticias",
    "/programas",
    "/grilla",
    "/contacto",
    "/vivo",
}


def discover_articles():
    """
    Discover news articles from Telefuturo.

    Telefuturo does not currently use /politica/
    in its article URLs. Articles are mostly
    root-level slugs.

    Returns:
        list[dict]
    """

    response = requests.get(
        NEWS_URL,
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

        # Keep only Telefuturo links
        if parsed.netloc not in {
            "telefuturo.com.py",
            "www.telefuturo.com.py",
        }:
            continue

        path = parsed.path.rstrip("/")

        # Ignore known navigation pages
        if path in EXCLUDED_PATHS:
            continue

        # Telefuturo articles are generally:
        #
        # /article-slug
        #
        # Therefore they should have exactly
        # one path component.
        parts = [
            part
            for part in path.split("/")
            if part
        ]

        if len(parts) != 1:
            continue

        title = link.get_text(
            " ",
            strip=True,
        )

        # Ignore image-only links and short
        # navigation labels
        if not title:
            continue

        if len(title) < 15:
            continue

        articles[full_url] = {
            "source": "Telefuturo",
            "title": title,
            "url": full_url,
            "section": "noticias",
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