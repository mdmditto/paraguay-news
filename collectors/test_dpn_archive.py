
import requests
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import Counter

BASE = "https://www.dpn.com.py"

PATHS = [
    "/",
    "/robots.txt",
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/wp-sitemap.xml",
    "/sitemap-news.xml",
    "/noticias",
    "/politica",
    "/economia",
    "/tag/seguridad",
    "/buscar",
    "/search",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xml;q=0.9,*/*;q=0.8",
})


def inspect(path):
    url = urljoin(BASE, path)

    print("\n" + "=" * 70)
    print("URL:", url)

    try:
        response = session.get(url, timeout=30)

        print("STATUS:", response.status_code)
        print("FINAL URL:", response.url)
        print(
            "CONTENT TYPE:",
            response.headers.get("Content-Type")
        )

        if response.status_code != 200:
            return

        if path == "/robots.txt":
            print("\nROBOTS CONTENT:")
            print(response.text[:4000])
            return

        content = response.content.lstrip()

        if content.startswith(b"<?xml") or (
            "xml" in response.headers.get(
                "Content-Type", ""
            ).lower()
        ):
            try:
                root = ET.fromstring(response.content)

                locs = [
                    element.text.strip()
                    for element in root.iter()
                    if element.tag.endswith("loc")
                    and element.text
                ]

                print("XML ROOT:", root.tag)
                print("XML ENTRIES:", len(locs))

                for loc in locs[:25]:
                    print(loc)

            except ET.ParseError as exc:
                print("XML ERROR:", exc)

            return

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        print(
            "TITLE:",
            soup.title.get_text(strip=True)
            if soup.title else None
        )

        links = set()

        for a in soup.find_all("a", href=True):
            href = urljoin(response.url, a["href"])

            host = urlparse(href).hostname or ""

            if host == "dpn.com.py" or host.endswith(
                ".dpn.com.py"
            ):
                links.add(href)

        print("INTERNAL LINKS:", len(links))

        print("\nSAMPLE LINKS:")

        for link in sorted(links)[:35]:
            print(link)

        print("\nPAGINATION LINKS:")

        for link in sorted(links):
            lower = link.lower()

            if any(x in lower for x in (
                "page=",
                "/page/",
                "pagina=",
                "/pagina/",
            )):
                print(link)

        print("\nFORMS:")

        for form in soup.find_all("form"):
            print(str(form)[:1000])

        print("\nPOSSIBLE API REFERENCES:")

        scripts = soup.find_all("script", src=True)

        for script in scripts:
            src = script["src"]

            if any(x in src.lower() for x in (
                "api",
                "app",
                "main",
                "search",
            )):
                print(urljoin(response.url, src))

    except Exception as exc:
        print("ERROR:", repr(exc))


if __name__ == "__main__":
    for path in PATHS:
        inspect(path)
