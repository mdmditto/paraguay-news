import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://digitalmisiones.com.py/"

ALLOWED_HOSTS = {
    "digitalmisiones.com.py",
    "www.digitalmisiones.com.py",
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
    "leer",
    "leer más",
    "leer mas",
    "leer más…",
    "leer mas…",
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
    Remove query parameters and fragments and normalize
    Digital Misiones URLs with a trailing slash.

    Article URLs look like:

        /index.php/YYYY/MM/DD/<slug>/
    """

    parsed = urlparse(url)

    path = parsed.path.rstrip("/")

    if path:
        path += "/"

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            path,
            "",
            "",
            "",
        )
    )


def is_article_url(url: str) -> bool:
    """
    Digital Misiones articles currently follow:

        /index.php/YYYY/MM/DD/<slug>/

    Example:

        /index.php/2026/09/01/
        asamblea-de-medicos-este-jueves-para-decidir-otra-huelga/

    Rejects category/archive URLs such as:

        /index.php/category/nacionales/
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
    # index.php / YYYY / MM / DD / slug
    #
    if len(parts) != 5:
        return False

    prefix, year, month, day, slug = parts

    if prefix.lower() != "index.php":
        return False

    # Validate year/month/day.
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

    if re.fullmatch(r"\d+", slug):
        return False

    if "-" not in slug:
        return False

    if len(slug) < 8:
        return False

    # Reject accidental file URLs.
    if re.search(
        r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf|xml|json|mp3|mp4|zip)$",
        slug,
        flags=re.I,
    ):
        return False

    return True


def discover_articles():
    """
    Discover recent Digital Misiones articles
    directly from the homepage.

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

        url = clean_url(
            urljoin(BASE_URL, href)
        )

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

        # Articles are repeated across several
        # homepage components:
        #
        # - Últimas noticias
        # - Misiones
        # - Nacionales
        # - Deporte
        # - Noticias recientes
        #
        # Deduplicate using normalized URL and
        # retain the most informative anchor text.
        if url not in discovered:

            discovered[url] = {
                "source": "Digital Misiones",
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

    print(f"Found {len(articles)} articles\n")

    for article in articles:

        print(
            f"[{article['section']}] "
            f"{article['title']}"
        )

        print(article["url"])
        print()
