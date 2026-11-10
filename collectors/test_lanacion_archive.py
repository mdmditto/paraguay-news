import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

BASE = "https://www.lanacion.com.py"

PATHS = [
    "/robots.txt",
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-news.xml",
    "/buscar/",
    "/search/",
    "/politica/",
    "/pais/",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0"
})


def inspect(path):
    url = urljoin(BASE, path)

    print("\n" + "=" * 70)
    print("URL:", url)

    try:
        response = session.get(
            url,
            timeout=30,
        )

        print("Status:", response.status_code)
        print("Final URL:", response.url)
        print("Content type:", response.headers.get("Content-Type"))

        if "robots.txt" in path:
            for line in response.text.splitlines():
                if "sitemap" in line.lower():
                    print(line)
            return

        if "xml" in response.headers.get(
            "Content-Type", ""
        ).lower():
            soup = BeautifulSoup(
                response.content,
                "xml",
            )

            locs = [
                tag.get_text(strip=True)
                for tag in soup.find_all("loc")
            ]

            print("Sitemap entries:", len(locs))

            for loc in locs[:15]:
                print(loc)

            return

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        links = set()

        for tag in soup.find_all("a", href=True):
            href = urljoin(
                response.url,
                tag["href"],
            )

            if urlparse(href).netloc.endswith(
                "lanacion.com.py"
            ):
                links.add(href)

        print("Internal links:", len(links))

        for link in sorted(links)[:20]:
            print(link)

    except Exception as exc:
        print("ERROR:", exc)


if __name__ == "__main__":
    for path in PATHS:
        inspect(path)
