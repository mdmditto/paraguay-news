import json
import requests

API_URL = "https://api.queryly.com/json.aspx"

PARAMS = {
    "queryly_key": "33530b56c6aa4c20",
    "query": "Paraguay",
    "endindex": 0,
    "batchsize": 20,
    "callback": "searchPage.resultcallback",
    "showfaceted": "true",
    "extendeddatafields": "creator,imageresizer,promo_image",
    "timezoneoffset": 240,
}

response = requests.get(
    API_URL,
    params=PARAMS,
    timeout=30,
)

response.raise_for_status()

body = response.text.strip()

import json

callback = "searchPage.resultcallback("

start = body.find(callback)

if start == -1:
    raise ValueError(
        f"Callback not found: {body[:300]}"
    )

# Extract the JSON object using JSONDecoder.
# This avoids problems with the surrounding try/catch
# wrapper and parentheses inside article text.
json_start = start + len(callback)

decoder = json.JSONDecoder()

data, consumed = decoder.raw_decode(
    body[json_start:].lstrip()
)

print("Top-level keys:", list(data.keys()))

print(
    json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
    )[:6000]
)