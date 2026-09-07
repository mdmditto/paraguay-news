import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


BASE_URL = "https://www.ultimahora.com"

DISCOVERY_URLS = [
    BASE_URL,
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    )
}


# Known root-level pages that are NOT articles.
EXCLUDED_PATHS = {
    "paraguay",
    "pib",
    "podcast-uh",
    "newsletters",
    "buscar",
    "busqueda",
    "contacto",
    "nosotros",
    "login",
    "registro",
    "iniciar-sesion",
    "arte-y-espectculos",
    "correo-semanal",
    "mundo-animal",
    "mas-analisis",
    "brand-voice"
}


def clean_url(url):
    """
    Remove query parameters and fragments and
    normalize the trailing slash.
    """

    parsed = urlparse(url)

    return parsed._replace(
        query="",
        fragment="",
    ).geturl().rstrip("/")


def is_article_url(url):
    """
    Determine whether a URL looks like an
    Última Hora article.

    Current article structure:

        /article-slug

    Unlike ABC, the section and date are not
    necessarily part of the URL.
    """

    parsed = urlparse(url)

    # Only accept Última Hora
    if parsed.netloc not in {
        "www.ultimahora.com",
        "ultimahora.com",
    }:
        return False

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    # Articles are currently root-level URLs.
    if len(parts) != 1:
        return False

    slug = parts[0].lower()

    # Known non-article pages
    if slug in EXCLUDED_PATHS:
        return False

    # Ignore files
    if "." in slug:
        return False

    # Ignore purely numeric URLs
    if slug.isdigit():
        return False

    # Article slugs should be reasonably descriptive
    if len(slug) < 10:
        return False

    # Article slugs generally contain multiple words
    if "-" not in slug:
        return False

    return True


def discover_from_page(page_url):
    """
    Discover article URLs from one Última Hora page.
    """

    response = requests.get(
        page_url,
        headers=HEADERS,
        timeout=20,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    articles = {}

    for link in soup.find_all(
        "a",
        href=True,
    ):

        href = link.get("href")

        if not href:
            continue

        full_url = urljoin(
            BASE_URL,
            href,
        )

        full_url = clean_url(
            full_url
        )

        if not is_article_url(
            full_url
        ):
            continue

        articles[full_url] = {
            "source": "Última Hora",
            "title": None,
            "url": full_url,
            "section": "general",
        }

    return articles


def discover_articles():
    """
    Discover articles from Última Hora.

    Returns:
        list[dict]
    """

    articles = {}

    for discovery_url in DISCOVERY_URLS:

        try:

            discovered = discover_from_page(
                discovery_url
            )

            articles.update(
                discovered
            )

            print(
                f"Última Hora: "
                f"{discovery_url} -> "
                f"{len(discovered)} articles"
            )

        except requests.RequestException as exc:

            print(
                f"Última Hora: failed to fetch "
                f"{discovery_url}: {exc}"
            )

    return list(
        articles.values()
    )


if __name__ == "__main__":

    articles = discover_articles()

    print(
        f"\nFound {len(articles)} articles\n"
    )

    for article in articles:

        print(
            f"[{article['section']}] "
            f"{article['url']}"
        )
