import json

import requests
import trafilatura

from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
}


# =========================================================
# JSON-LD HELPERS
# =========================================================

def find_date_published_in_jsonld(data):
    """
    Recursively search JSON-LD data for datePublished.

    Handles structures such as:

        {
            "@type": "NewsArticle",
            "datePublished": "..."
        }

    as well as:

        {
            "@graph": [
                {...},
                {...}
            ]
        }
    """

    if isinstance(data, dict):

        date_published = data.get(
            "datePublished"
        )

        if date_published:
            return date_published

        for value in data.values():

            result = (
                find_date_published_in_jsonld(
                    value
                )
            )

            if result:
                return result

    elif isinstance(data, list):

        for item in data:

            result = (
                find_date_published_in_jsonld(
                    item
                )
            )

            if result:
                return result

    return None


def extract_jsonld_date(
    soup,
):
    """
    Extract datePublished from JSON-LD metadata.
    """

    scripts = soup.find_all(
        "script",
        attrs={
            "type": "application/ld+json"
        },
    )

    for script in scripts:

        content = script.string

        if not content:
            continue

        try:

            data = json.loads(
                content
            )

        except (
            json.JSONDecodeError,
            TypeError,
        ):

            continue

        result = (
            find_date_published_in_jsonld(
                data
            )
        )

        if result:
            return str(
                result
            ).strip()

    return None


# =========================================================
# META TAG DATE
# =========================================================

def extract_meta_date(
    soup,
):
    """
    Extract publication timestamp from common
    article metadata tags.
    """

    candidates = [

        (
            "property",
            "article:published_time",
        ),

        (
            "name",
            "article:published_time",
        ),

        (
            "property",
            "og:published_time",
        ),

        (
            "name",
            "date",
        ),

        (
            "name",
            "pubdate",
        ),

        (
            "itemprop",
            "datePublished",
        ),
    ]

    for attribute, value in candidates:

        tag = soup.find(
            attrs={
                attribute: value
            }
        )

        if tag:

            content = (
                tag.get("content")
                or tag.get("datetime")
            )

            if content:

                return str(
                    content
                ).strip()

    return None


# =========================================================
# PUBLICATION DATE
# =========================================================

def extract_publication_date(
    html,
):
    """
    Extract the most precise publication timestamp
    available in the HTML.

    Priority:

        1. JSON-LD datePublished
        2. article/meta publication timestamp
        3. None

    Trafilatura is used separately as the final fallback.
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    # -----------------------------------------------------
    # 1. JSON-LD
    # -----------------------------------------------------

    date = extract_jsonld_date(
        soup
    )

    if date:
        return date

    # -----------------------------------------------------
    # 2. META
    # -----------------------------------------------------

    date = extract_meta_date(
        soup
    )

    if date:
        return date

    return None


# =========================================================
# ARTICLE EXTRACTION
# =========================================================

def extract_article(
    url,
    debug=False,
):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=20,
    )

    response.raise_for_status()

    html = response.text

    # =====================================================
    # TRAFILATURA
    # =====================================================

    result = trafilatura.extract(
        html,
        output_format="json",
        with_metadata=True,
        include_comments=False,
        include_tables=False,
    )

    if result is None:
        return None

    article = json.loads(
        result
    )

    # =====================================================
    # PRECISE PUBLICATION TIMESTAMP
    # =====================================================

    precise_date = (
        extract_publication_date(
            html
        )
    )

    trafilatura_date = (
        article.get(
            "date"
        )
    )

    # Prefer precise HTML metadata.
    #
    # Only fall back to Trafilatura if no more precise
    # timestamp could be found.
    if precise_date:

        article[
            "date"
        ] = precise_date

    # =====================================================
    # DEBUG
    # =====================================================

    if debug:

        print()
        print("=" * 78)
        print("ARTICLE METADATA")
        print("=" * 78)

        print(
            f"URL: {url}"
        )

        print(
            f"Trafilatura date: "
            f"{repr(trafilatura_date)}"
        )

        print(
            f"Precise HTML date: "
            f"{repr(precise_date)}"
        )

        print(
            f"Final date: "
            f"{repr(article.get('date'))}"
        )

        print(
            f"title: "
            f"{repr(article.get('title'))}"
        )

        print(
            f"author: "
            f"{repr(article.get('author'))}"
        )

        print(
            f"url: "
            f"{repr(article.get('url'))}"
        )

        print(
            f"hostname: "
            f"{repr(article.get('hostname'))}"
        )

        print(
            f"categories: "
            f"{repr(article.get('categories'))}"
        )

        print(
            f"tags: "
            f"{repr(article.get('tags'))}"
        )

    return article