import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


BASE_URL = "https://unicanal.com.py"
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
    Discover political articles from Unicanal.

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

    for link in soup.find_all("a", href=True):

        href = link.get("href")

        if not href:
            continue

        full_url = urljoin(
            BASE_URL,
            href,
        )

        parsed = urlparse(full_url)

        # Keep only Unicanal
        if parsed.netloc not in {
            "unicanal.com.py",
            "www.unicanal.com.py",
        }:
            continue

        # Real political articles use /politica/
        if not parsed.path.startswith("/politica/"):
            continue

        # Exclude the politics section itself, if encountered
        if parsed.path.rstrip("/") == "/politica":
            continue

        title = link.get_text(
            " ",
            strip=True,
        )

        # Ignore links without meaningful text
        if not title or len(title) < 10:
            continue

        articles[full_url] = {
            "source": "Unicanal",
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
