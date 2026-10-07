from __future__ import annotations

import argparse
from collections import Counter

import torch
from sqlalchemy import func, select

from database.db import SessionLocal
from database.models import (
    Article,
    ArticleEmbedding,
    ArticleNERStatus,
    Event,
    EventArticle,
    EventContent,
)

# =========================================================
# EXISTING PIPELINE COMPONENTS
# =========================================================

# Adjust these two import paths ONLY if your actual files
# are not named embeddings.generate and entities.generate.
#
# Based on the files you sent me:
#   generate.py      = embeddings
#   generate(1).py   = NER
#
# Rename them in your project to something unambiguous:
#
#   embeddings/generate.py
#   entities/generate.py

from embeddings.generate import (
    MODEL_NAME as EMBEDDING_MODEL,
    TASK as EMBEDDING_TASK,
    DIMENSIONS,
    BATCH_SIZE,
    build_article_text,
    load_model as load_embedding_model,
)

from entities.generate import (
    MODEL_NAME as NER_MODEL,
    load_ner,
    process_article as process_ner_article,
)

from events.assign_events import (
    EVENT_BACKFILL_START,
    get_effective_time,
    load_matcher,
    process_article as assign_event_article,
)

from events.select_representative_articles import (
    load_event_articles as load_representative_articles,
    select_representative,
)

from events.build_event_context import (
    load_event_articles as load_context_articles,
    select_context_articles,
    build_context,
)

from events.generate_event_content import (
    OLLAMA_MODEL,
    MAX_CONTEXT_ARTICLES,
    build_llm_prompt,
    call_ollama,
    save_event_draft,
)


# =========================================================
# CONFIG
# =========================================================

DEFAULT_LIMIT = 100

NER_COMMIT_EVERY = 25


# =========================================================
# DISPLAY
# =========================================================

def print_header(title: str):

    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


# =========================================================
# NEW / INCOMPLETE ARTICLE COUNTS
# =========================================================

def count_missing_embeddings(
    session,
) -> int:

    embedded = (
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

    stmt = (
        select(
            func.count(Article.id)
        )
        .where(
            ~Article.id.in_(
                embedded
            )
        )
    )

    return int(
        session.scalar(stmt)
        or 0
    )


def count_missing_ner(
    session,
) -> int:

    embedded = (
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

    processed = (
        select(
            ArticleNERStatus.article_id
        )
        .where(
            ArticleNERStatus.model
            == NER_MODEL
        )
    )

    stmt = (
        select(
            func.count(Article.id)
        )
        .where(
            Article.id.in_(
                embedded
            ),
            ~Article.id.in_(
                processed
            ),
        )
    )

    return int(
        session.scalar(stmt)
        or 0
    )


def count_unassigned(
    session,
) -> int:

    embedded = (
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

    ner_done = (
        select(
            ArticleNERStatus.article_id
        )
        .where(
            ArticleNERStatus.model
            == NER_MODEL
        )
    )

    assigned = (
        select(
            EventArticle.article_id
        )
    )

    effective_time = func.coalesce(
        Article.published_at,
        Article.scraped_at,
    )

    stmt = (
        select(
            func.count(Article.id)
        )
        .where(
            Article.id.in_(embedded),
            Article.id.in_(ner_done),
            ~Article.id.in_(assigned),
            effective_time
            >= EVENT_BACKFILL_START,
        )
    )

    return int(
        session.scalar(stmt)
        or 0
    )


# =========================================================
# ARTICLE SELECTION
# =========================================================

def get_articles_missing_embeddings(
    session,
    limit: int,
):

    embedded = (
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

    stmt = (
        select(Article)
        .where(
            ~Article.id.in_(
                embedded
            )
        )
        .order_by(
            Article.published_at.asc().nullslast(),
            Article.id.asc(),
        )
        .limit(limit)
    )

    return list(
        session.scalars(stmt).all()
    )


def get_articles_missing_ner(
    session,
    limit: int,
):

    embedded = (
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

    processed = (
        select(
            ArticleNERStatus.article_id
        )
        .where(
            ArticleNERStatus.model
            == NER_MODEL
        )
    )

    stmt = (
        select(Article)
        .where(
            Article.id.in_(embedded),
            ~Article.id.in_(processed),
        )
        .order_by(
            Article.id.asc()
        )
        .limit(limit)
    )

    return list(
        session.scalars(stmt).all()
    )


def get_articles_for_event_assignment(
    session,
    limit: int,
):

    embedded = (
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

    ner_done = (
        select(
            ArticleNERStatus.article_id
        )
        .where(
            ArticleNERStatus.model
            == NER_MODEL
        )
    )

    assigned = (
        select(
            EventArticle.article_id
        )
    )

    effective_time = func.coalesce(
        Article.published_at,
        Article.scraped_at,
    )

    stmt = (
        select(Article)
        .where(
            Article.id.in_(embedded),
            Article.id.in_(ner_done),
            ~Article.id.in_(assigned),
            effective_time
            >= EVENT_BACKFILL_START,
        )
        .order_by(
            effective_time.asc(),
            Article.id.asc(),
        )
        .limit(limit)
    )

    return list(
        session.scalars(stmt).all()
    )


# =========================================================
# EMBEDDING STAGE
# =========================================================

def run_embedding_stage(
    session,
    model,
    limit: int,
):

    print_header(
        "STAGE 1 — EMBEDDINGS"
    )

    articles = (
        get_articles_missing_embeddings(
            session,
            limit,
        )
    )

    if not articles:

        print(
            "No articles require embeddings."
        )

        return 0

    print(
        f"Articles to embed: "
        f"{len(articles)}"
    )

    texts = [
        build_article_text(article)
        for article in articles
    ]

    with torch.inference_mode():

        embeddings = model.encode(
            texts,
            task=EMBEDDING_TASK,
            batch_size=BATCH_SIZE,
            normalize_embeddings=True,
            show_progress_bar=True,
            convert_to_numpy=True,
        )

    if embeddings.shape[1] != DIMENSIONS:

        raise RuntimeError(
            f"Expected {DIMENSIONS} dimensions, "
            f"got {embeddings.shape[1]}."
        )

    for article, embedding in zip(
        articles,
        embeddings,
    ):

        row = ArticleEmbedding(
            article_id=article.id,
            model=EMBEDDING_MODEL,
            task=EMBEDDING_TASK,
            dimensions=DIMENSIONS,
            embedding=embedding.tolist(),
        )

        session.add(row)

    session.commit()

    saved = len(articles)

    print(
        f"Embeddings saved: {saved}"
    )

    del embeddings
    del texts

    torch.cuda.empty_cache()

    return saved


# =========================================================
# NER STAGE
# =========================================================

def run_ner_stage(
    session,
    ner,
    limit: int,
):

    print_header(
        "STAGE 2 — NER"
    )

    articles = (
        get_articles_missing_ner(
            session,
            limit,
        )
    )

    if not articles:

        print(
            "No articles require NER."
        )

        return {
            "processed": 0,
            "entities": 0,
            "zero_entities": 0,
        }

    print(
        f"Articles to process: "
        f"{len(articles)}"
    )

    processed = 0
    entities = 0
    zero_entities = 0

    for article in articles:

        entity_count = (
            process_ner_article(
                session,
                ner,
                article,
            )
        )

        processed += 1
        entities += entity_count

        if entity_count == 0:
            zero_entities += 1

        if (
            processed
            % NER_COMMIT_EVERY
            == 0
        ):

            session.commit()

            print(
                f"[{processed}/"
                f"{len(articles)}] "
                f"entities={entities}"
            )

    session.commit()

    print(
        f"NER processed: {processed}"
    )

    print(
        f"Entities saved: {entities}"
    )

    print(
        f"Zero-entity articles: "
        f"{zero_entities}"
    )

    return {
        "processed": processed,
        "entities": entities,
        "zero_entities": zero_entities,
    }


# =========================================================
# EVENT ASSIGNMENT STAGE
# =========================================================

def run_event_stage(
    session,
    matcher,
    limit: int,
):

    print_header(
        "STAGE 3 — EVENT ASSIGNMENT"
    )

    articles = (
        get_articles_for_event_assignment(
            session,
            limit,
        )
    )

    if not articles:

        print(
            "No articles require event assignment."
        )

        return {
            "processed": 0,
            "new_events": 0,
            "existing_events": 0,
            "skipped": 0,
            "affected_event_ids": set(),
        }

    print(
        f"Articles to assign: "
        f"{len(articles)}"
    )

    new_events = 0
    existing_events = 0
    skipped = 0

    affected_event_ids = set()

    for index, article in enumerate(
        articles,
        start=1,
    ):

        result = assign_event_article(
            session,
            matcher,
            article,
            dry_run=False,
        )

        decision = result[
            "decision"
        ]

        event_id = result.get(
            "event_id"
        )

        if event_id is not None:

            affected_event_ids.add(
                int(event_id)
            )

        if decision == "new_event":

            new_events += 1

        elif decision == "existing_event":

            existing_events += 1

        else:

            skipped += 1

        # -------------------------------------------------
        # CRITICAL:
        #
        # SessionLocal uses autoflush=False.
        #
        # Even though assign_events.py should now flush
        # assignments itself, keeping this here makes the
        # orchestration boundary explicit and safe.
        # -------------------------------------------------

        session.flush()

        if index % 25 == 0:

            session.commit()

            print(
                f"[{index}/"
                f"{len(articles)}] "
                f"new={new_events} "
                f"existing={existing_events}"
            )

    session.commit()

    print(
        f"New events: {new_events}"
    )

    print(
        "Assigned to existing events: "
        f"{existing_events}"
    )

    print(
        "Affected events: "
        f"{len(affected_event_ids)}"
    )

    return {
        "processed": len(articles),
        "new_events": new_events,
        "existing_events": existing_events,
        "skipped": skipped,
        "affected_event_ids":
            affected_event_ids,
    }


# =========================================================
# REPRESENTATIVE ARTICLE STAGE
# =========================================================

def update_representatives(
    session,
    event_ids: set[int],
):

    print_header(
        "STAGE 4 — REPRESENTATIVE ARTICLES"
    )

    if not event_ids:

        print(
            "No affected events."
        )

        return {
            "updated": 0,
            "multi_article_event_ids": set(),
        }

    updated = 0
    multi_article_event_ids = set()

    for event_id in sorted(
        event_ids
    ):

        event = session.get(
            Event,
            event_id,
        )

        if event is None:
            continue

        articles = (
            load_representative_articles(
                session,
                event.id,
            )
        )

        if not articles:
            continue

        # ---------------------------------------------
        # Singleton
        # ---------------------------------------------

        if len(articles) == 1:

            representative_id = (
                articles[0]["id"]
            )

        # ---------------------------------------------
        # Multi-article event
        # ---------------------------------------------

        else:

            multi_article_event_ids.add(
                event.id
            )

            (
                representative_id,
                _,
            ) = select_representative(
                articles
            )

        if representative_id is None:
            continue

        if (
            event.representative_article_id
            != representative_id
        ):

            event.representative_article_id = (
                representative_id
            )

            updated += 1

    session.commit()

    print(
        f"Representatives updated: "
        f"{updated}"
    )

    print(
        f"Multi-article affected events: "
        f"{len(multi_article_event_ids)}"
    )

    return {
        "updated": updated,
        "multi_article_event_ids":
            multi_article_event_ids,
    }


# =========================================================
# DRAFT GENERATION STAGE
# =========================================================

def get_existing_content_statuses(
    session,
    event_ids: set[int],
):

    if not event_ids:

        return {}

    stmt = (
        select(
            EventContent.event_id,
            EventContent.status,
        )
        .where(
            EventContent.event_id.in_(
                event_ids
            )
        )
    )

    rows = session.execute(
        stmt
    ).all()

    return {
        int(event_id): status
        for event_id, status
        in rows
    }


def generate_new_drafts(
    session,
    event_ids: set[int],
):

    print_header(
        "STAGE 5 — EVENT DRAFTS"
    )

    if not event_ids:

        print(
            "No multi-article events "
            "require consideration."
        )

        return {
            "generated": 0,
            "failed": 0,
            "protected": Counter(),
        }

    content_statuses = (
        get_existing_content_statuses(
            session,
            event_ids,
        )
    )

    generated = 0
    failed = 0

    protected = Counter()

    for event_id in sorted(
        event_ids
    ):

        event = session.get(
            Event,
            event_id,
        )

        if event is None:
            continue

        # ---------------------------------------------
        # Protect existing editorial content.
        # ---------------------------------------------

        existing_status = (
            content_statuses.get(
                event.id
            )
        )

        if existing_status is not None:

            protected[
                existing_status
            ] += 1

            print(
                f"Event {event.id}: "
                f"existing content "
                f"({existing_status}) "
                f"left unchanged."
            )

            continue

        if event.article_count <= 1:

            continue

        if (
            event.representative_article_id
            is None
        ):

            print(
                f"Event {event.id}: "
                f"no representative article."
            )

            failed += 1
            continue

        try:

            articles = (
                load_context_articles(
                    session,
                    event.id,
                )
            )

            if not articles:

                raise RuntimeError(
                    "No usable articles."
                )

            selected = (
                select_context_articles(
                    articles,
                    event.representative_article_id,
                    max_articles=(
                        MAX_CONTEXT_ARTICLES
                    ),
                )
            )

            if not selected:

                raise RuntimeError(
                    "No context articles selected."
                )

            context = build_context(
                event,
                articles,
                selected,
            )

            prompt = build_llm_prompt(
                context
            )

            print(
                f"Generating event "
                f"{event.id} with "
                f"{len(selected)} articles..."
            )

            result = call_ollama(
                prompt
            )

            save_event_draft(
                session=session,
                event=event,
                context=context,
                result=result,
            )

            generated += 1

            print(
                f"  Draft saved: "
                f"{result['title']}"
            )

        except Exception as exc:

            session.rollback()

            failed += 1

            print(
                f"  ERROR event "
                f"{event.id}: {exc}"
            )

    print()
    print(
        f"Drafts generated: {generated}"
    )

    print(
        f"Draft failures: {failed}"
    )

    if protected:

        print(
            "Existing content protected:"
        )

        for status, count in (
            protected.items()
        ):

            print(
                f"  {status}: {count}"
            )

    return {
        "generated": generated,
        "failed": failed,
        "protected": protected,
    }


# =========================================================
# MAIN PIPELINE
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Process new Paraguay News articles "
            "through the production pipeline."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=(
            "Maximum number of articles to "
            "process per stage. "
            f"Default: {DEFAULT_LIMIT}."
        ),
    )

    parser.add_argument(
        "--skip-drafts",
        action="store_true",
        help=(
            "Run article processing but do not "
            "generate Qwen drafts."
        ),
    )

    args = parser.parse_args()

    print_header(
        "PARAGUAY NEWS — PRODUCTION PIPELINE"
    )

    print(
        f"Article limit per stage: "
        f"{args.limit}"
    )

    print(
        f"Generate drafts: "
        f"{not args.skip_drafts}"
    )

    # =====================================================
    # PRE-FLIGHT
    # =====================================================

    session = SessionLocal()

    try:

        missing_embeddings = (
            count_missing_embeddings(
                session
            )
        )

        missing_ner = (
            count_missing_ner(
                session
            )
        )

        unassigned = (
            count_unassigned(
                session
            )
        )

    finally:

        session.close()

    print()
    print(
        "Current backlog:"
    )

    print(
        f"  Missing embeddings: "
        f"{missing_embeddings}"
    )

    print(
        f"  Missing NER: "
        f"{missing_ner}"
    )

    print(
        f"  Unassigned: "
        f"{unassigned}"
    )

    # =====================================================
    # NOTHING TO DO
    # =====================================================

    if (
        missing_embeddings == 0
        and missing_ner == 0
        and unassigned == 0
    ):

        print()
        print(
            "Nothing to process."
        )

        return

    # =====================================================
    # LOAD MODELS ONLY WHEN NEEDED
    # =====================================================

    embedding_model = None
    ner = None
    matcher = None

    # =====================================================
    # DATABASE SESSION
    # =====================================================

    session = SessionLocal()

    try:

        # =================================================
        # 1. EMBEDDINGS
        # =================================================

        if missing_embeddings > 0:

            embedding_model = (
                load_embedding_model()
            )

            embedding_count = (
                run_embedding_stage(
                    session,
                    embedding_model,
                    args.limit,
                )
            )

            del embedding_model
            embedding_model = None

            torch.cuda.empty_cache()

        else:

            print_header(
                "STAGE 1 — EMBEDDINGS"
            )

            print(
                "No articles require embeddings."
            )

            embedding_count = 0

        # =================================================
        # 2. NER
        # =================================================

        current_missing_ner = (
            count_missing_ner(
                session
            )
        )

        if current_missing_ner > 0:

            ner = load_ner()

            ner_result = (
                run_ner_stage(
                    session,
                    ner,
                    args.limit,
                )
            )

            del ner
            ner = None

            torch.cuda.empty_cache()

        else:

            print_header(
                "STAGE 2 — NER"
            )

            print(
                "No articles require NER."
            )

            ner_result = {
                "processed": 0,
                "entities": 0,
                "zero_entities": 0,
            }

        # =================================================
        # 3. EVENT ASSIGNMENT
        # =================================================

        current_unassigned = (
            count_unassigned(
                session
            )
        )

        if current_unassigned > 0:

            matcher = load_matcher()

            event_result = (
                run_event_stage(
                    session,
                    matcher,
                    args.limit,
                )
            )

        else:

            print_header(
                "STAGE 3 — EVENT ASSIGNMENT"
            )

            print(
                "No articles require "
                "event assignment."
            )

            event_result = {
                "processed": 0,
                "new_events": 0,
                "existing_events": 0,
                "skipped": 0,
                "affected_event_ids":
                    set(),
            }

        # =================================================
        # 4. REPRESENTATIVES
        # =================================================

        representative_result = (
            update_representatives(
                session,
                event_result[
                    "affected_event_ids"
                ],
            )
        )

        # =================================================
        # 5. DRAFTS
        # =================================================

        if args.skip_drafts:

            print_header(
                "STAGE 5 — EVENT DRAFTS"
            )

            print(
                "Draft generation skipped."
            )

            draft_result = {
                "generated": 0,
                "failed": 0,
                "protected": Counter(),
            }

        else:

            draft_result = (
                generate_new_drafts(
                    session,
                    representative_result[
                        "multi_article_event_ids"
                    ],
                )
            )

        # =================================================
        # SUMMARY
        # =================================================

        print_header(
            "PIPELINE COMPLETE"
        )

        print(
            f"Embeddings created: "
            f"{embedding_count}"
        )

        print(
            f"NER processed: "
            f"{ner_result['processed']}"
        )

        print(
            f"Event assignments: "
            f"{event_result['processed']}"
        )

        print(
            f"  New events: "
            f"{event_result['new_events']}"
        )

        print(
            f"  Existing events: "
            f"{event_result['existing_events']}"
        )

        print(
            f"Representatives updated: "
            f"{representative_result['updated']}"
        )

        print(
            f"Drafts generated: "
            f"{draft_result['generated']}"
        )

        print()
        print(
            "New drafts are now available "
            "in the Streamlit review interface."
        )

    except KeyboardInterrupt:

        session.rollback()

        print()
        print(
            "Pipeline interrupted."
        )

        print(
            "Committed stages remain saved. "
            "Run the pipeline again to resume."
        )

    except Exception:

        session.rollback()
        raise

    finally:

        session.close()


if __name__ == "__main__":
    main()
