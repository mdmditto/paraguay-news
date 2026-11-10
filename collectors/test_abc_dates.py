from collections import Counter
from datetime import date
from urllib.parse import urlparse

from collectors.historical_discovery import discover_historical_urls

urls = discover_historical_urls(
    "abc",
    date(2026, 11, 1),
    date(2026, 11, 9),
)

counts = Counter()

for url in urls:
    parts = urlparse(url).path.strip("/").split("/")

    article_date = date(
        int(parts[1]),
        int(parts[2]),
        int(parts[3]),
    )

    counts[article_date] += 1

for day, count in sorted(counts.items()):
    print(day, count)