import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

url = "https://www.ultimahora.com/politica"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
}

response = requests.get(
    url,
    headers=headers,
    timeout=20
)

response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")

articles = {}

for link in soup.select("div.PagePromo-title a.Link"):
    href = link.get("href")
    title = link.get_text(" ", strip=True)

    if not href or not title:
        continue

    full_url = urljoin(
        "https://www.ultimahora.com",
        href
    )

    articles[full_url] = title


print(f"Found {len(articles)} articles:\n")

for article_url, title in articles.items():
    print(title)
    print(article_url)
    print()