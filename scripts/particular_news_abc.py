import requests
import trafilatura

url = "https://www.abc.com.py/politica/2026/08/18/medico-de-cabecera-de-alliana-figura-en-lista-de-comisionados-de-la-eby/"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
}

response = requests.get(
    url,
    headers=headers,
    timeout=20
)

text = trafilatura.extract(
    response.text,
    include_comments=False,
    include_tables=False
)

print(text)