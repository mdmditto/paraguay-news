
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import Counter

BASE = "https://5dias.com.py"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
})

URLS = [
    BASE,
    BASE + "/ueno",
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

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        links = []

        for a in soup.find_all("a", href=True):
            href = urljoin(response.url, a["href"])
            parsed = urlparse(href)

            if parsed.netloc not in (
                "5dias.com.py",
                "www.5dias.com.py",
            ):
                continue

            links.append(href)

        links = list(dict.fromkeys(links))

        print("\nINTERNAL PATHS:")

        paths = Counter(
            urlparse(link).path.split("/")[1]
            for link in links
            if urlparse(link).path.strip("/")
        )

        for path, count in paths.most_common():
            print(path, count)

        print("\nNON-ARTICLE LINKS:")

        for link in links:
            if "/article/" not in link:
                print(link)

        print("\nPAGINATION CANDIDATES:")

        for link in links:
            if any(x in link.lower() for x in (
                "page=", "offset=", "cursor=",
                "/page/", "/categoria/",
                "/seccion/", "/tag/"
            )):
                print(link)

    except Exception as exc:
        print("ERROR:", repr(exc))


if __name__ == "__main__":
    for url in URLS:
        inspect(url)
