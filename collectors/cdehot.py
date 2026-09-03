import re
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.cdehot.com.py/"

ALLOWED_HOSTS = {
    "cdehot.com.py",
    "www.cdehot.com.py",
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
    Remove query parameters, fragments,
    and trailing slash.
    """

    parsed = urlparse(url)

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            "",
            "",
        )
    )


def is_article_url(url: str) -> bool:
    """
    CDE Hot articles currently follow:

        /noticia/<section>/<slug>

    Example:

        /noticia/nacionales/
        miercoles-con-amanecer-fresco-nieblas-y-una-tarde-calida
    """

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.netloc.lower() not in ALLOWED_HOSTS:
        return False

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    # Expected:
    #
    # noticia / section / slug
    #
    if len(parts) != 3:
        return False

    prefix, section, slug = parts

    if prefix.lower() != "noticia":
        return False

    if not section:
        return False

    if not slug:
        return False

    # Actual article slugs are descriptive.
    if len(slug) < 8:
        return False

    if "-" not in slug:
        return False

    # Reject obvious numeric-only slugs.
    if re.fullmatch(r"\d+", slug):
        return False

    return True


def get_section_from_url(url: str) -> str:
    """
    Extract the section from:

        /noticia/nacionales/article-slug

    Returns:

        nacionales
    """

    parsed = urlparse(url)

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    if len(parts) >= 3:
        return parts[1].lower()

    return "general"


def discover_articles():
    """
    Discover recent CDE Hot articles
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

    discovered = {}

    for link in soup.find_all(
        "a",
        href=True,
    ):

        href = link.get(
            "href",
            "",
        ).strip()

        if not href:
            continue

        url = urljoin(
            BASE_URL,
            href,
        )

        url = clean_url(url)

        if not is_article_url(url):
            continue

        title = link.get_text(
            " ",
            strip=True,
        )

        # Ignore generic labels.
        if title.lower() in {
            "ver más",
            "ver mas",
            "leer más",
            "leer mas",
            "más",
            "mas",
        }:
            title = None

        # Same story can appear several times
        # on the homepage.
        #
        # Merge duplicates and retain the best title.
        if url not in discovered:

            discovered[url] = {
                "source": "CDE Hot",
                "title": (
                    title
                    if title
                    else None
                ),
                "url": url,
                "section": get_section_from_url(
                    url
                ),
            }

        else:

            existing_title = (
                discovered[url]
                .get("title")
            )

            if (
                title
                and (
                    not existing_title
                    or len(title) > len(existing_title)
                )
            ):
                discovered[url][
                    "title"
                ] = title

    return list(
        discovered.values()
    )


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

        print(article["url"])
        print()
