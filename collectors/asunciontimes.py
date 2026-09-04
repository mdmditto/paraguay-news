import re
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://asunciontimes.com/"

ALLOWED_HOSTS = {
    "asunciontimes.com",
    "www.asunciontimes.com",
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


# Exact non-article pages that could otherwise look
# somewhat similar to article URLs.
EXCLUDED_PATHS = {
    "",
    "news",
    "sport",
    "sports",
    "culture",
    "lifestyle",
    "people",
    "travel",
    "map",
    "contact",
    "contact-us",
    "about",
    "about-us",
    "privacy-policy",
    "terms",
    "terms-and-conditions",
    "members-area",
    "my-profile",
    "community",
    "whats-on-guide",
    "homes-property",
}


# WordPress/archive structures that are not articles.
EXCLUDED_PREFIXES = {
    "category",
    "tag",
    "author",
    "page",
    "feed",
    "wp-admin",
    "wp-content",
    "wp-includes",
    "wp-json",
    "search",
}


GENERIC_TITLES = {
    "leer",
    "leer más",
    "leer mas",
    "ver más",
    "ver mas",
    "más",
    "mas",
    "read more",
    "continue reading",
    "previous",
    "next",
    "older posts",
    "newer posts",
}


def clean_url(url: str) -> str:
    """
    Remove query parameters and fragments and
    normalize URLs with a trailing slash.

    Example:

        https://asunciontimes.com/paraguay-news/business-news/article/
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
    Asunción Times articles use hierarchical paths.

    Examples:

        /paraguay-news/business-news/<slug>/

        /paraguay-news/national-news/<slug>/

        /people/national-heroes/<slug>/

        /lifestyle/exploring-paraguay/<slug>/

    Category/archive pages such as:

        /category/news/national-news/
        /tag/headlines/
        /sport/

    must be rejected.
    """

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.netloc.lower() not in ALLOWED_HOSTS:
        return False

    parts = [
        part.strip()
        for part in parsed.path.split("/")
        if part.strip()
    ]

    if not parts:
        return False

    # Reject exact static/root pages.
    normalized_path = "/".join(
        part.lower()
        for part in parts
    )

    if normalized_path in EXCLUDED_PATHS:
        return False

    # Reject WordPress archive structures.
    if parts[0].lower() in EXCLUDED_PREFIXES:
        return False

    # Articles currently contain a hierarchy plus
    # the final descriptive article slug.
    #
    # For example:
    #
    # paraguay-news / business-news / article-slug
    #
    if len(parts) < 3:
        return False

    slug = parts[-1].lower()

    if not slug:
        return False

    # Reject files/assets.
    if re.search(
        r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf|xml|json|mp3|mp4|zip)$",
        slug,
        flags=re.I,
    ):
        return False

    # Reject pagination IDs / numeric paths.
    if re.fullmatch(r"\d+", slug):
        return False

    # Reject date-like paths.
    if re.fullmatch(
        r"\d{4}(?:-\d{1,2})?(?:-\d{1,2})?",
        slug,
    ):
        return False

    # Current article titles result in descriptive slugs.
    if "-" not in slug:
        return False

    if len(slug) < 10:
        return False

    return True


def get_section_from_url(url: str) -> str:
    """
    Extract the most specific editorial section.

    Examples:

        /paraguay-news/business-news/article/
            -> business-news

        /paraguay-news/national-news/article/
            -> national-news

        /people/national-heroes/article/
            -> national-heroes

        /lifestyle/exploring-paraguay/article/
            -> exploring-paraguay
    """

    parsed = urlparse(url)

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    # The component immediately before the slug
    # is normally the most specific section.
    if len(parts) >= 3:
        return parts[-2].lower()

    return "general"


def discover_articles():
    """
    Discover recent Asunción Times articles
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

        # Stories are repeated heavily on the homepage:
        #
        # - National Headlines
        # - Top Story
        # - Local Headlines
        # - Local News
        # - National News
        # - Economy
        # - Business
        # - Sport
        # - Culture
        # - People
        #
        # Merge by normalized URL and retain the
        # most informative title.
        if url not in discovered:

            discovered[url] = {
                "source": "The Asunción Times",
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

    print(f"Found {len(articles)} articles\n")

    for article in articles:

        print(
            f"[{article['section']}] "
            f"{article['title']}"
        )

        print(article["url"])
        print()
