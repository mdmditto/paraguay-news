from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import torch
from sqlalchemy import func, select

from database.db import SessionLocal
from database.models import (
    Article, ArticleEmbedding, ArticleNERStatus, Source,
    Event, EventArticle, EventContent,
)
from embeddings.generate import (
    MODEL_NAME as EMBEDDING_MODEL, TASK as EMBEDDING_TASK,
    DIMENSIONS, BATCH_SIZE, build_article_text,
    load_model as load_embedding_model, MAX_EMBEDDING_TOKENS,
)
from entities.generate import (
    MODEL_NAME as NER_MODEL, load_ner,
    process_article as process_ner_article,
)
from events.assign_events import (
    EVENT_BACKFILL_START, load_matcher,
    process_article as assign_event_article,
)
from events.select_representative_articles import (
    load_event_articles as load_representative_articles,
    select_representative,
)
from events.build_event_context import (
    load_event_articles as load_context_articles,
    select_context_articles, build_context,
)
from events.generate_event_content import (
    MAX_CONTEXT_ARTICLES, build_llm_prompt,
    call_ollama, save_event_draft,
)

DEFAULT_LIMIT = 100
NER_COMMIT_EVERY = 25
EVENT_COMMIT_EVERY = 25

# Temporarily exclude this outlet from ALL new processing queues.
# Existing database rows and event assignments are never deleted.
# Remove its name from the set to re-enable processing.
EXCLUDED_SOURCES = {"Más Encarnación"}
LOCAL_TIMEZONE = ZoneInfo("America/Asuncion")


def print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def embedded_ids_query():
    return select(ArticleEmbedding.article_id).where(
        ArticleEmbedding.model == EMBEDDING_MODEL,
        ArticleEmbedding.task == EMBEDDING_TASK,
    )


def ner_ids_query():
    return select(ArticleNERStatus.article_id).where(
        ArticleNERStatus.model == NER_MODEL,
    )


def assigned_ids_query():
    return select(EventArticle.article_id)


def eligible_source_filter():
    """Reusable SQL expression for excluding sources by exact name."""
    if not EXCLUDED_SOURCES:
        return True
    return ~Article.source_id.in_(
        select(Source.id).where(Source.name.in_(EXCLUDED_SOURCES))
    )


def historical_filter(before):
    """Filter by scrape date; --before is exclusive local midnight."""
    return True if before is None else Article.scraped_at < before


def effective_time_expression():
    return func.coalesce(Article.published_at, Article.scraped_at)


def count_missing_embeddings(session, before=None):
    return int(session.scalar(select(func.count(Article.id)).where(
        eligible_source_filter(), historical_filter(before), ~Article.id.in_(embedded_ids_query()),
    )) or 0)


def count_missing_ner(session, before=None):
    return int(session.scalar(select(func.count(Article.id)).where(
        eligible_source_filter(), historical_filter(before), Article.id.in_(embedded_ids_query()),
        ~Article.id.in_(ner_ids_query()),
    )) or 0)


def count_unassigned(session, before=None):
    return int(session.scalar(select(func.count(Article.id)).where(
        eligible_source_filter(), historical_filter(before), Article.id.in_(embedded_ids_query()),
        Article.id.in_(ner_ids_query()),
        ~Article.id.in_(assigned_ids_query()),
        effective_time_expression() >= EVENT_BACKFILL_START,
    )) or 0)


def get_new_article_cohort(session, limit, before=None):
    stmt = select(Article).where(
        eligible_source_filter(), historical_filter(before),
        ~Article.id.in_(embedded_ids_query()),
    ).order_by(Article.scraped_at.desc().nullslast(), Article.id.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def get_missing_ner_catchup(session, limit, exclude_ids=None, before=None):
    stmt = select(Article).where(
        eligible_source_filter(), historical_filter(before), Article.id.in_(embedded_ids_query()),
        ~Article.id.in_(ner_ids_query()),
    )
    if exclude_ids:
        stmt = stmt.where(~Article.id.in_(exclude_ids))
    return list(session.scalars(stmt.order_by(
        Article.scraped_at.desc().nullslast(), Article.id.desc()
    ).limit(limit)).all())


def get_event_catchup_articles(session, limit, exclude_ids=None, before=None, chronological=False):
    stmt = select(Article).where(
        eligible_source_filter(), historical_filter(before), Article.id.in_(embedded_ids_query()),
        Article.id.in_(ner_ids_query()),
        ~Article.id.in_(assigned_ids_query()),
        effective_time_expression() >= EVENT_BACKFILL_START,
    )
    if exclude_ids:
        stmt = stmt.where(~Article.id.in_(exclude_ids))
    if chronological:
        # Select the oldest eligible unassigned articles across the entire backlog,
        # not merely sort a newest-first batch after selecting it.
        stmt = stmt.order_by(effective_time_expression().asc(), Article.id.asc())
    else:
        stmt = stmt.order_by(Article.scraped_at.desc().nullslast(), Article.id.desc())
    return list(session.scalars(stmt.limit(limit)).all())


def get_embedded_ids(session, article_ids):
    if not article_ids:
        return set()
    return set(session.scalars(select(ArticleEmbedding.article_id).where(
        ArticleEmbedding.article_id.in_(article_ids),
        ArticleEmbedding.model == EMBEDDING_MODEL,
        ArticleEmbedding.task == EMBEDDING_TASK,
    )).all())


def get_ner_done_ids(session, article_ids):
    if not article_ids:
        return set()
    return set(session.scalars(select(ArticleNERStatus.article_id).where(
        ArticleNERStatus.article_id.in_(article_ids),
        ArticleNERStatus.model == NER_MODEL,
    )).all())


def get_assigned_ids(session, article_ids):
    if not article_ids:
        return set()
    return set(session.scalars(select(EventArticle.article_id).where(
        EventArticle.article_id.in_(article_ids),
    )).all())


def safe_cuda_cleanup():
    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except (RuntimeError, torch.AcceleratorError) as exc:
            print(f"CUDA cleanup warning: {exc}")


def run_embedding_stage(session, model, articles):
    print_header("STAGE 1 — EMBEDDINGS")

    if not articles:
        print("No articles require embeddings.")
        return 0

    print(f"Articles to embed: {len(articles)}")

    # Build article text with token-aware truncation.
    texts = [
        build_article_text(
            article,
            tokenizer=model.tokenizer,
            max_tokens=MAX_EMBEDDING_TOKENS,
        )
        for article in articles
    ]

    with torch.inference_mode():
        vectors = model.encode(
            texts,
            task=EMBEDDING_TASK,
            batch_size=BATCH_SIZE,
            normalize_embeddings=True,
            show_progress_bar=True,
            convert_to_numpy=True,
        )

    if vectors.shape != (len(articles), DIMENSIONS):
        raise RuntimeError(
            f"Unexpected embedding shape: {vectors.shape}"
        )

    for article, vector in zip(articles, vectors):
        session.add(
            ArticleEmbedding(
                article_id=article.id,
                model=EMBEDDING_MODEL,
                task=EMBEDDING_TASK,
                dimensions=DIMENSIONS,
                embedding=vector.tolist(),
            )
        )

    session.commit()

    print(f"Embeddings saved: {len(articles)}")

    del vectors, texts
    safe_cuda_cleanup()

    return len(articles)


def run_ner_stage(session, ner, articles):
    print_header("STAGE 2 — NER")
    result = {"processed": 0, "entities": 0, "zero_entities": 0}
    if not articles:
        print("No articles require NER.")
        return result
    print(f"Articles to process: {len(articles)}")
    for article in articles:
        count = process_ner_article(session, ner, article)
        result["processed"] += 1
        result["entities"] += count
        result["zero_entities"] += (count == 0)
        if result["processed"] % NER_COMMIT_EVERY == 0:
            session.commit()
            print(f"[{result['processed']}/{len(articles)}] entities={result['entities']}")
    session.commit()
    print(f"NER processed: {result['processed']}")
    print(f"Entities saved: {result['entities']}")
    print(f"Zero-entity articles: {result['zero_entities']}")
    return result


def run_event_stage(session, matcher, articles):
    print_header("STAGE 3 — EVENT ASSIGNMENT")
    result = {"processed": 0, "new_events": 0, "existing_events": 0,
              "skipped": 0, "affected_event_ids": set()}
    if not articles:
        print("No articles require event assignment.")
        return result
    # Choose recent articles first, then process that chosen batch chronologically.
    articles = sorted(articles, key=lambda a: (
        a.published_at or a.scraped_at, a.id
    ))
    print(f"Articles to assign: {len(articles)}")
    for index, article in enumerate(articles, 1):
        decision_result = assign_event_article(
            session, matcher, article, dry_run=False,
        )
        decision = decision_result["decision"]
        event_id = decision_result.get("event_id")
        if event_id is not None:
            result["affected_event_ids"].add(int(event_id))
        if decision == "new_event":
            result["new_events"] += 1
        elif decision == "existing_event":
            result["existing_events"] += 1
        else:
            result["skipped"] += 1
        result["processed"] += 1
        # SessionLocal is configured with autoflush=False.
        session.flush()
        if index % EVENT_COMMIT_EVERY == 0:
            session.commit()
            print(f"[{index}/{len(articles)}] new={result['new_events']} existing={result['existing_events']}")
    session.commit()
    print(f"New events: {result['new_events']}")
    print(f"Assigned to existing events: {result['existing_events']}")
    print(f"Affected events: {len(result['affected_event_ids'])}")
    return result


def update_representatives(session, event_ids):
    print_header("STAGE 4 — REPRESENTATIVE ARTICLES")
    result = {"updated": 0, "multi_article_event_ids": set()}
    if not event_ids:
        print("No affected events.")
        return result
    for event_id in sorted(event_ids):
        event = session.get(Event, event_id)
        if event is None:
            continue
        articles = load_representative_articles(session, event.id)
        if not articles:
            continue
        if len(articles) == 1:
            representative_id = articles[0]["id"]
        else:
            result["multi_article_event_ids"].add(event.id)
            representative_id, _ = select_representative(articles)
        if representative_id is None:
            continue
        if event.representative_article_id != representative_id:
            event.representative_article_id = representative_id
            result["updated"] += 1
    session.commit()
    print(f"Representatives updated: {result['updated']}")
    print(f"Multi-article affected events: {len(result['multi_article_event_ids'])}")
    return result


def get_existing_content_statuses(session, event_ids):
    if not event_ids:
        return {}
    return dict(session.execute(select(
        EventContent.event_id, EventContent.status
    ).where(EventContent.event_id.in_(event_ids))).all())


def generate_new_drafts(session, event_ids):
    print_header("STAGE 5 — EVENT DRAFTS")
    result = {"generated": 0, "failed": 0, "protected": Counter()}
    if not event_ids:
        print("No multi-article events require consideration.")
        return result
    statuses = get_existing_content_statuses(session, event_ids)
    for event_id in sorted(event_ids):
        event = session.get(Event, event_id)
        if event is None:
            continue
        existing_status = statuses.get(event.id)
        if existing_status is not None:
            result["protected"][existing_status] += 1
            print(f"Event {event.id}: existing content ({existing_status}) left unchanged.")
            continue
        if event.article_count <= 1:
            continue
        if event.representative_article_id is None:
            print(f"Event {event.id}: no representative article.")
            result["failed"] += 1
            continue
        try:
            articles = load_context_articles(session, event.id)
            if not articles:
                raise RuntimeError("No usable articles.")
            selected = select_context_articles(
                articles, event.representative_article_id,
                max_articles=MAX_CONTEXT_ARTICLES,
            )
            if not selected:
                raise RuntimeError("No context articles selected.")
            context = build_context(event, articles, selected)
            prompt = build_llm_prompt(context)
            print(f"Generating event {event.id} with {len(selected)} articles...")
            llm_result = call_ollama(prompt)
            save_event_draft(session=session, event=event, context=context,
                             result=llm_result)
            result["generated"] += 1
            print(f"  Draft saved: {llm_result['title']}")
        except Exception as exc:
            session.rollback()
            result["failed"] += 1
            print(f"  ERROR event {event.id}: {exc}")
    print(f"Drafts generated: {result['generated']}")
    print(f"Draft failures: {result['failed']}")
    if result["protected"]:
        print(f"Existing content protected: {dict(result['protected'])}")
    return result


def prepare_ner_articles(session, main_cohort, catchup_limit, before=None):
    main_ids = {a.id for a in main_cohort}
    done = get_ner_done_ids(session, main_ids)
    needed = [a for a in main_cohort if a.id not in done]
    return needed + get_missing_ner_catchup(session, catchup_limit, main_ids, before=before)


def prepare_event_articles(session, main_cohort, ner_articles, catchup_limit, before=None):
    candidates = {a.id: a for a in main_cohort + ner_articles}
    ids = set(candidates)
    ready_ids = (get_embedded_ids(session, ids)
                 & get_ner_done_ids(session, ids)) - get_assigned_ids(session, ids)
    ready = [a for article_id, a in candidates.items()
             if article_id in ready_ids
             and (a.published_at or a.scraped_at) >= EVENT_BACKFILL_START]
    catchup = get_event_catchup_articles(session, catchup_limit, ids, before=before)
    return list({a.id: a for a in ready + catchup}.values())


def main():
    parser = argparse.ArgumentParser(
        description="Incremental Paraguay News article processing pipeline."
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help="Main cohort size and independent catch-up batch size.")
    parser.add_argument("--stage", choices=("all", "embeddings", "ner", "events"),
                        default="all", help="Run one stage or the full pipeline.")
    parser.add_argument("--before", type=date.fromisoformat, metavar="YYYY-MM-DD",
                        help="Only articles scraped before this local calendar date (exclusive).")
    parser.add_argument("--skip-drafts", action="store_true",
                        help="Do not generate Qwen editorial drafts.")
    args = parser.parse_args()
    if args.limit <= 0:
        parser.error("--limit must be greater than zero")

    before = (datetime.combine(args.before, time.min, tzinfo=LOCAL_TIMEZONE)
              if args.before is not None else None)
    print_header("PARAGUAY NEWS — PRODUCTION PIPELINE")
    print(f"Stage: {args.stage}")
    print(f"Limit: {args.limit}")
    print(f"Scraped before: {args.before or '(no cutoff)'} (exclusive; America/Asuncion)")
    print(f"Generate drafts: {args.stage == 'all' and not args.skip_drafts}")
    print(f"Excluded sources: {', '.join(sorted(EXCLUDED_SOURCES)) or '(none)'}")

    session = SessionLocal()
    try:
        print("\nCurrent eligible backlog:")
        print(f"  Missing embeddings: {count_missing_embeddings(session, before)}")
        print(f"  Missing NER: {count_missing_ner(session, before)}")
        print(f"  Unassigned (already embedded and NER-complete): {count_unassigned(session, before)}")

        main_cohort = []
        ner_articles = []
        embedding_count = 0
        ner_result = {"processed": 0, "entities": 0, "zero_entities": 0}
        event_result = {"processed": 0, "new_events": 0,
                        "existing_events": 0, "skipped": 0,
                        "affected_event_ids": set()}
        representatives = {"updated": 0, "multi_article_event_ids": set()}
        drafts = {"generated": 0, "failed": 0, "protected": Counter()}

        if args.stage in ("all", "embeddings"):
            main_cohort = get_new_article_cohort(session, args.limit, before=before)
            print(f"\nEmbedding cohort: {len(main_cohort)} articles")
            if main_cohort:
                model = load_embedding_model()
                try:
                    embedding_count = run_embedding_stage(session, model, main_cohort)
                finally:
                    del model
                    safe_cuda_cleanup()
            else:
                print("No articles require embeddings.")

        if args.stage in ("all", "ner"):
            if args.stage == "all":
                ner_articles = prepare_ner_articles(session, main_cohort, args.limit,
                                                    before=before)
            else:
                ner_articles = get_missing_ner_catchup(session, args.limit, before=before)
            if ner_articles:
                ner_model = load_ner()
                try:
                    ner_result = run_ner_stage(session, ner_model, ner_articles)
                finally:
                    del ner_model
                    safe_cuda_cleanup()
            else:
                print("No articles require NER.")

        if args.stage in ("all", "events"):
            if args.stage == "all":
                event_articles = prepare_event_articles(
                    session, main_cohort, ner_articles, args.limit, before=before
                )
            else:
                event_articles = get_event_catchup_articles(
                    session, args.limit, before=before, chronological=True
                )
            if event_articles:
                matcher = load_matcher()
                event_result = run_event_stage(session, matcher, event_articles)
            else:
                print("No eligible articles require event assignment.")
            representatives = update_representatives(
                session, event_result["affected_event_ids"]
            )

        if args.stage == "all" and not args.skip_drafts:
            drafts = generate_new_drafts(
                session, representatives["multi_article_event_ids"]
            )

        print_header("PIPELINE COMPLETE")
        print(f"Stage: {args.stage}")
        print(f"Embeddings created: {embedding_count}")
        print(f"NER processed: {ner_result['processed']}")
        print(f"Event assignments: {event_result['processed']}")
        print(f"  New events: {event_result['new_events']}")
        print(f"  Existing events: {event_result['existing_events']}")
        print(f"  Skipped: {event_result['skipped']}")
        print(f"Representatives updated: {representatives['updated']}")
        print(f"Drafts generated: {drafts['generated']}")
        print("\nRemaining eligible backlog:")
        print(f"  Missing embeddings: {count_missing_embeddings(session, before)}")
        print(f"  Missing NER: {count_missing_ner(session, before)}")
        print(f"  Unassigned (already embedded and NER-complete): {count_unassigned(session, before)}")
        if args.stage == "all" and args.skip_drafts:
            print("\nDraft generation was skipped.")
        elif args.stage != "all":
            print("\nOther stages were intentionally not run.")
    except KeyboardInterrupt:
        session.rollback()
        print("\nPipeline interrupted. Committed stages remain saved; rerun to resume.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
