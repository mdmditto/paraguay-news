import re
import unicodedata
from datetime import datetime, timezone

import torch
from sqlalchemy import select
from transformers import pipeline

from database.db import SessionLocal
from database.models import (
    Article,
    ArticleEmbedding,
    ArticleEntity,
    ArticleNERStatus,
)


# =========================================================
# CONFIG
# =========================================================

MODEL_NAME = "Davlan/xlm-roberta-base-ner-hrl"

EMBEDDING_MODEL = (
    "jinaai/jina-embeddings-v5-text-small"
)

EMBEDDING_TASK = "text-matching"

# Only keep entities above this confidence.
MIN_CONFIDENCE = 0.80

# Number of articles processed before fetching
# another database chunk.
BATCH_LIMIT = 1000

# Commit progress every N articles.
COMMIT_EVERY = 50


# =========================================================
# NORMALIZATION
# =========================================================

def normalize_entity(text: str) -> str:
    """
    Normalize entity text while preserving accents.

    Examples:

        Hernán Rivas
        HERNÁN RIVAS
        hernán rivas

    all become:

        hernán rivas
    """

    text = unicodedata.normalize(
        "NFKC",
        text,
    )

    text = text.lower().strip()

    # Collapse repeated whitespace.
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    # Remove whitespace before punctuation.
    text = re.sub(
        r"\s+([.,;:])",
        r"\1",
        text,
    )

    return text


# =========================================================
# MODEL
# =========================================================

def load_ner():
    """
    Load the multilingual NER model on CUDA.
    """

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


# =========================================================
# DATABASE SELECTION
# =========================================================

def get_articles(session):
    """
    Select articles that:

    1. already have the required Jina embedding
    2. do NOT have a processing-status row for this
       NER model

    The status table is important because an article
    can be successfully processed while producing
    zero qualifying entities.
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
            ArticleNERStatus.article_id
        )
        .where(
            ArticleNERStatus.model
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
        .limit(
            BATCH_LIMIT
        )
    )

    return list(
        session.scalars(
            stmt
        ).all()
    )


# =========================================================
# ARTICLE TEXT
# =========================================================

def build_text(article: Article) -> str:
    """
    NER operates on title + body.
    """

    title = (
        article.title or ""
    ).strip()

    body = (
        article.body or ""
    ).strip()

    return f"{title}\n\n{body}"


# =========================================================
# ENTITY EXTRACTION
# =========================================================

def extract_entities(
    ner,
    text: str,
):
    """
    Run NER and return unique PER/ORG/LOC entities.

    If the same normalized entity appears multiple times,
    retain the highest-confidence occurrence.
    """

    entities = ner(
        text
    )

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

        existing = (
            article_entities.get(
                key
            )
        )

        if (
            existing is None
            or score > existing["score"]
        ):
            article_entities[key] = {
                "text": entity_text,
                "score": score,
            }

    return article_entities


# =========================================================
# PROCESS ONE ARTICLE
# =========================================================

def process_article(
    session,
    ner,
    article,
):
    """
    Process one article and add both:

        ArticleEntity rows
        ArticleNERStatus row

    to the current transaction.

    Returns the number of entities found.
    """

    text = build_text(
        article
    )

    if text.strip():

        article_entities = (
            extract_entities(
                ner,
                text,
            )
        )

    else:

        article_entities = {}

    processed_at = datetime.now(
        timezone.utc
    )

    # -----------------------------------------------------
    # Save entities
    # -----------------------------------------------------

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
            created_at=processed_at,
        )

        session.add(
            row
        )

    # -----------------------------------------------------
    # Mark article as processed even if entity_count = 0
    # -----------------------------------------------------

    status = ArticleNERStatus(
        article_id=article.id,
        model=MODEL_NAME,
        entity_count=len(
            article_entities
        ),
        processed_at=processed_at,
    )

    session.add(
        status
    )

    return len(
        article_entities
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 60)
    print("ARTICLE NER PIPELINE")
    print("=" * 60)

    # Load the model only once.
    ner = load_ner()

    total_processed = 0
    total_entities = 0
    total_zero_entity = 0

    batch_number = 0

    while True:

        batch_number += 1

        session = SessionLocal()

        try:

            # -------------------------------------------------
            # Fetch next chunk
            # -------------------------------------------------

            articles = get_articles(
                session
            )

            if not articles:

                print()
                print("=" * 60)
                print("NER PIPELINE COMPLETE")
                print("=" * 60)

                print(
                    f"Articles processed this run: "
                    f"{total_processed}"
                )

                print(
                    f"Entities saved this run: "
                    f"{total_entities}"
                )

                print(
                    f"Articles with zero entities: "
                    f"{total_zero_entity}"
                )

                break

            print()
            print("=" * 60)
            print(
                f"BATCH {batch_number}"
            )
            print("=" * 60)

            print(
                f"Articles in batch: "
                f"{len(articles)}"
            )

            batch_processed = 0
            batch_entities = 0
            batch_zero_entity = 0

            # -------------------------------------------------
            # Process articles
            # -------------------------------------------------

            for article in articles:

                entity_count = (
                    process_article(
                        session,
                        ner,
                        article,
                    )
                )

                batch_processed += 1
                batch_entities += (
                    entity_count
                )

                total_processed += 1
                total_entities += (
                    entity_count
                )

                if entity_count == 0:

                    batch_zero_entity += 1
                    total_zero_entity += 1

                # ---------------------------------------------
                # Commit periodically
                # ---------------------------------------------

                if (
                    batch_processed
                    % COMMIT_EVERY
                    == 0
                ):

                    session.commit()

                    print(
                        f"[{batch_processed}/"
                        f"{len(articles)}] "
                        f"entities="
                        f"{batch_entities} "
                        f"zero="
                        f"{batch_zero_entity} "
                        f"| total processed="
                        f"{total_processed}"
                    )

            # Commit anything left after the last group of 50.
            session.commit()

            print()
            print(
                f"Batch {batch_number} complete."
            )

            print(
                f"Articles processed: "
                f"{batch_processed}"
            )

            print(
                f"Entities saved: "
                f"{batch_entities}"
            )

            print(
                f"Zero-entity articles: "
                f"{batch_zero_entity}"
            )

            del articles

        # -----------------------------------------------------
        # Ctrl+C
        # -----------------------------------------------------

        except KeyboardInterrupt:

            session.rollback()

            print()
            print("=" * 60)
            print("INTERRUPTED")
            print("=" * 60)

            print(
                "The current uncommitted group "
                "was rolled back."
            )

            print(
                "Previously committed articles "
                "remain processed."
            )

            print()
            print(
                "Run the script again to resume."
            )

            break

        # -----------------------------------------------------
        # Other errors
        # -----------------------------------------------------

        except Exception:

            session.rollback()
            raise

        finally:

            session.close()


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    main()