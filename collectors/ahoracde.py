import re
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://ahoracde.com/"

ALLOWED_HOSTS = {
    "ahoracde.com",
    "www.ahoracde.com",
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


EXCLUDED_PATHS = {
    "",
    "inicio",
    "contacto",
    "nosotros",
    "quienes-somos",
    "buscar",
    "search",
    "radio",
    "tv",
    "politica-de-privacidad",
    "terminos-y-condiciones",
    "terminos-de-uso",
}


EXCLUDED_PREFIXES = {
    "category",
    "author",
    "tag",
    "page",
    "feed",
    "wp-admin",
    "wp-content",
    "wp-includes",
    "wp-json",
}


def clean_url(url: str) -> str:
    """
    Remove query parameters and fragments and
    normalize the trailing slash.
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
    AhoraCDE articles currently use root-level slugs.

    Example:

        /el-fin-de-los-clubes-calendario-la-apf-prepara-un-cambios-para-2027/

    Category/archive pages use structures such as:

        /category/policiales/
        /author/admin/
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

    # Articles currently have exactly one
    # path component.
    if len(parts) != 1:
        return False

    slug = parts[0].lower().strip()

    if not slug:
        return False

    if slug in EXCLUDED_PATHS:
        return False

    if slug in EXCLUDED_PREFIXES:
        return False

    # Exclude obvious files.
    if re.search(
        r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf|xml|json|mp3|mp4)$",
        slug,
        flags=re.I,
    ):
        return False

    # Exclude numeric-only URLs.
    if re.fullmatch(r"\d+", slug):
        return False

    # Real article URLs are descriptive slugs.
    if "-" not in slug:
        return False

    if len(slug) < 10:
        return False

    return True


def discover_articles():
    """
    Discover recent AhoraCDE articles
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

    for link in soup.find_all(
        "a",
        href=True,
    ):

        href = link.get(
            "href",
            "",
        ).strip()

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

        # Generic labels are not useful titles.
        if title.lower() in {
            "leer más",
            "leer mas",
            "ver más",
            "ver mas",
            "más",
            "mas",
            "previous post",
            "next post",
        }:
            title = None

        # AhoraCDE repeats stories in several
        # homepage sections, so merge by URL.
        if url not in discovered:

            discovered[url] = {
                "source": "AhoraCDE",
                "title": (
                    title
                    if title
                    else None
                ),
                "url": url,
                "section": "general",
            }

        else:

            existing_title = (
                discovered[url]
                .get("title")
            )

            if (
                title
                and (
                    not existing_title
                    or len(title) > len(existing_title)
                )
            ):
                discovered[url][
                    "title"
                ] = title

    return list(
        discovered.values()
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
