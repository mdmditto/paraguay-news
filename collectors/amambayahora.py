import re
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://amambayahora.com.py/"

ALLOWED_HOSTS = {
    "amambayahora.com.py",
    "www.amambayahora.com.py",
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
    "leer noticia",
    "leer noticia →",
    "seguir leyendo",
    "seguir leyendo →",
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
    Remove query parameters and fragments.

    Amambay Ahora article URLs end in .html,
    so no trailing slash is added.
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
    Amambay Ahora articles currently follow:

        /descriptive-headline-slug.html

    Example:

        /suboficial-herido-de-un-disparo-en-el-hombro.html

    Section pages such as:

        /locales
        /nacionales
        /mundo
        /policiales

    are automatically rejected because they
    do not end in .html.
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

    # Current articles live directly at root level.
    if len(parts) != 1:
        return False

    filename = parts[0].strip()

    if not filename.lower().endswith(".html"):
        return False

    slug = filename[:-5].lower().strip()

    if not slug:
        return False

    # Reject numeric-only pages.
    if re.fullmatch(r"\d+", slug):
        return False

    # Reject date-like pages if any appear.
    if re.fullmatch(
        r"\d{4}(?:-\d{1,2})?(?:-\d{1,2})?",
        slug,
    ):
        return False

    # Real news stories use descriptive slugs.
    if "-" not in slug:
        return False

    if len(slug) < 8:
        return False

    return True


def discover_articles():
    """
    Discover recent Amambay Ahora articles
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

        # Stories appear multiple times:
        #
        # - ticker
        # - Último Momento
        # - Lo Último
        # - category cards
        #
        # Merge by URL and retain the best title.
        if url not in discovered:

            discovered[url] = {
                "source": "Amambay Ahora",
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
