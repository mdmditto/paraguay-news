import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.elpoder.com.py/"

ALLOWED_HOSTS = {
    "elpoder.com.py",
    "www.elpoder.com.py",
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
    Remove query parameters and fragments
    and normalize article URLs.
    """

    parsed = urlparse(url)

    path = parsed.path.rstrip("/") + "/"

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            path,
            "",
            "",
            "",
        )
    )


def is_article_url(url: str) -> bool:
    """
    El Poder article URLs follow:

        /<section>/YYYY/MM/DD/<slug>/

    Example:

        /nacionales/2026/08/31/
        crisis-en-salud-mas-de-430-medicos-renuncian-y-
        hospitales-pierden-planteles-completos/
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

    if not section:
        return False

    if section.lower() in {
        "category",
        "author",
        "tag",
        "page",
        "wp-content",
        "wp-admin",
        "wp-json",
    }:
        return False

    if not re.fullmatch(r"\d{4}", year):
        return False

    if not re.fullmatch(r"\d{1,2}", month):
        return False

    if not re.fullmatch(r"\d{1,2}", day):
        return False

    # Make sure the date is valid.
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

    if len(slug) < 5:
        return False

    # Most actual articles have descriptive slugs.
    if "-" not in slug:
        return False

    return True


def get_section_from_url(url: str) -> str:
    """
    Extract the article section from the URL.

    Example:

        /nacionales/2026/08/31/article/

    becomes:

        nacionales
    """

    parsed = urlparse(url)

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    if not parts:
        return "general"

    return parts[0].lower()


def discover_articles():
    """
    Discover recent El Poder articles
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

        title = link.get_text(
            " ",
            strip=True,
        )

        if url not in discovered:

            discovered[url] = {
                "source": "El Poder",
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
            # The homepage links to the same
            # article multiple times.
            #
            # Keep the most descriptive title.
            existing_title = (
                discovered[url]
                .get("title")
            )

            if (
                title
                and (
                    not existing_title
                    or len(title)
                    > len(existing_title)
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

        print(
            article["url"]
        )

        print()
