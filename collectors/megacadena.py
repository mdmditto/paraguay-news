import re
import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


BASE_URL = "https://megacadena.com.py"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
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
    "/radio/",
    "/tv/",
    "/contactenos/",
    "/politica-de-privacidad/",
    "/terminos-de-uso/",
    "/trabaja-con-nosotros/",
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
    Decide whether a URL looks like a Megacadena article.

    Current Megacadena articles use root-level slugs:

        /dnit-agilizara-el-acceso-a-movimientos-bancarios-para-controles-tributarios/
    """

    parsed = urlparse(url)

    if parsed.netloc not in {
        "megacadena.com.py",
        "www.megacadena.com.py",
    }:
        return False

    path = parsed.path

    if not path:
        return False

    if path in EXCLUDED_PATHS:
        return False

    # Exclude WordPress archive/system URLs.
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

    # Megacadena's current individual articles
    # use a single root-level slug.
    if len(parts) != 1:
        return False

    slug = parts[0]

    # Reject purely numeric pages.
    if slug.isdigit():
        return False

    # Reject date-only slugs if any are exposed.
    if re.fullmatch(
        r"\d{1,2}-\d{1,2}-(?:\d{2}|\d{4})",
        slug,
    ):
        return False

    # Most real article slugs contain hyphens.
    # This also removes many simple navigation pages.
    if "-" not in slug:
        return False

    return True


def discover_articles():
    """
    Discover current Megacadena articles from the homepage.

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

        # The homepage may link the same article
        # from the image, headline and other elements.
        if full_url not in articles:

            articles[full_url] = {
                "source": "Megacadena",
                "title": title or None,
                "url": full_url,
                "section": "general",
            }

        # If the first link was an image and had
        # no text, use a later textual link.
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
