import re
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://amambaynews.com/"

ALLOWED_HOSTS = {
    "amambaynews.com",
    "www.amambaynews.com",
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


# Amambay News category/archive pages use the same
# root-level .html structure as articles, so these
# need to be explicitly excluded.
EXCLUDED_HTML_SLUGS = {
    "locales",
    "nacionales",
    "mundo",
    "policiales",
    "deportes",
    "variedades",
    "judiciales",

    # Common static/navigation pages.
    "contacto",
    "nosotros",
    "quienes-somos",
    "buscar",
    "search",
    "radio",
    "politica-de-privacidad",
    "terminos-y-condiciones",
    "terminos-de-uso",
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
    Remove query parameters and fragments.

    Amambay News article URLs end in .html,
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
    Amambay News articles currently follow:

        /descriptive-headline-slug.html

    Examples:

        /juez-de-la-corte-de-brasil-en-el-foco-de-una-trama-corrupta.html

        /renuncian-20-medicos-al-hospital-de-cde-y-25-de-san-pablo.html

    Category pages also use .html:

        /nacionales.html
        /policiales.html
        /deportes.html

    so those are explicitly excluded.
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

    # Articles are currently at the root.
    if len(parts) != 1:
        return False

    filename = parts[0].strip()

    if not filename.lower().endswith(".html"):
        return False

    slug = filename[:-5].lower().strip()

    if not slug:
        return False

    # Reject categories/static pages.
    if slug in EXCLUDED_HTML_SLUGS:
        return False

    # Reject numeric pages.
    if re.fullmatch(r"\d+", slug):
        return False

    # Reject date-like archive slugs.
    if re.fullmatch(
        r"\d{4}(?:-\d{1,2})?(?:-\d{1,2})?",
        slug,
    ):
        return False

    # Actual articles use descriptive headline slugs.
    if "-" not in slug:
        return False

    if len(slug) < 10:
        return False

    return True


def discover_articles():
    """
    Discover recent Amambay News articles
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

        # The same article can appear in:
        # - Últimas noticias
        # - Noticias policiales
        # - Noticias nacionales
        # - Más leídas
        #
        # Deduplicate by URL and keep the best title.
        if url not in discovered:

            discovered[url] = {
                "source": "Amambay News",
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
