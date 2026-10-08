from datetime import datetime

import torch
from sentence_transformers import SentenceTransformer
from sqlalchemy import select

from database.db import SessionLocal
from database.models import Article, ArticleEmbedding


# =========================================================
# CONFIG
# =========================================================

MODEL_NAME = "jinaai/jina-embeddings-v5-text-small"
TASK = "text-matching"
DIMENSIONS = 1024
MAX_EMBEDDING_TOKENS = 1024

# Number of articles processed before committing to PostgreSQL.
BATCH_LIMIT = 900

# Number of articles sent through the GPU at once.
BATCH_SIZE = 2


# =========================================================
# ARTICLE TEXT
# =========================================================

def build_article_text(
    article: Article,
    tokenizer=None,
    max_tokens: int = MAX_EMBEDDING_TOKENS,
) -> str:
    """
    Build title + body representation for embedding.

    When a tokenizer is supplied, truncate the body so
    the complete text stays within the token budget.

    The original database article remains unchanged.
    """

    title = (article.title or "").strip()
    body = (article.body or "").strip()

    prefix = f"Título: {title}\n\nArtículo:\n"

    if tokenizer is None:
        return prefix + body

    # Leave room for any special tokens added during encoding.
    special_tokens = tokenizer.num_special_tokens_to_add(
        pair=False
    )

    budget = max_tokens - special_tokens

    prefix_ids = tokenizer.encode(
        prefix,
        add_special_tokens=False,
    )

    body_ids = tokenizer.encode(
        body,
        add_special_tokens=False,
    )

    remaining = max(0, budget - len(prefix_ids))

    if len(prefix_ids) > budget:
        prefix_ids = prefix_ids[:budget]
        body_ids = []
    else:
        body_ids = body_ids[:remaining]

    return tokenizer.decode(
        prefix_ids + body_ids,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )


# =========================================================
# MODEL
# =========================================================

def load_model():
    """
    Load Jina Embeddings v5-small on the GPU.
    """

    print("Loading Jina v5-small...")

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is not available."
        )

    print(
        "GPU:",
        torch.cuda.get_device_name(0),
    )

    model = SentenceTransformer(
        MODEL_NAME,
        trust_remote_code=True,
        device="cuda",
        model_kwargs={
            "dtype": torch.bfloat16,
        },
    )

    print("Model loaded.")

    return model


# =========================================================
# DATABASE
# =========================================================

def get_articles_without_embeddings(
    session,
    limit: int,
):
    """
    Return articles that do not already have an embedding
    for the current model/task combination.

    This makes the pipeline resumable and prevents existing
    embeddings from being regenerated.
    """

    already_embedded = (
        select(
            ArticleEmbedding.article_id
        )
        .where(
            ArticleEmbedding.model == MODEL_NAME,
            ArticleEmbedding.task == TASK,
        )
    )

    stmt = (
        select(Article)
        .where(
            ~Article.id.in_(
                already_embedded
            )
        )
        .order_by(
            Article.published_at.desc().nullslast(),
            Article.id.desc(),
        )
        .limit(limit)
    )

    return list(
        session.scalars(
            stmt
        ).all()
    )


# =========================================================
# MAIN PIPELINE
# =========================================================

def main():

    print("=" * 60)
    print("ARTICLE EMBEDDING PIPELINE")
    print("=" * 60)

    # Load the model only once.
    model = load_model()

    total_saved = 0
    batch_number = 0

    while True:

        batch_number += 1

        session = SessionLocal()

        try:

            # -------------------------------------------------
            # Get next group of unembedded articles
            # -------------------------------------------------

            articles = get_articles_without_embeddings(
                session,
                BATCH_LIMIT,
            )

            if not articles:

                print()
                print("=" * 60)
                print("EMBEDDING PIPELINE COMPLETE")
                print("=" * 60)

                print(
                    f"Total embeddings saved this run: "
                    f"{total_saved}"
                )

                break

            print()
            print("=" * 60)
            print(
                f"BATCH {batch_number}"
            )
            print("=" * 60)

            print(
                f"Articles to embed: "
                f"{len(articles)}"
            )

            # -------------------------------------------------
            # Build text representations
            # -------------------------------------------------

            tokenizer = model.tokenizer

            texts = [
                build_article_text(
                    article,
                    tokenizer=tokenizer,
                    max_tokens=MAX_EMBEDDING_TOKENS,
                )
                for article in articles
         ]
            print(
                f"Generating embeddings "
                f"(GPU batch size={BATCH_SIZE})..."
            )

            torch.cuda.reset_peak_memory_stats()

            # -------------------------------------------------
            # Generate embeddings
            # -------------------------------------------------

            with torch.inference_mode():

                embeddings = model.encode(
                    texts,
                    task=TASK,
                    batch_size=BATCH_SIZE,
                    normalize_embeddings=True,
                    show_progress_bar=True,
                    convert_to_numpy=True,
                )

            print(
                "\nEmbedding shape:",
                embeddings.shape,
            )

            # -------------------------------------------------
            # Validate dimensions
            # -------------------------------------------------

            if embeddings.shape[1] != DIMENSIONS:

                raise RuntimeError(
                    f"Expected {DIMENSIONS} dimensions, "
                    f"got {embeddings.shape[1]}"
                )

            # -------------------------------------------------
            # Save to PostgreSQL
            # -------------------------------------------------

            print(
                "\nSaving embeddings..."
            )

            created_at = (
                datetime.now().astimezone()
            )

            for article, embedding in zip(
                articles,
                embeddings,
            ):

                row = ArticleEmbedding(
                    article_id=article.id,
                    model=MODEL_NAME,
                    task=TASK,
                    dimensions=DIMENSIONS,
                    embedding=embedding.tolist(),
                    created_at=created_at,
                )

                session.add(row)

            # One transaction per BATCH_LIMIT articles.
            session.commit()

            saved = len(articles)

            total_saved += saved

            print(
                f"\nSaved {saved} embeddings."
            )

            print(
                f"Total saved this run: "
                f"{total_saved}"
            )

            print(
                "Peak GPU memory:",
                round(
                    torch.cuda.max_memory_allocated()
                    / 1024**3,
                    2,
                ),
                "GB",
            )

            # -------------------------------------------------
            # Release batch objects before next iteration
            # -------------------------------------------------

            del embeddings
            del texts
            del articles

            # Release unused cached CUDA memory.
            torch.cuda.empty_cache()

        # -----------------------------------------------------
        # Graceful Ctrl+C
        # -----------------------------------------------------

        except KeyboardInterrupt:

            session.rollback()

            print()
            print("=" * 60)
            print("INTERRUPTED")
            print("=" * 60)

            print(
                "The current unfinished database "
                "transaction was rolled back."
            )

            print(
                f"Previously committed embeddings "
                f"from this run: {total_saved}"
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