import requests

from urllib.parse import urlparse


BASE_URL = "https://diariolajornada.com.py"

SUPABASE_URL = (
    "https://hagilpkemrdjdmfxvvwc.supabase.co"
)

SUPABASE_KEY = (
    "sb_publishable_7iR1LFppZLha2xuQAvkaVQ_9oHJsFYF"
)

ARTICLES_API = (
    f"{SUPABASE_URL}/rest/v1/articles"
)


HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": (
        f"Bearer {SUPABASE_KEY}"
    ),
    "Accept": "application/json",
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


def discover_articles():
    """
    Discover current Diario La Jornada articles
    through the public data API used by the site.

    Returns:
        list[dict]
    """

    params = {
        "select": (
            "id,"
            "title,"
            "slug,"
            "published_at,"
            "cover_image_url"
        ),
        "status": "eq.published",
        "order": "published_at.desc",
        "limit": "50",
    }

    response = requests.get(
        ARTICLES_API,
        headers=HEADERS,
        params=params,
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    articles = []

    for item in data:

        slug = item.get("slug")

        if not slug:
            continue

        title = item.get("title")

        url = (
            f"{BASE_URL}/noticia/{slug}"
        )

        articles.append(
            {
                "source": "Diario La Jornada",
                "title": title,
                "url": clean_url(url),
                "section": "general",
            }
        )

    return articles


if __name__ == "__main__":

    articles = discover_articles()

    print(
        f"Found {len(articles)} articles\n"
    )

    for article in articles:

        print(article["title"])
        print(article["url"])
        print()