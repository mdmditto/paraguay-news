
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE = "https://5dias.com.py"

PAGES = [
    BASE + "/noticiasdeldia",
    BASE + "/category/Negocios",
]

KEYWORDS = [
    "home_noticias_btn_cargar_mas",
    "cargarMas",
    "loadMore",
    "loadmore",
    "5diasbkn",
    "/api/v1/",
    "getArticles",
    "getNews",
    "getNoticias",
    "pageSize",
    "offset",
    "skip",
    "limit",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
})


def get_scripts():
    scripts = set()

    for page in PAGES:
        response = session.get(page, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for script in soup.find_all("script", src=True):
            url = urljoin(page, script["src"])

            if "/_next/static/" in url:
                scripts.add(url)

    return sorted(scripts)


def inspect_script(url):
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()

        content = response.text

        matches = []

        for keyword in KEYWORDS:
            for match in re.finditer(
                re.escape(keyword),
                content,
                re.IGNORECASE
            ):
                start = max(0, match.start() - 300)
                end = min(
                    len(content),
                    match.end() + 500
                )

                snippet = content[start:end]

                matches.append((keyword, snippet))

                if len(matches) >= 20:
                    break

            if len(matches) >= 20:
                break

        if not matches:
            return

        print("\n" + "=" * 75)
        print("SCRIPT:", url)
        print("SIZE:", len(content))

        for keyword, snippet in matches:
            print("\nKEYWORD:", keyword)
            print(snippet[:900])

    except Exception as exc:
        print("ERROR:", url, exc)


if __name__ == "__main__":
    scripts = get_scripts()

    print("TOTAL JAVASCRIPT FILES:", len(scripts))

    for script in scripts:
        inspect_script(script)
