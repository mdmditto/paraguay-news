
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE = "https://diarioparaguayo.com"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0"
})

TEST_URLS = [
    BASE + "/buscar?q=Paraguay",
    BASE + "/buscar?q=Paraguay&page=2",
    BASE + "/buscar?q=Paraguay&page=10",
    BASE + "/categoria/politica",
    BASE + "/categoria/politica?page=2",
    BASE + "/categoria/politica?page=10",
]


def inspect(url):
    print("\n" + "=" * 70)
    print("URL:", url)

    try:
        response = session.get(url, timeout=30)
        print("STATUS:", response.status_code)
        print("FINAL URL:", response.url)

        if response.status_code != 200:
            return

        soup = BeautifulSoup(response.text, "html.parser")

        print(
            "TITLE:",
            soup.title.get_text(strip=True)
            if soup.title else None
        )

        article_links = []

        for a in soup.find_all("a", href=True):
            href = urljoin(response.url, a["href"])

            if "/noticia/" in href:
                article_links.append(href)

        article_links = list(dict.fromkeys(article_links))

        print("ARTICLE LINKS:", len(article_links))

        for link in article_links[:10]:
            print(" ", link)

        print("\nPAGINATION:")

        pagination = soup.select(
            ".pagination a, "
            "a[rel='next'], "
            "nav a"
        )

        for a in pagination[:25]:
            print(
                a.get_text(" ", strip=True),
                urljoin(response.url, a.get("href", ""))
            )

        print("\nDATE ELEMENTS:")

        for element in soup.select(
            "time, "
            "[datetime], "
            ".news-date, "
            ".article-date, "
            ".fecha"
        )[:15]:
            print(
                element.get_text(" ", strip=True)[:100],
                element.get("datetime")
            )

        print("\nPAGE TEXT SAMPLE:")
        print(
            soup.get_text(" ", strip=True)[:700]
        )

    except Exception as exc:
        print("ERROR:", repr(exc))


if __name__ == "__main__":
    for url in TEST_URLS:
        inspect(url)
