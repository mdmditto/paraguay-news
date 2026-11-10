
import json
import re
from pathlib import Path
from collections import Counter
from bs4 import BeautifulSoup

FILES = [
    "5dias_daily_server.html",
    "5dias_category_server.html",
]


def extract_articles(path):
    html = Path(path).read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    articles = {}

    for script in soup.find_all("script"):
        content = script.get_text()

        if "self.__next_f.push" not in content:
            continue

        # Decode the JSON string passed into the React Flight payload.
        for match in re.finditer(
            r'self\.__next_f\.push\(\[1,("(?:\\.|[^"\\])*")\]\)',
            content,
            re.DOTALL,
        ):
            try:
                payload = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

            # Find complete article objects within the payload.
            decoder = json.JSONDecoder()

            for start in [
                m.start()
                for m in re.finditer(r'\{"_id":', payload)
            ]:
                try:
                    obj, _ = decoder.raw_decode(payload[start:])
                except json.JSONDecodeError:
                    continue

                if not isinstance(obj, dict):
                    continue

                slug = obj.get("notice_url")
                published = obj.get("publish_date")

                if slug and published:
                    articles[slug] = {
                        "title": obj.get("title"),
                        "url": (
                            "https://5dias.com.py/article/"
                            + slug
                        ),
                        "publish_date": published,
                    }

    return list(articles.values())


all_articles = {}

for filename in FILES:
    if not Path(filename).exists():
        print("Missing:", filename)
        continue

    articles = extract_articles(filename)

    print(filename, ":", len(articles), "articles")

    for article in articles:
        all_articles[article["url"]] = article

articles = list(all_articles.values())

counts = Counter(
    a["publish_date"][:10]
    for a in articles
)

print("\nARTICLES BY PUBLICATION DATE:")

for date, count in sorted(counts.items()):
    print(date, count)

print("\nTARGET ARTICLES:")

for article in articles:
    if "2026-11-04" <= article["publish_date"][:10] <= "2026-11-06":
        print(article["publish_date"], article["url"])

Path("5dias_extracted_articles.json").write_text(
    json.dumps(articles, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print("\nTOTAL UNIQUE:", len(articles))

