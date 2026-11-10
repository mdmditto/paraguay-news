import requests
from bs4 import BeautifulSoup
from collections import Counter
from datetime import date
from urllib.parse import urlparse

from collectors.abc import is_article_url

URL = "https://www.abc.com.py/buscador/"

response = requests.get(
    URL,
    params={"query": "Economía"},
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30,
)

print("Status:", response.status_code)
print("Final URL:", response.url)

soup = BeautifulSoup(response.text, "html.parser")

articles = set()

for link in soup.find_all("a", href=True):
    href = requests.compat.urljoin(response.url, link["href"])

    if is_article_url(href):
        articles.add(href)

print("Articles found:", len(articles))

counts = Counter()

for url in articles:
    parts = urlparse(url).path.strip("/").split("/")

    try:
        publication_date = date(
            int(parts[1]),
            int(parts[2]),
            int(parts[3]),
        )
        counts[publication_date] += 1
    except (ValueError, IndexError):
        pass

for day, count in sorted(counts.items()):
    print(day, count)

print("\nSample URLs:")
for url in sorted(articles)[:10]:
    print(url)
