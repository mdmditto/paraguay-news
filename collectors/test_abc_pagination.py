from collections import Counter
from datetime import date
from urllib.parse import urlparse

from collectors.abc import discover_from_page

BASE = "https://www.abc.com.py"

TEST_URLS = [
    f"{BASE}/ultimas-noticias/",
    f"{BASE}/ultimas-noticias/?page=2",
    f"{BASE}/ultimas-noticias/?page=5",
    f"{BASE}/ultimas-noticias/?page=10",
    f"{BASE}/politica/",
    f"{BASE}/nacionales/",
]


def get_date(url):
    parts = urlparse(url).path.strip("/").split("/")

    try:
        return date(
            int(parts[1]),
            int(parts[2]),
            int(parts[3]),
        )
    except (ValueError, IndexError):
        return None


for page_url in TEST_URLS:
    print(f"\nPAGE: {page_url}")

    try:
        articles = discover_from_page(page_url)

        counts = Counter(
            get_date(url)
            for url in articles
            if get_date(url) is not None
        )

        print(f"Articles discovered: {len(articles)}")

        for day, count in sorted(counts.items()):
            print(f"  {day}: {count}")

    except Exception as exc:
        print(f"ERROR: {exc}")