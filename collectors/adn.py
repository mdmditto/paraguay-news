import re
import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


BASE_URL = "https://www.adndigital.com.py"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


EXCLUDED_PREFIXES = (
    "/category/",
    "/author/",
    "/tag/",
    "/page/",
    "/wp-content/",
    "/wp-admin/",
    "/wp-json/",
    "/feed/",
)

EXCLUDED_PATHS = {
    "/",
}


def clean_url(url: str) -> str:
    """
    Remove query parameters and fragments.
    """

    parsed = urlparse(url)

    return (
        f"{parsed.scheme}://"
        f"{parsed.netloc}"
        f"{parsed.path}"
    )


def is_article_url(url: str) -> bool:
    """
    Decide whether a URL looks like an ADN Digital article.

    Current ADN Digital articles use root-level slugs:

        /orue-propone-debatir-ajustes-a-regimenes-especiales-sin-aumentar-impuestos/
    """

    parsed = urlparse(url)

    if parsed.netloc not in {
        "adndigital.com.py",
        "www.adndigital.com.py",
    }:
        return False

    path = parsed.path

    if not path:
        return False

    if path in EXCLUDED_PATHS:
        return False

    if any(
        path.startswith(prefix)
        for prefix in EXCLUDED_PREFIXES
    ):
        return False

    # Ignore files and assets.
    if path.lower().endswith(
        (
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
            ".svg",
            ".pdf",
            ".xml",
            ".css",
            ".js",
            ".ico",
        )
    ):
        return False

    parts = [
        part
        for part in path.split("/")
        if part
    ]

    # Current articles are root-level URLs:
    #
    # /article-slug/
    if len(parts) != 1:
        return False

    slug = parts[0]

    # Reject numeric/archive-like pages.
    if slug.isdigit():
        return False

    # Reject date-only slugs if the site exposes any.
    if re.fullmatch(
        r"\d{1,2}-\d{1,2}-(?:\d{2}|\d{4})",
        slug,
    ):
        return False

    # Real article slugs should normally contain
    # at least one hyphen.
    if "-" not in slug:
        return False

    return True


def discover_articles():
    """
    Discover current ADN Digital articles.

    Returns:
        list[dict]
    """

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    response = session.get(
        BASE_URL,
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

        full_url = clean_url(
            full_url
        )

        if not is_article_url(
            full_url
        ):
            continue

        title = link.get_text(
            " ",
            strip=True,
        )

        if full_url not in articles:

            articles[full_url] = {
                "source": "ADN Digital",
                "title": title or None,
                "url": full_url,
                "section": "general",
            }

        # The first occurrence can be an image link,
        # so replace an empty title if we later find
        # the text link for the same article.
        elif (
            not articles[full_url]["title"]
            and title
        ):

            articles[full_url]["title"] = title

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
