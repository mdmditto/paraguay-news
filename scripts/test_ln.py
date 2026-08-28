import requests
from bs4 import BeautifulSoup

url = "https://www.lanacion.com.py/category/politica/"

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

print(response.status_code)
print(len(response.text))

soup = BeautifulSoup(response.text, "html.parser")

for link in soup.find_all("a", href=True):
    href = link["href"]

    if "/politica/" in href:
        print(href)