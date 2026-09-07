import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


BASE_URL = "https://www.npy.com.py"

DISCOVERY_URLS = [
    f"{BASE_URL}/noticias/nacionales/politica",
    f"{BASE_URL}/noticias/nacionales/sucesos",
    f"{BASE_URL}/noticias/nacionales",
    f"{BASE_URL}/noticias/internacionales",
    f"{BASE_URL}/noticias/deportes",
]


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    )
}


def clean_url(url):
    """
    Remove query parameters and fragments from a URL.
    """
    parsed = urlparse(url)

    return parsed._replace(
        query="",
        fragment="",
    ).geturl().rstrip("/")


def is_article_url(url):
    """
    Determine whether a URL looks like an article URL.

    NPY article URLs are expected to be under /noticias/
    and deeper than the section landing pages.
    """

    parsed = urlparse(url)

    # Only NPY
    if parsed.netloc not in {
        "www.npy.com.py",
        "npy.com.py",
    }:
        return False

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    # Must start with /noticias/
    if not parts or parts[0].lower() != "noticias":
        return False

    # Section pages are usually only 2-3 levels deep.
    # Articles should be deeper.
    if len(parts) < 4:
        return False

    slug = parts[-1].lower()

    # Avoid obvious non-article URLs
    if not slug:
        return False

    if "." in slug:
        return False

    if slug.isdigit():
        return False

    # Article slugs normally contain words separated by hyphens
    if "-" not in slug:
        return False

    if len(slug) < 10:
        return False

    return True


def get_section_from_url(url):
    """
    Determine the section from the article URL.
    """

    parsed = urlparse(url)

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    if len(parts) < 2:
        return "general"

    # /noticias/nacionales/politica/...
    # /noticias/nacionales/sucesos/...
    # /noticias/internacionales/...
    # /noticias/deportes/...
    return parts[1].lower()


def discover_from_page(page_url):
    """
    Discover articles from one NPY section page.
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

        # Keep only actual article URLs
        if not is_article_url(full_url):
            continue

        # Ignore the section page itself
        if full_url.rstrip("/") == page_url.rstrip("/"):
            continue

        title = link.get_text(
            " ",
            strip=True,
        )

        if title:
            title = title.strip()

        # Ignore very short link text
        if not title or len(title) < 10:
            title = None

        section = get_section_from_url(
            full_url
        )

        articles[full_url] = {
            "source": "NPY",
            "title": title,
            "url": full_url,
            "section": section,
        }

    return articles


def discover_articles():
    """
    Discover articles from all configured NPY sections.
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
                f"NPY: {discovery_url} "
                f"-> {len(discovered)} articles"
            )

        except requests.RequestException as exc:

            print(
                f"NPY: failed to fetch "
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