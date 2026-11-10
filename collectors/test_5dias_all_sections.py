
import json
import time
from collections import Counter
from pathlib import Path
from urllib.parse import quote

import requests

from collectors.test_5dias_extract_payload import extract_articles

BASE = "https://5dias.com.py"

SECTIONS = [
    "/",
    "/noticiasdeldia",
    "/especiales",
    "/5dteconecta",
    "/banca-y-finanzas",
    "/category/Negocios",
    "/category/Economía y Finanzas",
    "/subcategory/Internacional",
    "/5data",
    "/qeq",
    "/ueno",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0"
})

all_articles = {}

for index, section in enumerate(SECTIONS, start=1):
    url = BASE + quote(section, safe="/")

    print(f"\n[{index}/{len(SECTIONS)}] {url}")

    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()

        filename = Path(
            f"5dias_section_{index}.html"
        )

        filename.write_text(
            response.text,
            encoding="utf-8"
        )

        articles = extract_articles(filename)

        new_count = 0

        for article in articles:
            if article["url"] not in all_articles:
                all_articles[article["url"]] = article
                new_count += 1

        print(
            f"Found: {len(articles)} | "
            f"New: {new_count} | "
            f"Total: {len(all_articles)}"
        )

    except Exception as exc:
        print("ERROR:", repr(exc))

    time.sleep(1)

articles = list(all_articles.values())

counts = Counter(
    article["publish_date"][:10]
    for article in articles
)

print("\n" + "=" * 60)
print("ARTICLES BY DATE")

for date, count in sorted(counts.items()):
    print(date, count)

target = [
    article
    for article in articles
    if "2026-11-04"
    <= article["publish_date"][:10]
    <= "2026-11-06"
]

print("\nTARGET ARTICLES:", len(target))

for article in target:
    print(article["publish_date"], article["url"])

Path("5dias_all_articles.json").write_text(
    json.dumps(
        articles,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

Path("5dias_target_articles.json").write_text(
    json.dumps(
        target,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

print("\nTOTAL UNIQUE ARTICLES:", len(articles))
