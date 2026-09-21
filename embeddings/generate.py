from datetime import datetime

import torch
from sentence_transformers import SentenceTransformer
from sqlalchemy import select

from database.db import SessionLocal
from database.models import Article, ArticleEmbedding


MODEL_NAME = "jinaai/jina-embeddings-v5-text-small"
TASK = "text-matching"
DIMENSIONS = 1024

LIMIT = 100
BATCH_SIZE = 8


def build_article_text(article: Article) -> str:
    """
    Build the text that will represent an article.

    For now:
        title + body

    Later we can experiment with:
        title + body + entities
        title weighted differently
        summaries
        etc.
    """

    title = (article.title or "").strip()
    body = (article.body or "").strip()

    return f"""Título: {title}

Artículo:
{body}"""


def load_model():
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


def get_articles_without_embeddings(
    session,
    limit: int,
):
    """
    Get recent articles that do not already have
    an embedding for this model/task.
    """

    already_embedded = (
        select(ArticleEmbedding.article_id)
        .where(
            ArticleEmbedding.model == MODEL_NAME,
            ArticleEmbedding.task == TASK,
        )
    )

    stmt = (
        select(Article)
        .where(
            ~Article.id.in_(already_embedded)
        )
        .order_by(
            Article.published_at.desc().nullslast(),
            Article.id.desc(),
        )
        .limit(limit)
    )

    return list(
        session.scalars(stmt).all()
    )


def main():

    print("=" * 60)
    print("ARTICLE EMBEDDING PIPELINE")
    print("=" * 60)

    model = load_model()

    session = SessionLocal()

    try:

        articles = get_articles_without_embeddings(
            session,
            LIMIT,
        )

        print(
            f"\nArticles to embed: {len(articles)}"
        )

        if not articles:
            print(
                "No new articles need embeddings."
            )
            return

        texts = [
            build_article_text(article)
            for article in articles
        ]

        print(
            f"Generating embeddings "
            f"(batch size={BATCH_SIZE})..."
        )

        torch.cuda.reset_peak_memory_stats()

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

        if embeddings.shape[1] != DIMENSIONS:
            raise RuntimeError(
                f"Expected {DIMENSIONS} dimensions, "
                f"got {embeddings.shape[1]}"
            )

        print("\nSaving embeddings...")

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
                created_at=datetime.now().astimezone(),
            )

            session.add(row)

        session.commit()

        print(
            f"\nSaved {len(articles)} embeddings."
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

    except Exception:

        session.rollback()
        raise

    finally:

        session.close()


if __name__ == "__main__":
    main()
