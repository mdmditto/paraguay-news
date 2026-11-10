from datetime import date
from collections import Counter

from collectors.abc_queryly import (
    discover_abc_historical,
    article_date_from_url,
)


articles = discover_abc_historical(
    start_date=date(2026, 11, 4),
    end_date=date(2026, 11, 6),
    max_pages_per_query=15,
)

counts = Counter(
    article_date_from_url(item["url"])
    for item in articles
)

print("\nARTICLES PER DATE")

for day, count in sorted(counts.items()):
    print(day, count)

print("\nSAMPLE ARTICLES")

for article in articles[:10]:
    print(article["url"])
