import requests
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date
from urllib.parse import urlparse

URL = (
    "https://www.lanacion.com.py"
    "/arc/outboundfeeds/sitemap/?outputType=xml"
)

response = requests.get(
    URL,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30,
)

response.raise_for_status()

root = ET.fromstring(response.content)

print("Root tag:", root.tag)
print("Total sitemap entries:", len(root))

counts = Counter()
articles = []
nested_sitemaps = []

for element in root:
    loc = element.find("{*}loc")

    if loc is None or not loc.text:
        continue

    url = loc.text.strip()

    if element.tag.endswith("sitemap"):
        nested_sitemaps.append(url)
        continue

    parts = urlparse(url).path.strip("/").split("/")

    if len(parts) < 5:
        continue

    try:
        published = date(
            int(parts[1]),
            int(parts[2]),
            int(parts[3]),
        )
    except (ValueError, IndexError):
        continue

    counts[published] += 1

    if date(2026, 11, 4) <= published <= date(2026, 11, 9):
        articles.append(url)

print("\nNESTED SITEMAPS:", len(nested_sitemaps))

for url in nested_sitemaps[:20]:
    print(url)

print("\nARTICLES PER DATE")

for day, count in sorted(counts.items()):
    if date(2026, 11, 1) <= day <= date(2026, 11, 9):
        print(day, count)

print("\nTOTAL ARTICLES NOV 4-9:", len(articles))

print("\nSAMPLE URLS")

for url in articles[:10]:
    print(url)
