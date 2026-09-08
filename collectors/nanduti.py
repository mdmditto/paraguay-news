import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


BASE_URL = "https://nanduti.com.py"

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


EXCLUDED_PATHS = {
    "buscar",
    "search",
    "contacto",
    "nosotros",
    "login",
    "registro",
    "politica",
    "nacionales",
    "actualidad",
    "destacadas",
    "deportes",
    "economia",
    "cultura",
    "internacionales",
    "policiales",
    "audios",
    "programacion",
    "en-vivo",
    "radio",
    "podcasts",
    "newsletter",
    "anuncie-con-nosotros",
}


def clean_url(url):
    """
    Remove query parameters and fragments.
    """

    parsed = urlparse(url)

    return parsed._replace(
        query="",
        fragment="",
    ).geturl().rstrip("/")


def is_article_url(url):
    """
    Determine whether a URL looks like a Ñanduti article.

    Ñanduti currently uses root-level article URLs:

        https://nanduti.com.py/article-slug
    """

    parsed = urlparse(url)

    # Only Ñanduti
    if parsed.netloc not in {
        "nanduti.com.py",
        "www.nanduti.com.py",
    }:
        return False

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    # Article URLs are root-level URLs.
    if len(parts) != 1:
        return False

    slug = parts[0].lower()

    # Ignore known static/section pages
    if slug in EXCLUDED_PATHS:
        return False

    # Ignore files
    if "." in slug:
        return False

    # Ignore numeric URLs
    if slug.isdigit():
        return False

    # Article slugs should normally be descriptive
    if len(slug) < 20:
        return False

    # Ñanduti article slugs use hyphens
    if "-" not in slug:
        return False

    return True


def discover_from_page(page_url):
    """
    Discover article URLs from a Ñanduti page.
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

        full_url = clean_url(
            urljoin(
                BASE_URL,
                href,
            )
        )

        if not is_article_url(full_url):
            continue

        title = link.get_text(
            " ",
            strip=True,
        )

        if title:
            title = title.strip()

        # Avoid navigation links with very little text
        if not title or len(title) < 10:
            title = None

        articles[full_url] = {
            "source": "Ñanduti",
            "title": title,
            "url": full_url,
            "section": "general",
        }

    return articles


def discover_articles():
    """
    Discover articles from Ñanduti.
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
                f"Ñanduti: {discovery_url} "
                f"-> {len(discovered)} articles"
            )

        except requests.RequestException as exc:

            print(
                f"Ñanduti: failed to fetch "
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
