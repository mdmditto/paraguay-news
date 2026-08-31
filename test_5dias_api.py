import re
import requests


BASE_URL = "https://5dias.com.py"

JS_URL = (
    BASE_URL
    + "/_next/static/chunks/app/"
    + "noticiasdeldia/"
    + "page-a118d77588362f36.js"
)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


response = requests.get(
    JS_URL,
    headers=HEADERS,
    timeout=30,
)

response.raise_for_status()

js = response.text


print("Status:", response.status_code)
print("JS length:", len(js))


print("\n--- ABSOLUTE URLS ---")

urls = sorted(
    set(
        re.findall(
            r'https?://[^"\'`\s]+',
            js,
        )
    )
)

for url in urls:
    print(url)


print("\n--- API-LIKE STRINGS ---")

patterns = [
    r'[^"\']*api[^"\']*',
    r'[^"\']*noticia[^"\']*',
    r'[^"\']*article[^"\']*',
    r'[^"\']*fetch[^"\']*',
    r'[^"\']*axios[^"\']*',
]

found = set()

for pattern in patterns:

    matches = re.findall(
        pattern,
        js,
        flags=re.IGNORECASE,
    )

    for match in matches:

        match = match.strip()

        if not match:
            continue

        if len(match) > 500:
            continue

        if match in found:
            continue

        found.add(match)

        print(match)


print("\n--- FETCH CONTEXT ---")

for match in re.finditer(
    r'fetch',
    js,
    flags=re.IGNORECASE,
):

    start = max(
        0,
        match.start() - 300,
    )

    end = min(
        len(js),
        match.end() + 500,
    )

    print("\n")
    print(
        js[start:end]
    )


print("\n--- NOTICIA CONTEXT ---")

for match in re.finditer(
    r'noticia',
    js,
    flags=re.IGNORECASE,
):

    start = max(
        0,
        match.start() - 300,
    )

    end = min(
        len(js),
        match.end() + 500,
    )

    print("\n")
    print(
        js[start:end]
    )
