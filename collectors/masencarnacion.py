import re
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.masencarnacion.com/"

ALLOWED_HOSTS = {
    "masencarnacion.com",
    "www.masencarnacion.com",
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
    "image",
}


def clean_url(url: str) -> str:
    """
    Remove query parameters and fragments.

    Más Encarnación article URLs do not require
    a trailing slash:

        /articulo/<slug>
    """

    parsed = urlparse(url)

    path = parsed.path.rstrip("/")

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
    Más Encarnación articles currently follow:

        /articulo/<descriptive-slug>

    Example:

        /articulo/eby-inicia-entrega-de-recursos-para-
        apoyo-pequenos-productores-de-itapua

    Category URLs such as:

        /categoria/regionales

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
    # articulo / slug
    #
    if len(parts) != 2:
        return False

    prefix, slug = parts

    if prefix.lower() != "articulo":
        return False

    if not slug:
        return False

    # Reject numeric-only slugs.
    if re.fullmatch(r"\d+", slug):
        return False

    # Actual stories use descriptive slugs.
    if "-" not in slug:
        return False

    if len(slug) < 8:
        return False

    # Reject accidental file URLs.
    if re.search(
        r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf|xml|json|mp3|mp4|zip)$",
        slug,
        flags=re.I,
    ):
        return False

    return True


def discover_articles():
    """
    Discover recent Más Encarnación articles
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

        # Articles appear multiple times on the homepage:
        #
        # - Novedades
        # - Noticias destacadas
        # - Noticias más recientes
        # - category blocks
        # - Leer Más links
        #
        # Merge them by normalized URL.
        if url not in discovered:

            discovered[url] = {
                "source": "Más Encarnación",
                "title": title,
                "url": url,
                "section": "general",
            }

        else:

            existing_title = discovered[url].get(
                "title"
            )

            # Prefer the longest useful anchor text.
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
