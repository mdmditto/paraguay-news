
import json
import requests
from bs4 import BeautifulSoup

BASE = "https://diarioparaguayo.com"

URLS = [
    BASE + "/noticia/felix-sosa-gimenez-retorna-como-presidente-de-la-ande",
    BASE + "/noticia/caso-ueno-bank-incautan-siete-lujosos-vehiculos-en-vivienda-de-miguel-vazquez-en-asuncion",
    BASE + "/noticia/la-tormenta-perfecta",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
})


def inspect(url):
    print("\n" + "=" * 70)
    print("ARTICLE:", url)

    response = session.get(url, timeout=30)
    print("STATUS:", response.status_code)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    print("\nMETA TAGS:")

    for meta in soup.find_all("meta"):
        key = (
            meta.get("property")
            or meta.get("name")
            or meta.get("itemprop")
            or ""
        )

        if any(word in key.lower() for word in (
            "date", "time", "publish", "modified"
        )):
            print(key, "=", meta.get("content"))

    print("\nJSON-LD:")

    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):
        try:
            data = json.loads(script.string or script.get_text())
            print(json.dumps(data, ensure_ascii=False, indent=2)[:4000])
        except (ValueError, TypeError):
            continue

    print("\nHTML DATE ELEMENTS:")

    for element in soup.select(
        "time, [datetime], .fecha, .article-date, "
        ".published, .post-date, .news-date"
    ):
        print(str(element)[:500])

    print("\nTEXT SAMPLE:")
    print(soup.get_text(" ", strip=True)[:1000])


if __name__ == "__main__":
    for url in URLS:
        try:
            inspect(url)
        except Exception as exc:
            print("ERROR:", exc)
