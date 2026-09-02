import re
import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


BASE_URL = "https://www.rdn.com.py"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
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
    Decide whether a URL looks like an RDN article.

    Current RDN article URLs follow:

        /YYYY/MM/DD/article-slug/

    Example:

        /2026/09/01/
        vecinos-denuncian-riesgo-de-desborde-cloacal-en-asuncion/
    """

    parsed = urlparse(url)

    if parsed.netloc not in {
        "rdn.com.py",
        "www.rdn.com.py",
    }:
        return False

    path = parsed.path

    if not path:
        return False

    # Split URL into path components.
    parts = [
        part
        for part in path.split("/")
        if part
    ]

    # Expected:
    #
    # year / month / day / slug
    #
    if len(parts) != 4:
        return False

    year, month, day, slug = parts

    # Year
    if not re.fullmatch(
        r"\d{4}",
        year,
    ):
        return False

    # Month
    if not re.fullmatch(
        r"\d{1,2}",
        month,
    ):
        return False

    # Day
    if not re.fullmatch(
        r"\d{1,2}",
        day,
    ):
        return False

    # Basic numeric validation.
    try:
        month_number = int(month)
        day_number = int(day)
    except ValueError:
        return False

    if not 1 <= month_number <= 12:
        return False

    if not 1 <= day_number <= 31:
        return False

    # Article needs an actual slug.
    if not slug:
        return False

    # Ignore files/assets.
    if slug.endswith(
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
    Discover current RDN articles from the homepage.

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

        # Avoid duplicate article links.
        # Homepage cards often link the image,
        # title and other elements separately.
        if full_url not in articles:

            articles[full_url] = {
                "source": "RDN",
                "title": title or None,
                "url": full_url,
                "section": "general",
            }

        # Prefer a useful title if the first link
        # found was an image or empty link.
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

        print(article["title"])
        print(article["url"])
        print()
