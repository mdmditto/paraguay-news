
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE = "https://5dias.com.py"

URLS = [
    BASE + "/noticiasdeldia",
    BASE + "/category/Negocios",
    BASE + "/category/Econom%C3%ADa%20y%20Finanzas",
    BASE + "/subcategory/Internacional",
    BASE + "/banca-y-finanzas",
    BASE + "/especiales",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
})

PATTERNS = [
    r"https?://[^\s\"'<>]+/api/[^\s\"'<>]+",
    r"/api/[a-zA-Z0-9_/?=&.%:-]+",
    r"https?://[^\s\"'<>]+graphql[^\s\"'<>]*",
    r"(?i).{0,100}(?:pagination|pageSize|perPage|hasNextPage|totalPages).{0,150}",
]


def inspect_page(url):
    print("\n" + "=" * 75)
    print("PAGE:", url)

    try:
        response = session.get(url, timeout=30)
        print("STATUS:", response.status_code)

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        article_links = list(dict.fromkeys(
            urljoin(response.url, a["href"])
            for a in soup.find_all("a", href=True)
            if "/article/" in a["href"]
        ))

        print("ARTICLE LINKS:", len(article_links))

        for link in article_links[:10]:
            print(" ", link)

        print("\nPAGINATION ELEMENTS:")

        for element in soup.select(
            "a[rel='next'], button, "
            "[class*='pagination'], [class*='load-more']"
        ):
            text = element.get_text(" ", strip=True)
            if any(word in text.lower() for word in (
                "más", "more", "siguiente",
                "anterior", "cargar", "ver más"
            )):
                print(str(element)[:500])

        print("\nNEXT.JS DATA:")

        next_data = soup.find(
            "script", id="__NEXT_DATA__"
        )

        if next_data:
            print(
                next_data.get_text()[:1500]
            )
        else:
            print("No __NEXT_DATA__ script")

        print("\nPOTENTIAL API REFERENCES:")

        matches = set()

        for pattern in PATTERNS:
            matches.update(
                re.findall(
                    pattern,
                    response.text
                )
            )

        for match in sorted(matches)[:15]:
            print(str(match)[:300])

        return [
            urljoin(response.url, script["src"])
            for script in soup.find_all(
                "script", src=True
            )
            if "/_next/static/" in script["src"]
        ]

    except Exception as exc:
        print("ERROR:", repr(exc))
        return []


def inspect_bundles(urls):
    print("\n" + "=" * 75)
    print("JAVASCRIPT BUNDLE INSPECTION")

    matches = set()

    # Limit requests to avoid downloading
    # every JavaScript file.
    for url in list(dict.fromkeys(urls))[:12]:
        try:
            response = session.get(
                url, timeout=30
            )

            if response.status_code != 200:
                continue

            content = response.text

            print(
                "\nBUNDLE:",
                url.split("/")[-1],
                "SIZE:",
                len(content)
            )

            for pattern in PATTERNS:
                for match in re.findall(
                    pattern, content
                )[:10]:
                    matches.add(
                        str(match)[:350]
                    )

        except Exception as exc:
            print("ERROR:", exc)

    print("\nPOTENTIAL ENDPOINTS / PAGINATION:")

    for match in sorted(matches)[:60]:
        print(match)


if __name__ == "__main__":
    scripts = []

    for url in URLS:
        scripts.extend(
            inspect_page(url)
        )

    inspect_bundles(scripts)
