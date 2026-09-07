import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


BASE_URL = "https://www.monumental.com.py"

DISCOVERY_URLS = [
    f"{BASE_URL}/noticias",
]


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    )
}


# Known paths under /noticias/ that are NOT individual articles.
EXCLUDED_PATHS = {
    "noticias",
    "buscar",
    "search",
    "contacto",
    "nosotros",
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
    Determine whether a URL looks like a Monumental
    article.

    Current article structure:

        /noticias/<section>/<slug>

    Some sections have a second-level subsection:

        /noticias/futbol-a-lo-grande/copa-mundial-2026/<slug>

    Therefore we identify articles based on the
    /noticias/ prefix and the final path component,
    rather than requiring a fixed number of path parts.
    """

    parsed = urlparse(url)

    # Only Monumental
    if parsed.netloc not in {
        "www.monumental.com.py",
        "monumental.com.py",
    }:
        return False

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    # Must start with /noticias/
    if not parts:
        return False

    if parts[0].lower() != "noticias":
        return False

    # /noticias/ itself is the news landing page
    if len(parts) < 3:
        return False

    # Last component should be the article slug
    slug = parts[-1].lower()

    # Known non-article paths
    if slug in EXCLUDED_PATHS:
        return False

    # Ignore files
    if "." in slug:
        return False

    # Ignore numeric-only URLs
    if slug.isdigit():
        return False

    # Article slugs should be descriptive
    if len(slug) < 10:
        return False

    # Monumental article slugs generally contain
    # multiple words separated by hyphens.
    if "-" not in slug:
        return False

    return True


def get_section_from_url(url):
    """
    Extract the first section after /noticias/.

    Examples:

        /noticias/nacionales/article
            -> nacionales

        /noticias/politica/article
            -> politica

        /noticias/futbol-a-lo-grande/copa-mundial-2026/article
            -> futbol-a-lo-grande
    """

    parsed = urlparse(url)

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    if len(parts) < 2:
        return "general"

    return parts[1].lower()


def discover_from_page(page_url):
    """
    Discover Monumental articles from one page.
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

        section = get_section_from_url(
            full_url
        )

        # Anchor text is often useful on Monumental,
        # but the article detail extractor should be
        # considered the authoritative source for title.
        title = link.get_text(
            " ",
            strip=True,
        )

        if title:
            title = title.strip()

        if not title or len(title) < 10:
            title = None

        articles[full_url] = {
            "source": "Monumental",
            "title": title,
            "url": full_url,
            "section": section,
        }

    return articles


def discover_articles():
    """
    Discover all available Monumental articles.

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
                f"Monumental: "
                f"{discovery_url} -> "
                f"{len(discovered)} articles"
            )

        except requests.RequestException as exc:

            print(
                f"Monumental: failed to fetch "
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