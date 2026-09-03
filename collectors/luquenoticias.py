import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.luquenoticias.com.py/"

ALLOWED_HOSTS = {
    "luquenoticias.com.py",
    "www.luquenoticias.com.py",
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
    Remove query parameters and fragments and
    normalize article URLs with a trailing slash.
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
    Luque Noticias articles follow:

        /YYYY/MM/DD/<slug>/

    Example:

        /2022/06/28/
        violento-y-millonario-asalto-en-local-de-chortitzer-en-luque/

    This rejects archives such as:

        /2026/07/
        /2026/07/09/

    as well as:

        /tag/...
        /category/...
        /contacto/
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

    # Article URLs have exactly:
    #
    # year / month / day / slug
    #
    if len(parts) != 4:
        return False

    year, month, day, slug = parts

    if not re.fullmatch(r"\d{4}", year):
        return False

    if not re.fullmatch(r"\d{1,2}", month):
        return False

    if not re.fullmatch(r"\d{1,2}", day):
        return False

    # Validate the actual date.
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

    # Actual stories use descriptive slugs.
    if "-" not in slug:
        return False

    if len(slug) < 6:
        return False

    # Reject numeric-only slugs just in case.
    if re.fullmatch(r"\d+", slug):
        return False

    return True


def discover_articles():
    """
    Discover recent Luque Noticias articles
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

    for link in soup.find_all("a", href=True):

        href = link.get("href", "").strip()

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

        if (
            not title
            or title.lower().strip() in GENERIC_TITLES
        ):
            title = None

        # Luque Noticias repeats stories in several
        # homepage sections such as:
        #
        # - Destacado
        # - Nacionales
        # - Policiales
        # - Deportes
        #
        # Merge duplicates and retain the most
        # informative anchor text.
        if url not in discovered:

            discovered[url] = {
                "source": "Luque Noticias",
                "title": title,
                "url": url,
                "section": "general",
            }

        else:

            existing_title = discovered[url].get(
                "title"
            )

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
