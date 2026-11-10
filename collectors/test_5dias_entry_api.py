
import re
import requests

BASE = "https://5dias.com.py/_next/static/chunks/app"

BUNDLES = {
    "daily_news": (
        BASE + "/noticiasdeldia/"
        "page-200f626ae8cf9351.js"
    ),
    "category": (
        BASE + "/category/%5Bcategory%5D/"
        "page-18f227ce9c9c50a9.js"
    ),
}

KEYWORDS = [
    "getEntrys",
    "/api/v1/entrys/",
    "fetch(",
    "axios",
    "useEffect",
    "setNoticias",
    "notice_url",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
})


def inspect_bundle(name, url):
    print("\n" + "=" * 75)
    print("BUNDLE:", name)

    response = session.get(url, timeout=30)
    print("STATUS:", response.status_code)
    response.raise_for_status()

    code = response.text

    print("SIZE:", len(code))

    # Extract every referenced entry API path.
    endpoints = sorted(set(re.findall(
        r"/api/v1/entrys/[A-Za-z0-9_/?=&.${}-]+",
        code
    )))

    print("\nENTRY API ENDPOINTS:")

    for endpoint in endpoints:
        print(endpoint)

    print("\nFETCH CALL CONTEXT:")

    for keyword in KEYWORDS:
        matches = list(re.finditer(
            re.escape(keyword),
            code,
            re.IGNORECASE
        ))

        print(f"\n{keyword}: {len(matches)} matches")

        for match in matches[:5]:
            start = max(0, match.start() - 450)
            end = min(len(code), match.end() + 900)

            print("\n---")
            print(code[start:end])

    # Save the entire bundle for further inspection.
    filename = f"5dias_{name}_bundle.js"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)

    print("\nSAVED:", filename)


if __name__ == "__main__":
    for name, url in BUNDLES.items():
        try:
            inspect_bundle(name, url)
        except Exception as exc:
            print("ERROR:", name, repr(exc))
