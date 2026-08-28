import requests
import trafilatura

url = "https://www.ultimahora.com/viaducto-en-pedrozo-propietario-de-inmueble-afirma-que-se-debio-liberar-la-franja-de-dominio-primero"

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