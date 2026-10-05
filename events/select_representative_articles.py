from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
from sqlalchemy import select

from database.db import SessionLocal
from database.models import (
    Article,
    ArticleEmbedding,
    Event,
    EventArticle,
    Source,
)


# =========================================================
# CONFIGURATION
# =========================================================

EMBEDDING_MODEL = "jinaai/jina-embeddings-v5-text-small"
EMBEDDING_TASK = "text-matching"

CENTRALITY_WEIGHT = 0.50
SOURCE_DIVERSITY_WEIGHT = 0.30
COMPLETENESS_WEIGHT = 0.20

COMMIT_EVERY = 100


# =========================================================
# EMBEDDING
# =========================================================

def embedding_to_numpy(value) -> np.ndarray:

    if isinstance(value, str):

        vector = np.fromstring(
            value.strip("[]"),
            sep=",",
            dtype=np.float32,
        )

    else:

        vector = np.asarray(
            value,
            dtype=np.float32,
        )

    norm = np.linalg.norm(vector)

    if norm > 0:
        vector = vector / norm

    return vector


# =========================================================
# LOAD EVENT ARTICLES
# =========================================================

def load_event_articles(
    session,
    event_id: int,
):

    stmt = (
        select(
            Article.id,
            Article.source_id,
            Article.title,
            Article.body,
            Article.image_url,
            Article.published_at,
            Article.scraped_at,
            ArticleEmbedding.embedding,
        )
        .join(
            EventArticle,
            EventArticle.article_id == Article.id,
        )
        .join(
            ArticleEmbedding,
            ArticleEmbedding.article_id == Article.id,
        )
        .where(
            EventArticle.event_id == event_id,
            ArticleEmbedding.model == EMBEDDING_MODEL,
            ArticleEmbedding.task == EMBEDDING_TASK,
        )
        .order_by(
            Article.published_at.asc().nullslast(),
            Article.id.asc(),
        )
    )

    rows = session.execute(stmt).all()

    articles = []

    for row in rows:

        articles.append(
            {
                "id": int(row.id),
                "source_id": int(row.source_id),
                "title": row.title or "",
                "body": row.body or "",
                "image_url": row.image_url,
                "published_at": row.published_at,
                "scraped_at": row.scraped_at,
                "embedding": embedding_to_numpy(
                    row.embedding
                ),
            }
        )

    return articles


# =========================================================
# SEMANTIC CENTRALITY
# =========================================================

def calculate_centrality(
    articles,
):
    """
    Centrality = mean cosine similarity between one article
    and all other articles in the event.

    Embeddings are normalized, so matrix multiplication
    gives cosine similarity.
    """

    if len(articles) == 1:

        return {
            articles[0]["id"]: 1.0
        }

    matrix = np.stack(
        [
            article["embedding"]
            for article in articles
        ]
    )

    similarity_matrix = (
        matrix @ matrix.T
    )

    n = len(articles)

    scores = {}

    for index, article in enumerate(
        articles
    ):

        # Exclude similarity with itself.
        total_similarity = (
            similarity_matrix[index].sum()
            - 1.0
        )

        mean_similarity = (
            total_similarity
            / (n - 1)
        )

        scores[
            article["id"]
        ] = float(
            mean_similarity
        )

    return scores


# =========================================================
# SOURCE DIVERSITY
# =========================================================

def calculate_source_scores(
    articles,
):
    """
    Articles from sources that appear many times inside
    the same event receive less weight.

    Example:

        ABC:          10 articles
        Última Hora:   1 article

    The single Última Hora article should not be
    overwhelmed simply because ABC produced many URLs.
    """

    source_counts = Counter(
        article["source_id"]
        for article in articles
    )

    raw_scores = {}

    for article in articles:

        count = source_counts[
            article["source_id"]
        ]

        raw_scores[
            article["id"]
        ] = (
            1.0
            / count
        )

    max_score = max(
        raw_scores.values()
    )

    return {
        article_id:
            score / max_score

        for article_id, score
        in raw_scores.items()
    }


# =========================================================
# COMPLETENESS
# =========================================================

def calculate_completeness(
    article,
):
    """
    Simple article-quality proxy.

    Body length contributes most of the score.

    A usable title and image provide small bonuses.
    """

    body_length = len(
        article["body"].strip()
    )

    # Saturate at 4,000 characters.
    body_score = min(
        body_length / 4000,
        1.0,
    )

    title_score = (
        1.0
        if len(
            article["title"].strip()
        ) >= 20
        else 0.0
    )

    image_score = (
        1.0
        if article["image_url"]
        else 0.0
    )

    return (
        0.70 * body_score
        + 0.15 * title_score
        + 0.15 * image_score
    )


# =========================================================
# NORMALIZATION
# =========================================================

def minmax_normalize(
    values: dict[int, float],
):
    """
    Normalize values to [0, 1].

    If all articles have the same score, give them all 1.
    """

    if not values:
        return {}

    minimum = min(
        values.values()
    )

    maximum = max(
        values.values()
    )

    if np.isclose(
        minimum,
        maximum,
    ):

        return {
            key: 1.0
            for key in values
        }

    return {
        key:
            (
                value - minimum
            )
            /
            (
                maximum - minimum
            )

        for key, value
        in values.items()
    }


# =========================================================
# SELECT REPRESENTATIVE
# =========================================================

def select_representative(
    articles,
):
    if not articles:

        return None, []

    # -----------------------------------------------------
    # Singleton
    # -----------------------------------------------------

    if len(articles) == 1:

        article = articles[0]

        return (
            article["id"],
            [
                {
                    "article_id":
                        article["id"],

                    "centrality":
                        1.0,

                    "centrality_norm":
                        1.0,

                    "source_score":
                        1.0,

                    "completeness":
                        calculate_completeness(
                            article
                        ),

                    "final_score":
                        1.0,
                }
            ],
        )

    # -----------------------------------------------------
    # Centrality
    # -----------------------------------------------------

    centrality = (
        calculate_centrality(
            articles
        )
    )

    centrality_norm = (
        minmax_normalize(
            centrality
        )
    )

    # -----------------------------------------------------
    # Source diversity
    # -----------------------------------------------------

    source_scores = (
        calculate_source_scores(
            articles
        )
    )

    # -----------------------------------------------------
    # Score
    # -----------------------------------------------------

    scored = []

    for article in articles:

        article_id = article["id"]

        completeness = (
            calculate_completeness(
                article
            )
        )

        final_score = (
            CENTRALITY_WEIGHT
            * centrality_norm[
                article_id
            ]

            +

            SOURCE_DIVERSITY_WEIGHT
            * source_scores[
                article_id
            ]

            +

            COMPLETENESS_WEIGHT
            * completeness
        )

        scored.append(
            {
                "article_id":
                    article_id,

                "centrality":
                    centrality[
                        article_id
                    ],

                "centrality_norm":
                    centrality_norm[
                        article_id
                    ],

                "source_score":
                    source_scores[
                        article_id
                    ],

                "completeness":
                    completeness,

                "final_score":
                    final_score,
            }
        )

    scored.sort(
        key=lambda row: (
            row["final_score"],
            row["centrality"],
        ),
        reverse=True,
    )

    return (
        scored[0]["article_id"],
        scored,
    )


# =========================================================
# GET EVENTS
# =========================================================

def get_events_to_process(
    session,
    limit=None,
):

    stmt = (
        select(Event)
        .where(
            Event.representative_article_id.is_(None),
            Event.article_count > 1,
        )
        .order_by(
            Event.article_count.desc(),
            Event.id,
    )
)

    if limit is not None:

        stmt = stmt.limit(
            limit
        )

    return list(
        session.scalars(
            stmt
        ).all()
    )


# =========================================================
# MAIN
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Select a representative article "
            "for every event."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum number of events to process."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Calculate selections without "
            "saving them."
        ),
    )

    args = parser.parse_args()

    print("=" * 70)
    print("REPRESENTATIVE ARTICLE SELECTION")
    print("=" * 70)

    print(
        f"Centrality weight: "
        f"{CENTRALITY_WEIGHT}"
    )

    print(
        f"Source diversity weight: "
        f"{SOURCE_DIVERSITY_WEIGHT}"
    )

    print(
        f"Completeness weight: "
        f"{COMPLETENESS_WEIGHT}"
    )

    print(
        f"Dry run: "
        f"{args.dry_run}"
    )

    session = SessionLocal()

    try:

        events = get_events_to_process(
            session,
            limit=args.limit,
        )

        total = len(events)

        print()
        print(
            f"Events to process: "
            f"{total}"
        )

        if not events:

            print(
                "No events require representative "
                "article selection."
            )
            return

        processed = 0

        singleton_events = 0

        multi_article_events = 0

        missing_articles = 0

        for event in events:

            articles = (
                load_event_articles(
                    session,
                    event.id,
                )
            )

            if not articles:

                missing_articles += 1
                continue

            if len(articles) == 1:

                singleton_events += 1

            else:

                multi_article_events += 1

            (
                representative_id,
                scores,
            ) = select_representative(
                articles
            )

            if representative_id is None:

                missing_articles += 1
                continue

            if not args.dry_run:

                event.representative_article_id = (
                    representative_id
                )

            processed += 1

            # -------------------------------------------------
            # Useful diagnostics for larger events
            # -------------------------------------------------

            if (
                len(articles) >= 10
                and processed <= 100
            ):

                best = scores[0]

                print(
                    f"\nEvent {event.id} "
                    f"({len(articles)} articles)"
                )

                print(
                    f"Representative: "
                    f"{representative_id}"
                )

                print(
                    f"Centrality: "
                    f"{best['centrality']:.4f}"
                )

                print(
                    f"Source score: "
                    f"{best['source_score']:.4f}"
                )

                print(
                    f"Completeness: "
                    f"{best['completeness']:.4f}"
                )

                print(
                    f"Final score: "
                    f"{best['final_score']:.4f}"
                )

            # -------------------------------------------------
            # Commit checkpoint
            # -------------------------------------------------

            if (
                not args.dry_run
                and processed % COMMIT_EVERY == 0
            ):

                session.commit()

                print(
                    f"Processed "
                    f"{processed}/{total}"
                )

        if args.dry_run:

            session.rollback()

        else:

            session.commit()

        print()
        print("=" * 70)
        print("SELECTION COMPLETE")
        print("=" * 70)

        print(
            f"Processed: "
            f"{processed}"
        )

        print(
            f"Singleton events: "
            f"{singleton_events}"
        )

        print(
            f"Multi-article events: "
            f"{multi_article_events}"
        )

        print(
            f"Events without usable articles: "
            f"{missing_articles}"
        )

    except KeyboardInterrupt:

        session.rollback()

        print()
        print(
            "Interrupted. Current uncommitted "
            "changes rolled back."
        )

        print(
            "Previously committed selections "
            "remain saved."
        )

    except Exception:

        session.rollback()
        raise

    finally:

        session.close()


if __name__ == "__main__":
    main()
