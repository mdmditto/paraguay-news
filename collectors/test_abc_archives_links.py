import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE = "https://www.abc.com.py"

PAGES = [
    f"{BASE}/ultimas-noticias/",
    f"{BASE}/politica/",
    f"{BASE}/buscar/",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

for page in PAGES:
    print(f"\n{'=' * 70}")
    print("PAGE:", page)

    try:
        response = requests.get(
            page,
            headers=HEADERS,
            timeout=20,
        )
        print("Status:", response.status_code)
        print("Final URL:", response.url)

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        candidates = set()

        for tag in soup.find_all(["a", "form", "link"]):
            href = tag.get("href") or tag.get("action")

            if not href:
                continue

            full_url = urljoin(response.url, href)

            if any(
                term in full_url.lower()
                for term in (
                    "buscar",
                    "search",
                    "page=",
                    "pagina",
                    "archivo",
                    "fecha",
                )
            ):
                candidates.add(full_url)

        for url in sorted(candidates):
            print(url)

    except requests.RequestException as exc:
        print("ERROR:", exc)
