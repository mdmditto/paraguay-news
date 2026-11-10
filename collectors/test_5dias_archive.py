
import json
import requests
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

BASE = "https://5dias.com.py"

PATHS = [
    "/robots.txt",
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-0.xml",
    "/api",
    "/ueno",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
})


def inspect(url):
    print("\n" + "=" * 65)
    print("URL:", url)

    try:
        response = session.get(url, timeout=30)
        print("STATUS:", response.status_code)
        print("FINAL URL:", response.url)
        print("CONTENT TYPE:", response.headers.get("Content-Type"))

        if response.status_code != 200:
            return

        if url.endswith("robots.txt"):
            print(response.text[:4000])
            return

        content = response.content.lstrip()

        if content.startswith(b"<?xml") or (
            "xml" in response.headers.get("Content-Type", "").lower()
        ):
            root = ET.fromstring(response.content)

            locs = [
                element.text.strip()
                for element in root.iter()
                if element.tag.endswith("loc") and element.text
            ]

            print("XML ROOT:", root.tag)
            print("XML ENTRIES:", len(locs))

            for loc in locs[:25]:
                print(loc)

            print(
                "ARTICLE URLS:",
                sum("/article/" in loc for loc in locs)
            )
            return

        soup = BeautifulSoup(response.text, "html.parser")

        print(
            "TITLE:",
            soup.title.get_text(strip=True) if soup.title else None
        )

        links = set()

        for a in soup.find_all("a", href=True):
            href = urljoin(response.url, a["href"])

            if urlparse(href).hostname in (
                "5dias.com.py",
                "www.5dias.com.py",
            ):
                links.add(href)

        print("INTERNAL LINKS:", len(links))

        article_links = sorted(
            link for link in links
            if "/article/" in link
        )

        print("ARTICLE LINKS:", len(article_links))

        for link in article_links[:20]:
            print(link)

        print("\nPAGINATION LINKS:")

        for link in sorted(links):
            if any(x in link.lower() for x in (
                "page=", "/page/", "offset=", "cursor="
            )):
                print(link)

        print("\nSCRIPTS:")

        for script in soup.find_all("script", src=True)[:20]:
            print(urljoin(response.url, script["src"]))

    except Exception as exc:
        print("ERROR:", repr(exc))


def inspect_article():
    url = (
        BASE
        + "/article/atraso-cambiario-y-produccin"
    )

    print("\n" + "=" * 65)
    print("ARTICLE METADATA:", url)

    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for meta in soup.find_all("meta"):
            key = (
                meta.get("property")
                or meta.get("name")
                or ""
            )

            if any(x in key.lower() for x in (
                "publish", "date", "modified", "time"
            )):
                print(key, "=", meta.get("content"))

        for script in soup.find_all(
            "script", type="application/ld+json"
        ):
            try:
                data = json.loads(
                    script.string or script.get_text()
                )
                print(
                    "JSON-LD:",
                    json.dumps(data, ensure_ascii=False)[:2000]
                )
            except (ValueError, TypeError):
                pass

        print("\nDATE ELEMENTS:")

        for element in soup.select(
            "time, [datetime], .date, .article-date"
        )[:15]:
            print(str(element)[:400])

    except Exception as exc:
        print("ERROR:", repr(exc))


if __name__ == "__main__":
    for path in PATHS:
        inspect(urljoin(BASE, path))

    inspect_article()
