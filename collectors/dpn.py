import re
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.dpn.com.py/"

ALLOWED_HOSTS = {
    "dpn.com.py",
    "www.dpn.com.py",
    "diarioparaguayo.com",
    "www.diarioparaguayo.com",
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def clean_url(url: str) -> str:
    """
    Remove query parameters and fragments and normalize trailing slash.
    """

    parsed = urlparse(url)

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip("/"),
            "",
            "",
            "",
        )
    )


def is_article_url(url: str) -> bool:
    """
    DPN article URLs currently use:

        /noticia/<slug>

    Examples:
        /noticia/rector-critica-a-pena-por-divertirse-en-rally-mientras-medicos-protestan
        /noticia/palmeiras-empata-ante-mirassol-con-gol-de-mauricio
    """

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    host = parsed.netloc.lower()

    if host not in ALLOWED_HOSTS:
        return False

    path = parsed.path.rstrip("/")

    match = re.fullmatch(
        r"/noticia/([^/]+)",
        path,
    )

    if not match:
        return False

    slug = match.group(1)

    if not slug:
        return False

    # Articles use descriptive slugs.
    if len(slug) < 10:
        return False

    if "-" not in slug:
        return False

    return True


def discover_articles():
    """
    Discover recent DPN / Diario Paraguayo articles
    from the homepage.

    Returns:
        list[dict]
    """

    response = requests.get(
        BASE_URL,
        headers=HEADERS,
        timeout=20,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    articles = []
    seen = set()

    for link in soup.find_all(
        "a",
        href=True,
    ):

        href = link["href"].strip()

        if not href:
            continue

        url = urljoin(
            BASE_URL,
            href,
        )

        url = clean_url(url)

        if not is_article_url(url):
            continue

        if url in seen:
            continue

        seen.add(url)

        title = link.get_text(
            " ",
            strip=True,
        )

        # Some links wrap an image and contain no useful text.
        # Another link to the same article usually contains the title.
        if not title:
            title = None

        articles.append(
            {
                "source": "DPN",
                "title": title,
                "url": url,
                "section": "general",
            }
        )

    return articles


if __name__ == "__main__":

    articles = discover_articles()

    print(
        f"Found {len(articles)} articles\n"
    )

    for article in articles:

        print(
            f"[{article['section']}] "
            f"{article['title']}"
        )

        print(
            article["url"]
        )

        print()
