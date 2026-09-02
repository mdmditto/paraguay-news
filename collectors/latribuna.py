import re
import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


BASE_URL = "https://www.latribuna.com.py"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


def clean_url(url: str) -> str:
    """
    Remove query parameters and fragments.
    """

    parsed = urlparse(url)

    return (
        f"{parsed.scheme}://"
        f"{parsed.netloc}"
        f"{parsed.path}"
    )


def is_article_url(url: str) -> bool:
    """
    Decide whether a URL looks like a La Tribuna article.

    Current article URLs follow:

        /section/YYYY/MM/DD/article-slug/

    Example:

        /editorial/2026/08/29/
        la-marca-pais-o-el-giro-sobre-lo-mismo/
    """

    parsed = urlparse(url)

    if parsed.netloc not in {
        "latribuna.com.py",
        "www.latribuna.com.py",
    }:
        return False

    path = parsed.path

    if not path:
        return False

    parts = [
        part
        for part in path.split("/")
        if part
    ]

    # Expected structure:
    #
    # section / year / month / day / slug
    if len(parts) != 5:
        return False

    section, year, month, day, slug = parts

    # Section must contain something.
    if not section:
        return False

    # Validate date structure.
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
        month_number = int(month)
        day_number = int(day)

    except ValueError:
        return False

    if not 1 <= month_number <= 12:
        return False

    if not 1 <= day_number <= 31:
        return False

    # Need a real article slug.
    if not slug:
        return False

    # Avoid file URLs.
    if slug.lower().endswith(
        (
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
            ".svg",
            ".pdf",
            ".xml",
            ".css",
            ".js",
        )
    ):
        return False

    return True


def discover_articles():
    """
    Discover current La Tribuna articles from the homepage.

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

        title = link.get_text(
            " ",
            strip=True,
        )

        # Extract section directly from URL.
        parsed = urlparse(
            full_url
        )

        parts = [
            part
            for part in parsed.path.split("/")
            if part
        ]

        section = (
            parts[0]
            if parts
            else "general"
        )

        # Homepage often links the same article
        # through image, title and other components.
        if full_url not in articles:

            articles[full_url] = {
                "source": "La Tribuna",
                "title": title or None,
                "url": full_url,
                "section": section,
            }

        # Prefer a non-empty title when the first
        # occurrence was an image link.
        elif (
            not articles[full_url]["title"]
            and title
        ):

            articles[full_url]["title"] = title

    return list(
        articles.values()
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
