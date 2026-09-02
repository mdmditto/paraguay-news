import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.cronica.com.py/"

ALLOWED_HOSTS = {
    "cronica.com.py",
    "www.cronica.com.py",
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
    and normalize the trailing slash.
    """

    parsed = urlparse(url)

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip("/") + "/",
            "",
            "",
            "",
        )
    )


def is_article_url(url: str) -> bool:
    """
    Crónica articles follow:

        /YYYY/MM/DD/article-slug/

    Example:

        /2026/08/30/diego-dominguez-campeon-orgullo-nacional/
    """

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    host = parsed.netloc.lower()

    if host not in ALLOWED_HOSTS:
        return False

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    # Expected:
    #
    # YYYY / MM / DD / slug
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

    # Validate that the date is real.
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

    # Normal article slugs are descriptive.
    if len(slug) < 5:
        return False

    return True


def discover_articles():
    """
    Discover recent Crónica articles
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

        # The homepage may link to the same
        # article multiple times.
        #
        # Keep one record per URL and retain
        # the best title encountered.
        if url not in discovered:

            discovered[url] = {
                "source": "Crónica",
                "title": (
                    title
                    if title
                    else None
                ),
                "url": url,
                "section": "general",
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

        print(article["title"])
        print(article["url"])
        print()
