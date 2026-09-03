import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.reddigitalsanpedro.com.py/"

ALLOWED_HOSTS = {
    "reddigitalsanpedro.com.py",
    "www.reddigitalsanpedro.com.py",
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


GENERIC_TITLES = {
    "leer",
    "leer más",
    "leer mas",
    "ver más",
    "ver mas",
    "más",
    "mas",
    "read more",
    "previous",
    "next",
    "anterior",
    "siguiente",
}


def clean_url(url: str) -> str:
    """
    Remove query parameters and fragments and normalize
    article URLs with a trailing slash.

    Example:

        /nacionales/2026/09/01/article-slug/
    """

    parsed = urlparse(url)

    path = parsed.path.rstrip("/")

    if path:
        path += "/"

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            path,
            "",
            "",
            "",
        )
    )


def is_article_url(url: str) -> bool:
    """
    Red Digital San Pedro articles currently follow:

        /<section>/YYYY/MM/DD/<slug>/

    Examples:

        /nacionales/2026/09/01/article-slug/

        /locales/2026/08/11/article-slug/

    Section/archive pages such as:

        /seccion/nacionales/

    are automatically rejected.
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
    # section / YYYY / MM / DD / slug
    #
    if len(parts) != 5:
        return False

    section, year, month, day, slug = parts

    # Explicitly reject archive/utility prefixes.
    if section.lower() in {
        "seccion",
        "tag",
        "author",
        "autor",
        "page",
        "feed",
        "wp-admin",
        "wp-content",
        "wp-includes",
        "wp-json",
    }:
        return False

    if not section:
        return False

    # Validate date.
    if not re.fullmatch(r"\d{4}", year):
        return False

    if not re.fullmatch(r"\d{1,2}", month):
        return False

    if not re.fullmatch(r"\d{1,2}", day):
        return False

    try:
        datetime(
            int(year),
            int(month),
            int(day),
        )
    except ValueError:
        return False

    if not slug:
        return False

    # Reject numeric-only slugs.
    if re.fullmatch(r"\d+", slug):
        return False

    # Actual article slugs are descriptive.
    if "-" not in slug:
        return False

    if len(slug) < 8:
        return False

    # Reject accidental files/assets.
    if re.search(
        r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf|xml|json|mp3|mp4|zip)$",
        slug,
        flags=re.I,
    ):
        return False

    return True


def get_section_from_url(url: str) -> str:
    """
    Extract the section from an article URL.

    Example:

        /nacionales/2026/09/01/article-slug/

    returns:

        nacionales
    """

    parsed = urlparse(url)

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    if len(parts) == 5:
        return parts[0].lower()

    return "general"


def discover_articles():
    """
    Discover recent Red Digital San Pedro articles
    directly from the homepage.

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

    for link in soup.find_all("a", href=True):

        href = link.get("href", "").strip()

        if not href:
            continue

        url = clean_url(
            urljoin(BASE_URL, href)
        )

        if not is_article_url(url):
            continue

        title = link.get_text(
            " ",
            strip=True,
        )

        if (
            not title
            or title.lower().strip() in GENERIC_TITLES
        ):
            title = None

        # Stories are repeated across homepage components:
        #
        # - Destacados
        # - Más destacadas
        # - section blocks
        # - Recientes
        # - Noticias recientes
        #
        # Deduplicate by normalized URL.
        if url not in discovered:

            discovered[url] = {
                "source": "Red Digital San Pedro",
                "title": title,
                "url": url,
                "section": get_section_from_url(url),
            }

        else:

            existing_title = discovered[url].get(
                "title"
            )

            # Prefer the most informative anchor text.
            if (
                title
                and (
                    not existing_title
                    or len(title) > len(existing_title)
                )
            ):
                discovered[url]["title"] = title

    return list(discovered.values())


if __name__ == "__main__":

    articles = discover_articles()

    print(f"Found {len(articles)} articles\n")

    for article in articles:

        print(
            f"[{article['section']}] "
            f"{article['title']}"
        )

        print(article["url"])
        print()
