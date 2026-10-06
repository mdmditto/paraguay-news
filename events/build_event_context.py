from __future__ import annotations

import argparse
import json
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

MAX_CONTEXT_ARTICLES = 6

# Avoid selecting articles that are essentially duplicate
# versions of something already selected.
DUPLICATE_SIMILARITY_THRESHOLD = 0.97

OUTPUT_DIR = Path("events/context_samples")


# =========================================================
# HELPERS
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


def effective_time(article):
    return (
        article["published_at"]
        or article["scraped_at"]
    )


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
            Source.name.label("source_name"),
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
            Source,
            Source.id == Article.source_id,
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
                "source_name": row.source_name,
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
# CENTRALITY
# =========================================================

def calculate_centrality(
    articles,
) -> dict[int, float]:

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

    centrality = {}

    for index, article in enumerate(
        articles
    ):
        total_similarity = (
            similarity_matrix[index].sum()
            - similarity_matrix[index, index]
        )

        centrality[
            article["id"]
        ] = float(
            total_similarity
            / (n - 1)
        )

    return centrality


# =========================================================
# DUPLICATE CHECK
# =========================================================

def cosine_similarity(
    a: np.ndarray,
    b: np.ndarray,
) -> float:

    return float(
        np.dot(a, b)
    )


def is_near_duplicate(
    candidate,
    selected,
) -> bool:

    for existing in selected:

        similarity = cosine_similarity(
            candidate["embedding"],
            existing["embedding"],
        )

        if (
            similarity
            >= DUPLICATE_SIMILARITY_THRESHOLD
        ):
            return True

    return False


# =========================================================
# SUPPORT ARTICLE SELECTION
# =========================================================

def select_context_articles(
    articles,
    representative_article_id: int,
    max_articles: int = MAX_CONTEXT_ARTICLES,
):
    """
    Always include the representative article.

    Then greedily select supporting articles while
    encouraging:

      1. semantic centrality
      2. new sources
      3. avoidance of near-duplicates
    """

    if not articles:
        return []

    article_by_id = {
        article["id"]: article
        for article in articles
    }

    representative = article_by_id.get(
        representative_article_id
    )

    if representative is None:
        raise ValueError(
            f"Representative article "
            f"{representative_article_id} "
            f"not found in event."
        )

    if len(articles) <= 1:
        return [representative]

    centrality = calculate_centrality(
        articles
    )

    # Rank candidates from most central to least central.
    candidates = sorted(
        [
            article
            for article in articles
            if article["id"]
            != representative_article_id
        ],
        key=lambda article: (
            centrality[article["id"]],
            len(article["body"]),
        ),
        reverse=True,
    )

    selected = [
        representative
    ]

    selected_sources = {
        representative["source_id"]
    }

    # -----------------------------------------------------
    # PASS 1:
    # Prefer different sources.
    # -----------------------------------------------------

    for candidate in candidates:

        if len(selected) >= max_articles:
            break

        if (
            candidate["source_id"]
            in selected_sources
        ):
            continue

        if is_near_duplicate(
            candidate,
            selected,
        ):
            continue

        selected.append(
            candidate
        )

        selected_sources.add(
            candidate["source_id"]
        )

    # -----------------------------------------------------
    # PASS 2:
    # If there are still empty slots, allow repeated
    # sources, but continue avoiding near duplicates.
    # -----------------------------------------------------

    if len(selected) < max_articles:

        selected_ids = {
            article["id"]
            for article in selected
        }

        for candidate in candidates:

            if len(selected) >= max_articles:
                break

            if candidate["id"] in selected_ids:
                continue

            if is_near_duplicate(
                candidate,
                selected,
            ):
                continue

            selected.append(
                candidate
            )

            selected_ids.add(
                candidate["id"]
            )

    return selected


# =========================================================
# SERIALIZATION
# =========================================================

def article_to_json(
    article,
    representative_id: int,
    centrality: dict[int, float],
):
    timestamp = effective_time(
        article
    )

    return {
        "article_id": article["id"],

        "is_representative": (
            article["id"]
            == representative_id
        ),

        "source": article["source_name"],

        "published_at": (
            timestamp.isoformat()
            if timestamp
            else None
        ),

        "title": article["title"],

        "body": article["body"],

        "image_url": article["image_url"],

        "centrality": round(
            centrality.get(
                article["id"],
                0.0,
            ),
            6,
        ),
    }


def build_context(
    event,
    articles,
    selected,
):
    centrality = calculate_centrality(
        articles
    )

    source_count = len(
        {
            article["source_id"]
            for article in articles
        }
    )

    selected_source_count = len(
        {
            article["source_id"]
            for article in selected
        }
    )

    return {
        "event_id": event.id,

        "current_title": event.title,

        "article_count": len(
            articles
        ),

        "source_count": source_count,

        "context_article_count": len(
            selected
        ),

        "context_source_count":
            selected_source_count,

        "representative_article_id":
            event.representative_article_id,

        "articles": [
            article_to_json(
                article,
                event.representative_article_id,
                centrality,
            )
            for article in selected
        ],
    }


# =========================================================
# DISPLAY
# =========================================================

def print_context_summary(
    context,
):
    print()
    print("=" * 80)

    print(
        f"EVENT {context['event_id']}"
    )

    print(
        f"Event articles: "
        f"{context['article_count']}"
    )

    print(
        f"Event sources: "
        f"{context['source_count']}"
    )

    print(
        f"Selected articles: "
        f"{context['context_article_count']}"
    )

    print(
        f"Selected sources: "
        f"{context['context_source_count']}"
    )

    print()

    for index, article in enumerate(
        context["articles"],
        start=1,
    ):

        marker = (
            " [REPRESENTATIVE]"
            if article[
                "is_representative"
            ]
            else ""
        )

        print(
            f"{index}. "
            f"{article['source']}"
            f"{marker}"
        )

        print(
            f"   centrality="
            f"{article['centrality']:.4f}"
        )

        print(
            f"   {article['title']}"
        )


# =========================================================
# GET EVENTS
# =========================================================

def get_events(
    session,
    limit=None,
    event_id=None,
):
    stmt = (
        select(Event)
        .where(
            Event.article_count > 1,
            Event.representative_article_id.is_not(
                None
            ),
        )
    )

    if event_id is not None:

        stmt = stmt.where(
            Event.id == event_id
        )

    else:

        stmt = stmt.order_by(
            Event.article_count.desc(),
            Event.id,
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
            "Build compact, diverse article "
            "contexts for news events."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help=(
            "Number of events to process. "
            "Default: 10."
        ),
    )

    parser.add_argument(
        "--event-id",
        type=int,
        default=None,
        help=(
            "Build context for one specific "
            "event."
        ),
    )

    parser.add_argument(
        "--max-articles",
        type=int,
        default=MAX_CONTEXT_ARTICLES,
        help=(
            "Maximum number of articles "
            "per event context."
        ),
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help=(
            "Save contexts as JSON files."
        ),
    )

    args = parser.parse_args()

    session = SessionLocal()

    try:

        events = get_events(
            session,
            limit=args.limit,
            event_id=args.event_id,
        )

        print("=" * 80)
        print("EVENT CONTEXT BUILDER")
        print("=" * 80)

        print(
            f"Events selected: "
            f"{len(events)}"
        )

        print(
            f"Maximum articles per context: "
            f"{args.max_articles}"
        )

        print(
            f"Duplicate threshold: "
            f"{DUPLICATE_SIMILARITY_THRESHOLD}"
        )

        if args.save:
            OUTPUT_DIR.mkdir(
                parents=True,
                exist_ok=True,
            )

        for event in events:

            articles = load_event_articles(
                session,
                event.id,
            )

            if not articles:
                print(
                    f"Event {event.id}: "
                    f"no articles found."
                )
                continue

            selected = select_context_articles(
                articles,
                event.representative_article_id,
                max_articles=args.max_articles,
            )

            context = build_context(
                event,
                articles,
                selected,
            )

            print_context_summary(
                context
            )

            if args.save:

                output_path = (
                    OUTPUT_DIR
                    / f"event_{event.id}.json"
                )

                with output_path.open(
                    "w",
                    encoding="utf-8",
                ) as file:

                    json.dump(
                        context,
                        file,
                        ensure_ascii=False,
                        indent=2,
                    )

        print()
        print("=" * 80)
        print("DONE")
        print("=" * 80)

    finally:
        session.close()


if __name__ == "__main__":
    main()
