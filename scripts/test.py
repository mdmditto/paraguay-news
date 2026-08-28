from extraction.article import extract_article


url = "https://www.abc.com.py/nacionales/2026/08/18/de-cartes-a-riera-el-historial-de-maniobras-de-los-rectores-para-esquivar-las-acreditaciones/"

article = extract_article(url)

if article is None:
    print("Extraction failed.")
else:
    print("Available fields:")
    print(article.keys())

    print("\nTITLE:")
    print(article.get("title"))

    print("\nAUTHOR:")
    print(article.get("author"))

    print("\nDATE:")
    print(article.get("date"))

    print("\nTEXT:")
    print(article.get("text", "")[:2000])