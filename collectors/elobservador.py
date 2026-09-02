import re
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://observador.com.py/"

ALLOWED_HOSTS = {
    "observador.com.py",
    "www.observador.com.py",
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


# Known non-article root pages.
EXCLUDED_PATHS = {
    "",
    "inicio",
    "contacto",
    "anuncie",
    "nosotros",
    "quienes-somos",
    "radio",
    "tv",
    "buscar",
    "search",
    "politica-de-privacidad",
    "terminos-y-condiciones",
    "terminos-de-uso",
    "prueba-inicio",
}


# Archive / taxonomy / WordPress paths.
EXCLUDED_PREFIXES = {
    "seccion",
    "etiqueta",
    "author",
    "category",
    "tag",
    "page",
    "feed",
    "wp-content",
    "wp-admin",
    "wp-json",
    "wp-includes",
}


def clean_url(url: str) -> str:
    """
    Remove query parameters and fragments
    and normalize trailing slash.
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
    Observador articles currently use root-level slugs:

        /article-slug/

    Examples:

        /exempleada-de-mocipar-testifico-que-su-trabajo-era-vender-suenos-para-captar-clientes/

        /giuzzio-niega-haber-amenazado-a-fiscales-y-afirma-que-la-unica-amenaza-real-es-la-verdad/

    Archive pages use structures such as:

        /seccion/opinion/
        /etiqueta/paraguay/
        /author/example/
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

    # Current article URLs contain exactly one
    # path component.
    if len(parts) != 1:
        return False

    slug = parts[0].lower().strip()

    if not slug:
        return False

    if slug in EXCLUDED_PATHS:
        return False

    if slug in EXCLUDED_PREFIXES:
        return False

    # Exclude file URLs.
    if re.search(
        r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf|mp3|mp4|xml|json)$",
        slug,
        flags=re.I,
    ):
        return False

    # Exclude purely numeric pages.
    if re.fullmatch(r"\d+", slug):
        return False

    # Exclude date-like standalone paths.
    if re.fullmatch(
        r"\d{4}-\d{1,2}-\d{1,2}",
        slug,
    ):
        return False

    # News headlines normally produce descriptive
    # multi-word WordPress slugs.
    if "-" not in slug:
        return False

    if len(slug) < 12:
        return False

    return True


def discover_articles():
    """
    Discover recent El Observador articles
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

        # Ignore generic anchor text.
        if title.lower() in {
            "leer más",
            "leer mas",
            "ver más",
            "ver mas",
            "más",
            "mas",
        }:
            title = None

        # The same article may appear several times
        # on the homepage. Keep the best title.
        if url not in discovered:

            discovered[url] = {
                "source": "El Observador",
                "title": (
                    title
                    if title
                    else None
                ),
                "url": url,
                "section": "general",
            }

        else:

            old_title = discovered[
                url
            ].get("title")

            if (
                title
                and (
                    not old_title
                    or len(title) > len(old_title)
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
