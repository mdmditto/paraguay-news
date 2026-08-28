from extraction.article import extract_article


url = "https://www.ultimahora.com/viaducto-en-pedrozo-propietario-de-inmueble-afirma-que-se-debio-liberar-la-franja-de-dominio-primero"

article = extract_article(url)

print(article)