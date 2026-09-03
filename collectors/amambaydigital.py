import re
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://amambaydigital.com/"

ALLOWED_HOSTS = {
    "amambaydigital.com",
    "www.amambaydigital.com",
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
    "leer más",
    "leer mas",
    "ver más",
    "ver mas",
    "más",
    "mas",
    "read more",
    "previous",
    "next",
}


def clean_url(url: str) -> str:
    """
    Remove query parameters and fragments.

    Amambay Digital article URLs end in .html,
    so we do not add a trailing slash.
    """

    parsed = urlparse(url)

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path,
            "",
            "",
            "",
        )
    )


def is_article_url(url: str) -> bool:
    """
    Current Amambay Digital articles follow:

        /descriptive-article-slug.html

    Example:

        /aporte-de-la-universidad-interamericana-permite-
        habilitar-moderna-sala-de-electroencefalograma-
        en-el-juan-pablo-ii.html

    Category pages such as:

        /locales
        /nacionales
        /deportes

    are automatically rejected because they do not
    end in .html.
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

    # Current articles are at the domain root.
    if len(parts) != 1:
        return False

    filename = parts[0].lower().strip()

    if not filename.endswith(".html"):
        return False

    slug = filename[:-5]

    if not slug:
        return False

    # Reject numeric-only pages.
    if re.fullmatch(r"\d+", slug):
        return False

    # News URLs are descriptive headline slugs.
    if "-" not in slug:
        return False

    if len(slug) < 8:
        return False

    return True


def discover_articles():
    """
    Discover recent Amambay Digital articles
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

        # Some article cards may expose generic
        # anchor labels instead of the headline.
        if (
            not title
            or title.lower().strip() in GENERIC_TITLES
        ):
            title = None

        # The homepage repeats articles under
        # Destacadas, Último Momento, Nacionales,
        # Más Leídas, etc.
        #
        # Deduplicate by URL and retain the most
        # informative anchor text.
        if url not in discovered:

            discovered[url] = {
                "source": "Amambay Digital",
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
