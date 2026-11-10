
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import Counter
from datetime import date
import xml.etree.ElementTree as ET

BASE = "https://rdn.com.py"

PATHS = [
    "/",
    "/robots.txt",
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/wp-sitemap.xml",
    "/feed/",
    "/buscar/",
    "/search/",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0"
})


def extract_date(url):
    parts = urlparse(url).path.strip("/").split("/")

    for i in range(len(parts) - 2):
        try:
            year = int(parts[i])
            month = int(parts[i + 1])
            day = int(parts[i + 2])

            if 2000 <= year <= 2100:
                return date(year, month, day)
        except (ValueError, IndexError):
            continue

    return None


def inspect(url):
    print("\n" + "=" * 70)
    print("URL:", url)

    try:
        response = session.get(url, timeout=25)

        print("STATUS:", response.status_code)
        print("FINAL URL:", response.url)
        print("CONTENT TYPE:", response.headers.get("Content-Type"))

        if response.status_code != 200:
            return

        if "robots.txt" in url:
            print("\nROBOTS CONTENT:")
            print(response.text[:4000])
            return

        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        if "xml" in content_type or response.content.lstrip().startswith(b"<?xml"):
            root = ET.fromstring(response.content)

            locs = [
                el.text.strip()
                for el in root.iter()
                if el.tag.endswith("loc") and el.text
            ]

            print("XML ENTRIES:", len(locs))

            for loc in locs[:20]:
                print(loc)

            counts = Counter(
                extract_date(loc)
                for loc in locs
                if extract_date(loc)
            )

            print("\nNOVEMBER 4-9:")

            for day, count in sorted(counts.items()):
                if date(2026, 11, 4) <= day <= date(2026, 11, 9):
                    print(day, count)

            return

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        print("PAGE TITLE:",
              soup.title.get_text(strip=True) if soup.title else None)

        links = set()

        for a in soup.find_all("a", href=True):
            href = urljoin(response.url, a["href"])

            if urlparse(href).hostname and (
                urlparse(href).hostname.endswith("rdn.com.py")
            ):
                links.add(href)

        print("INTERNAL LINKS:", len(links))

        for link in sorted(links)[:25]:
            print(link)

        print("\nFORMS:")

        for form in soup.find_all("form"):
            print(str(form)[:800])

    except Exception as exc:
        print("ERROR:", repr(exc))


if __name__ == "__main__":
    for path in PATHS:
        inspect(urljoin(BASE, path))
