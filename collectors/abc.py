import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin


BASE_URL = "https://www.abc.com.py"
POLITICS_URL = f"{BASE_URL}/politica/"

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
    Discover political articles from ABC Color.

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

        # Keep only real political article URLs
        if "/politica/" not in full_url:
            continue

        # Ignore the politics landing page
        if (
            full_url.rstrip("/")
            == POLITICS_URL.rstrip("/")
        ):
            continue

        # ABC political article URLs currently contain
        # year/month/day after /politica/
        path = full_url.replace(
            BASE_URL,
            "",
        )

        parts = [
            part
            for part in path.split("/")
            if part
        ]

        # Expected:
        #
        # politica / 2026 / 08 / 21 / article-slug
        #
        if len(parts) < 5:
            continue

        if parts[0] != "politica":
            continue

        # Basic date validation
        if not (
            parts[1].isdigit()
            and len(parts[1]) == 4
            and parts[2].isdigit()
            and parts[3].isdigit()
        ):
            continue

        # The anchor often says only "Ver más",
        # so we should not use anchor text as the title.
        articles[full_url] = {
            "source": "ABC Color",
            "title": None,
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

        print(article["url"])
