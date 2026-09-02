import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.laclave.com.py/"

ALLOWED_HOSTS = {
    "laclave.com.py",
    "www.laclave.com.py",
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
    La Clave articles follow:

        /YYYY/MM/DD/<slug>/

    Example:

        /2026/08/25/
        alto-parana-lidera-la-siembra-de-maiz-y-soja-zafrina-en-2026/
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

    # Article:
    #
    # YYYY / MM / DD / slug
    #
    # This automatically excludes monthly archives:
    #
    # /2026/08/
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

    # Make sure the URL contains a real date.
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

    # Article slugs are descriptive.
    if len(slug) < 6:
        return False

    # Helps avoid miscellaneous date-based URLs.
    if "-" not in slug:
        return False

    return True


def discover_articles():
    """
    Discover recent Diario La Clave articles
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

        # Avoid generic anchor labels.
        if title.lower() in {
            "leer más",
            "leer mas",
            "ver más",
            "ver mas",
            "más",
            "mas",
        }:
            title = None

        # The homepage may expose the same article
        # through image, headline, sidebar, etc.
        #
        # Merge duplicates and keep the best title.
        if url not in discovered:

            discovered[url] = {
                "source": "La Clave",
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

        print(
            article["url"]
        )

        print()
