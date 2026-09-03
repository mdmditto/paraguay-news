import re
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://pedrojuandigital.com.py/"

ALLOWED_HOSTS = {
    "pedrojuandigital.com.py",
    "www.pedrojuandigital.com.py",
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


EXCLUDED_PATHS = {
    "",
    "inicio",
    "home",
    "contacto",
    "nosotros",
    "quienes-somos",
    "buscar",
    "search",
    "radio",
    "tv",
    "politica-de-privacidad",
    "terminos-y-condiciones",
    "terminos-de-uso",
}


EXCLUDED_PREFIXES = {
    "category",
    "author",
    "tag",
    "page",
    "feed",
    "wp-admin",
    "wp-content",
    "wp-includes",
    "wp-json",
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
    normalize URLs with a trailing slash.
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
    Pedro Juan Digital currently uses root-level
    article slugs.

    Example:

        /emotiva-despedida-de-la-seleccionparaguaya-
        de-futbol-de-salon-c15/

    Category archives use:

        /category/locales/
        /category/nacionales/
        /category/policiales/

    and are automatically rejected.
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

    # Current articles have exactly one path component.
    if len(parts) != 1:
        return False

    slug = parts[0].lower().strip()

    if not slug:
        return False

    if slug in EXCLUDED_PATHS:
        return False

    if slug in EXCLUDED_PREFIXES:
        return False

    # Exclude files/assets.
    if re.search(
        r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf|xml|json|mp3|mp4|zip)$",
        slug,
        flags=re.I,
    ):
        return False

    # Numeric-only paths are not articles.
    if re.fullmatch(r"\d+", slug):
        return False

    # Reject possible date/archive paths.
    if re.fullmatch(
        r"\d{4}(?:-\d{1,2})?(?:-\d{1,2})?",
        slug,
    ):
        return False

    # Real article URLs use descriptive slugs.
    if "-" not in slug:
        return False

    if len(slug) < 10:
        return False

    return True


def discover_articles():
    """
    Discover recent Pedro Juan Digital articles
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

        # Articles are repeated in several homepage
        # blocks: "Lo último", "Últimas entradas",
        # Locales, Nacionales, Policiales, etc.
        #
        # Deduplicate by URL and retain the best title.
        if url not in discovered:

            discovered[url] = {
                "source": "Pedro Juan Digital",
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
