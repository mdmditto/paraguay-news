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

for link in soup.find_all("a", href=True):
    text = link.get_text(" ", strip=True)

    if len(text) > 35:
        full_url = urljoin(
            "https://www.ultimahora.com",
            link["href"]
        )

        print("=" * 100)
        print("TEXT:", text)
        print("URL :", full_url)

        # Show parent HTML so we can identify article-card structure
        print("PARENT:")
        print(link.parent.prettify()[:1200])