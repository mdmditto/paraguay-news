
import requests
from bs4 import BeautifulSoup

URLS = {
    "daily": "https://5dias.com.py/noticiasdeldia",
    "category": "https://5dias.com.py/category/Negocios",
}

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
})


for name, url in URLS.items():
    print(f"\n{'=' * 70}")
    print(name, url)

    response = session.get(url, timeout=30)
    print("Status:", response.status_code)
    print("HTML length:", len(response.text))

    soup = BeautifulSoup(response.text, "html.parser")

    links = sorted({
        a.get("href")
        for a in soup.select('a[href*="/article/"]')
        if a.get("href")
    })

    print("Article links in HTML:", len(links))

    for link in links[:15]:
        print(" ", link)

    scripts = soup.find_all("script")

    next_data = soup.find(
        "script", id="__NEXT_DATA__"
    )

    print("__NEXT_DATA__ present:", bool(next_data))

    flight_scripts = [
        s.get_text()
        for s in scripts
        if "self.__next_f.push" in s.get_text()
    ]

    print("React Flight scripts:", len(flight_scripts))
    print(
        "React Flight total characters:",
        sum(map(len, flight_scripts))
    )

    for keyword in [
        "notice_url",
        "published_at",
        "publication_date",
        "createdAt",
        "2026-11-04",
    ]:
        print(
            f"{keyword}:",
            response.text.count(keyword)
        )

    filename = f"5dias_{name}_server.html"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(response.text)

    print("Saved:", filename)
