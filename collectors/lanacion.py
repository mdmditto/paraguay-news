import re
import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


BASE_URL = "https://www.lanacion.com.py"

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


# These are known non-article areas.
#
# IMPORTANT:
# We do NOT use a whitelist of sections such as
# "politica", "pais", "negocios", etc.
#
# This allows La Nación to add new sections without
# breaking the collector.
EXCLUDED_FIRST_PATHS = {
    "category",
    "tag",
    "author",
    "autor",
    "buscar",
    "search",
    "contacto",
    "nosotros",
    "login",
    "registro",
    "feed",
    "wp-json",
    "wp-admin",
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
    Determine whether a URL looks like a La Nación
    article.

    Current article structure:

        /section/YYYY/MM/DD/article-slug/

    Examples:

        /politica/2026/07/02/article-slug/
        /pais/2026/01/02/article-slug/
        /negocios/2026/08/16/article-slug/
        /editorial/2026/08/20/article-slug/

    We intentionally do not restrict the section to a
    fixed list.
    """

    parsed = urlparse(url)

    # Only La Nación
    if parsed.netloc not in {
        "www.lanacion.com.py",
        "lanacion.com.py",
    }:
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

    section = parts[0].lower()
    year = parts[1]
    month = parts[2]
    day = parts[3]
    slug = parts[4]

    # Reject known non-article areas
    if section in EXCLUDED_FIRST_PATHS:
        return False

    # Validate date
    if not re.fullmatch(
        r"\d{4}",
        year,
    ):
        return False

    if not re.fullmatch(
        r"\d{1,2}",
        month,
    ):
        return False

    if not re.fullmatch(
        r"\d{1,2}",
        day,
    ):
        return False

    try:
        year_int = int(year)
        month_int = int(month)
        day_int = int(day)

    except ValueError:
        return False

    # Basic date sanity checks
    if not (
        2000 <= year_int <= 2100
    ):
        return False

    if not (
        1 <= month_int <= 12
    ):
        return False

    if not (
        1 <= day_int <= 31
    ):
        return False

    # Article slug must be descriptive
    if not slug:
        return False

    if len(slug) < 10:
        return False

    # La Nación article slugs are generally
    # composed of multiple words.
    if "-" not in slug:
        return False

    # Reject obvious files
    if "." in slug:
        return False

    return True


def get_section_from_url(url):
    """
    Extract the section from a La Nación article URL.

    Example:

        /politica/2026/07/02/article-slug/

    returns:

        politica
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
    Discover La Nación articles from one page.
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

        # Only keep valid article URLs
        if not is_article_url(
            full_url
        ):
            continue

        section = get_section_from_url(
            full_url
        )

        # Use anchor text when it looks useful.
        # The detail extractor can replace this later
        # with the definitive article title.
        title = link.get_text(
            " ",
            strip=True,
        )

        if title:
            title = title.strip()

        if not title or len(title) < 10:
            title = None

        articles[full_url] = {
            "source": "La Nación",
            "title": title,
            "url": full_url,
            "section": section,
        }

    return articles


def discover_articles():
    """
    Discover articles from La Nación.

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
                f"La Nación: "
                f"{discovery_url} -> "
                f"{len(discovered)} articles"
            )

        except requests.RequestException as exc:

            print(
                f"La Nación: failed to fetch "
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
            f"{article['title']}"
        )

        print(
            article["url"]
        )

        print()