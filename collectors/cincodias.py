import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


BASE_URL = "https://5dias.com.py"
NEWS_URL = f"{BASE_URL}/noticiasdeldia"

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
    Discover current articles from 5Días.

    Unlike the other collectors, 5Días is mainly
    an economics/business outlet, so we collect
    its general current-news feed and classify
    political relevance later.

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

        # Keep only 5Días
        if parsed.netloc not in {
            "5dias.com.py",
            "www.5dias.com.py",
        }:
            continue

        # Current 5Días articles use:
        #
        # /article/article-slug
        #
        if not parsed.path.startswith(
            "/article/"
        ):
            continue

        # Make sure there is an actual slug
        slug = parsed.path.replace(
            "/article/",
            "",
        ).strip("/")

        if not slug:
            continue

        title = link.get_text(
            " ",
            strip=True,
        )

        articles[full_url] = {
            "source": "5Días",
            "title": title or None,
            "url": full_url,
            "section": "general",
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
