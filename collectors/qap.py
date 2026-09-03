import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://qapchaconews.com/"

ALLOWED_HOSTS = {
    "qapchaconews.com",
    "www.qapchaconews.com",
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
    "anterior",
    "siguiente",
}


def clean_url(url: str) -> str:
    """
    Remove query parameters and fragments.

    QAP Chaco News article URLs end in .html,
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
    QAP Chaco News articles currently follow:

        /noticia/<section>/YYYY/MM/DD/<slug>/<id>.html

    Example:

        /noticia/policiales/2026/08/08/
        turista-suizo-denuncia-robo-en-asuncion/
        42796.html
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

    # Expected:
    #
    # noticia
    # section
    # YYYY
    # MM
    # DD
    # slug
    # ID.html
    #
    if len(parts) != 7:
        return False

    prefix, section, year, month, day, slug, article_file = parts

    if prefix.lower() != "noticia":
        return False

    if not section:
        return False

    # Validate date components.
    if not re.fullmatch(r"\d{4}", year):
        return False

    if not re.fullmatch(r"\d{1,2}", month):
        return False

    if not re.fullmatch(r"\d{1,2}", day):
        return False

    try:
        datetime(
            int(year),
            int(month),
            int(day),
        )
    except ValueError:
        return False

    # Article slug should be descriptive.
    if not slug:
        return False

    if "-" not in slug:
        return False

    if len(slug) < 6:
        return False

    # Final component must be numeric ID + .html
    #
    # Example:
    # 42846.html
    #
    if not re.fullmatch(
        r"\d+\.html",
        article_file,
        flags=re.I,
    ):
        return False

    return True


def get_section_from_url(url: str) -> str:
    """
    Extract section from:

        /noticia/agropecuaria-y-forestal/2026/08/24/.../42846.html

    Returns:

        agropecuaria-y-forestal
    """

    parsed = urlparse(url)

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    if (
        len(parts) >= 2
        and parts[0].lower() == "noticia"
    ):
        return parts[1].lower()

    return "general"


def discover_articles():
    """
    Discover recent QAP Chaco News articles
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

        # Articles can appear multiple times:
        #
        # - main headlines
        # - section blocks
        # - Más leído
        # - related stories
        #
        # Merge by URL and retain the most useful title.
        if url not in discovered:

            discovered[url] = {
                "source": "QAP Chaco News",
                "title": title,
                "url": url,
                "section": get_section_from_url(url),
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
