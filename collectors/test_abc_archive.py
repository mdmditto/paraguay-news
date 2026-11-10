import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

API_URL = "https://api.queryly.com/json.aspx"
CALLBACK = "searchPage.resultcallback("

session = requests.Session()

def search(query, offset=0, batchsize=100):
    params = {
        "queryly_key": "33530b56c6aa4c20",
        "query": query,
        "endindex": offset,
        "batchsize": batchsize,
        "callback": "searchPage.resultcallback",
        "showfaceted": "true",
        "extendeddatafields": "creator,imageresizer,promo_image",
        "timezoneoffset": 240,
    }

    response = session.get(
        API_URL,
        params=params,
        timeout=30,
    )
    response.raise_for_status()

    body = response.text
    pos = body.find(CALLBACK)

    if pos == -1:
        raise ValueError(body[:300])

    decoder = json.JSONDecoder()

    data, _ = decoder.raw_decode(
        body[pos + len(CALLBACK):].lstrip()
    )

    return data


def inspect(query):
    print(f"\n{'=' * 60}")
    print(f"QUERY: {query!r}")

    for offset in (0, 100):
        try:
            data = search(query, offset)

            metadata = data.get("metadata", {})
            items = data.get("items", [])

            print(
                f"\nOffset: {offset}",
                f"Total: {metadata.get('total')}",
                f"Returned: {len(items)}",
                f"Next index: {metadata.get('endindex')}",
            )

            for item in items[:3]:
                timestamp = item.get("pubdateunix")

                published = (
                    datetime.fromtimestamp(
                        timestamp,
                        ZoneInfo("America/Asuncion"),
                    )
                    if timestamp
                    else None
                )

                print(
                    published,
                    item.get("title"),
                )

        except Exception as exc:
            print("ERROR:", exc)


if __name__ == "__main__":
    inspect("")
    inspect("Paraguay")
