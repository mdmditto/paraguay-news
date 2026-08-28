import requests
import trafilatura


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
}


def extract_article(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()

    result = trafilatura.extract(
        response.text,
        output_format="json",
        with_metadata=True,
        include_comments=False,
        include_tables=False
    )

    if result is None:
        return None

    import json

    return json.loads(result)