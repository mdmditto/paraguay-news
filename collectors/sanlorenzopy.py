import re
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.sanlorenzopy.com/"

ALLOWED_HOSTS = {
    "sanlorenzopy.com",
    "www.sanlorenzopy.com",
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
    Remove query parameters and fragments and
    normalize article URLs with a trailing slash.
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
    San Lorenzo PY articles currently follow:

        /<numeric-id>/<descriptive-slug>/

    Examples:

        /84439/los-vecinos-de-lerida-y-reducto-pagan-impuestos-
        para-ser-protegidos-no-contaminados/

        /84432/talentos-de-nuestra-ciudad-los-que-vinieron-
        la-banda-de-rock-sanlorenzana-que-busca-conquistar-
        el-reciclarte/

    Category/archive URLs such as:

        /categoria/deportes/
        /page/2/

    are rejected automatically.
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
    # numeric-id / slug
    #
    if len(parts) != 2:
        return False

    article_id, slug = parts

    # First component must be an article ID.
    if not re.fullmatch(r"\d+", article_id):
        return False

    if not slug:
        return False

    # Reject numeric-only second components.
    if re.fullmatch(r"\d+", slug):
        return False

    # Real article URLs use descriptive slugs.
    if "-" not in slug:
        return False

    if len(slug) < 8:
        return False

    # Reject obvious files/assets.
    if re.search(
        r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf|xml|json|mp3|mp4|zip)$",
        slug,
        flags=re.I,
    ):
        return False

    return True


def discover_articles():
    """
    Discover recent San Lorenzo PY articles
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

        # The homepage repeats stories in several
        # blocks and often provides both:
        #
        # headline link
        # "Leer más" link
        #
        # Merge by normalized URL and retain the
        # most informative title.
        if url not in discovered:

            discovered[url] = {
                "source": "San Lorenzo PY",
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
