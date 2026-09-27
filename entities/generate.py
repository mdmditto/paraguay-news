import re
import unicodedata
from datetime import datetime, timezone

import torch
from sqlalchemy import select
from transformers import pipeline

from database.db import SessionLocal
from database.models import Article, ArticleEmbedding, ArticleEntity


MODEL_NAME = "Davlan/xlm-roberta-base-ner-hrl"

EMBEDDING_MODEL = "jinaai/jina-embeddings-v5-text-small"
EMBEDDING_TASK = "text-matching"

# Only keep entities above this confidence
MIN_CONFIDENCE = 0.80

# Process articles in chunks
LIMIT = 1000


def normalize_entity(text: str) -> str:
    """
    Normalize an entity so that variations such as:

        "Hernán Rivas"
        "HERNÁN RIVAS"
        "hernán rivas"

    become the same string.

    Accents are preserved because they are meaningful
    in Spanish.
    """

    text = unicodedata.normalize(
        "NFKC",
        text,
    )

    text = text.lower().strip()

    # Collapse repeated whitespace
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    # Remove whitespace before punctuation
    text = re.sub(
        r"\s+([.,;:])",
        r"\1",
        text,
    )

    return text


def load_ner():

    print("=" * 60)
    print("LOADING NER MODEL")
    print("=" * 60)

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is not available."
        )

    print(
        "GPU:",
        torch.cuda.get_device_name(0),
    )

    ner = pipeline(
        "token-classification",
        model=MODEL_NAME,
        tokenizer=MODEL_NAME,
        aggregation_strategy="simple",
        device=0,
    )

    print("NER model loaded.")

    return ner


def get_articles(session):
    """
    Select articles that:

    1. already have a Jina embedding
    2. have not yet been processed by this NER model

    This keeps our NER experiment aligned with the
    embedding experiment.
    """

    embedded_articles = (
        select(
            ArticleEmbedding.article_id
        )
        .where(
            ArticleEmbedding.model
            == EMBEDDING_MODEL,

            ArticleEmbedding.task
            == EMBEDDING_TASK,
        )
    )

    already_processed = (
        select(
            ArticleEntity.article_id
        )
        .where(
            ArticleEntity.model
            == MODEL_NAME
        )
    )

    stmt = (
        select(Article)
        .where(
            Article.id.in_(
                embedded_articles
            ),

            ~Article.id.in_(
                already_processed
            ),
        )
        .order_by(
            Article.id
        )
        .limit(LIMIT)
    )

    return list(
        session.scalars(stmt).all()
    )


def build_text(article: Article) -> str:

    title = (
        article.title or ""
    ).strip()

    body = (
        article.body or ""
    ).strip()

    return f"{title}\n\n{body}"


def main():

    ner = load_ner()

    session = SessionLocal()

    try:

        articles = get_articles(
            session
        )

        print()
        print(
            f"Articles to process: "
            f"{len(articles)}"
        )

        total_entities = 0

        for i, article in enumerate(
            articles,
            start=1,
        ):

            text = build_text(
                article
            )

            if not text.strip():
                continue

            entities = ner(
                text
            )

            # ------------------------------------------
            # Deduplicate entities inside the article
            # ------------------------------------------

            article_entities = {}

            for entity in entities:

                entity_type = (
                    entity["entity_group"]
                )

                if entity_type not in {
                    "PER",
                    "ORG",
                    "LOC",
                }:
                    continue

                score = float(
                    entity["score"]
                )

                if score < MIN_CONFIDENCE:
                    continue

                entity_text = (
                    entity["word"]
                    .strip()
                )

                normalized = normalize_entity(
                    entity_text
                )

                if not normalized:
                    continue

                key = (
                    normalized,
                    entity_type,
                )

                # If the same entity occurs several
                # times, keep the highest-confidence
                # occurrence.
                existing = (
                    article_entities.get(
                        key
                    )
                )

                if (
                    existing is None
                    or score
                    > existing["score"]
                ):
                    article_entities[key] = {
                        "text": entity_text,
                        "score": score,
                    }

            # ------------------------------------------
            # Save
            # ------------------------------------------

            for (
                normalized,
                entity_type,
            ), value in (
                article_entities.items()
            ):

                row = ArticleEntity(
                    article_id=article.id,
                    entity_text=value[
                        "text"
                    ],
                    entity_type=entity_type,
                    normalized_text=normalized,
                    model=MODEL_NAME,
                    confidence=value[
                        "score"
                    ],
                    created_at=datetime.now(
                        timezone.utc
                    ),
                )

                session.add(row)

                total_entities += 1

            # Commit periodically
            if i % 50 == 0:

                session.commit()

                print(
                    f"[{i}/{len(articles)}] "
                    f"entities: "
                    f"{total_entities}"
                )

        session.commit()

        print()
        print("=" * 60)
        print("DONE")
        print("=" * 60)

        print(
            f"Articles processed: "
            f"{len(articles)}"
        )

        print(
            f"Entities saved: "
            f"{total_entities}"
        )

    except Exception:

        session.rollback()
        raise

    finally:

        session.close()


if __name__ == "__main__":
    main()
