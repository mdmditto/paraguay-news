from transformers import pipeline


MODEL_NAME = "Davlan/xlm-roberta-base-ner-hrl"


ner = pipeline(
    "token-classification",
    model=MODEL_NAME,
    aggregation_strategy="simple",
    device=0,
)


texts = [
    """
    El senador Hernán Rivas deberá enfrentar un juicio oral
    por el supuesto título falso de abogado, según resolvió
    un tribunal en Asunción.
    """,

    """
    El presidente Santiago Peña se reunió con representantes
    del Banco Central del Paraguay en Asunción.
    """,

    """
    Olimpia enfrentará a Cerro Porteño este domingo en
    el estadio Defensores del Chaco.
    """,

    """
    La Municipalidad de Ciudad del Este anunció nuevas
    medidas para el tránsito en la capital de Alto Paraná.
    """,
]


for text in texts:

    print("\n" + "=" * 70)
    print(text.strip())
    print("=" * 70)

    entities = ner(text)

    for entity in entities:

        print(
            f"{entity['entity_group']:5} | "
            f"{entity['word']:30} | "
            f"{entity['score']:.4f}"
        )
