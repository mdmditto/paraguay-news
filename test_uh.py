import re
import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


BASE_URL = "https://www.ultimahora.com"

DISCOVERY_URLS = [
    BASE_URL
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    )
}


# Sections that are actual article sections on ABC.
#
# This is intentionally not used to restrict discovery.
# It is mainly used to distinguish article URLs from
# other ABC pages.
ARTICLE_SECTIONS = {
    "nacionales",
    "politica",
    "pais",
    "economia",
    "deportes",
    "sucesos",
    "opinion",
    "interior",
    "arte-y-espectaculos"
}


EXCLUDED_FIRST_PATHS = {
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
        "colecciones-uh"
        "politica-de-uso-de-la-ia"
        "politica-de-calidad"
}


def clean_url(url):
    """
    Remove query parameters and fragments.

    This is important because ABC can expose the same
    article with tracking/query parameters.
    """

    parsed = urlparse(url)

    clean = parsed._replace(
        query="",
        fragment="",
    ).geturl()

    return clean.rstrip("/")


def is_article_url(url):
    """
    Determine whether a URL looks like an ABC Color article.

    ABC article URLs generally look like:

        /politica/2026/09/07/article-slug
        /nacionales/2026/09/07/article-slug
        /economia/2026/09/07/article-slug
        /deportes/2026/09/07/article-slug

    We don't restrict discovery to one section.
    """

    url = clean_url(url)

    parsed = urlparse(url)

    # Only ABC itself
    if parsed.netloc not in {
        "www.abc.com.py",
        "abc.com.py",
    }:
        return False

    path = parsed.path

    parts = [
        part
        for part in path.split("/")
        if part
    ]

    # Expected:
    #
    # section / YYYY / MM / DD / slug
    #
    if len(parts) < 5:
        return False

    section = parts[0].lower()
    year = parts[1]
    month = parts[2]
    day = parts[3]
    slug = parts[4]

    # Reject known non-article areas
    if section in EXCLUDED_FIRST_PATHS:
        return False

    # Date must look like YYYY/MM/DD
    if not (
        re.fullmatch(r"\d{4}", year)
        and re.fullmatch(r"\d{1,2}", month)
        and re.fullmatch(r"\d{1,2}", day)
    ):
        return False

    # Basic date validation
    try:
        year_int = int(year)
        month_int = int(month)
        day_int = int(day)

        if not (2000 <= year_int <= 2100):
            return False

        if not (1 <= month_int <= 12):
            return False

        if not (1 <= day_int <= 31):
            return False

    except ValueError:
        return False

    # Article slug should be descriptive
    if not slug:
        return False

    if len(slug) < 8:
        return False

    # Most ABC articles have descriptive hyphenated slugs
    if "-" not in slug:
        return False

    # Reject obvious files
    if "." in slug:
        return False

    return True


def get_section_from_url(url):
    """
    Extract the first path component.

    Example:

        /politica/2026/09/07/foo
        -> politica
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


def discover_from_page(page_url):
    """
    Discover ABC articles from one page.
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

        full_url = clean_url(full_url)

        if not is_article_url(full_url):
            continue

        section = get_section_from_url(
            full_url
        )

        articles[full_url] = {
            "source": "ABC Color",
            "title": None,
            "url": full_url,
            "section": section,
        }

    return articles


def discover_articles():
    """
    Discover articles from ABC Color.

    Articles are discovered from both:
        - ABC homepage
        - Últimas Noticias

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
                f"ABC: {discovery_url} -> "
                f"{len(discovered)} articles"
            )

        except requests.RequestException as exc:

            print(
                f"ABC: failed to fetch "
                f"{discovery_url}: {exc}"
            )

    return list(
        articles.values()
    )


if __name__ == "__main__":

    articles = discover_articles()

    print(
        f"\nFound {len(articles)} ABC articles\n"
    )

    for article in articles:

        print(
            f"[{article['section']}] "
            f"{article['url']}"
        )
