from __future__ import annotations

import argparse
from collections import Counter

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
    load_model as load_embedding_model,
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


def effective_time_expression():
    return func.coalesce(Article.published_at, Article.scraped_at)


def count_missing_embeddings(session):
    return int(session.scalar(select(func.count(Article.id)).where(
        eligible_source_filter(), ~Article.id.in_(embedded_ids_query()),
    )) or 0)


def count_missing_ner(session):
    return int(session.scalar(select(func.count(Article.id)).where(
        eligible_source_filter(), Article.id.in_(embedded_ids_query()),
        ~Article.id.in_(ner_ids_query()),
    )) or 0)


def count_unassigned(session):
    return int(session.scalar(select(func.count(Article.id)).where(
        eligible_source_filter(), Article.id.in_(embedded_ids_query()),
        Article.id.in_(ner_ids_query()),
        ~Article.id.in_(assigned_ids_query()),
        effective_time_expression() >= EVENT_BACKFILL_START,
    )) or 0)


def get_new_article_cohort(session, limit):
    stmt = select(Article).where(
        eligible_source_filter(),
        ~Article.id.in_(embedded_ids_query()),
    ).order_by(Article.scraped_at.desc().nullslast(), Article.id.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def get_missing_ner_catchup(session, limit, exclude_ids=None):
    stmt = select(Article).where(
        eligible_source_filter(), Article.id.in_(embedded_ids_query()),
        ~Article.id.in_(ner_ids_query()),
    )
    if exclude_ids:
        stmt = stmt.where(~Article.id.in_(exclude_ids))
    return list(session.scalars(stmt.order_by(
        Article.scraped_at.desc().nullslast(), Article.id.desc()
    ).limit(limit)).all())


def get_event_catchup_articles(session, limit, exclude_ids=None):
    stmt = select(Article).where(
        eligible_source_filter(), Article.id.in_(embedded_ids_query()),
        Article.id.in_(ner_ids_query()),
        ~Article.id.in_(assigned_ids_query()),
        effective_time_expression() >= EVENT_BACKFILL_START,
    )
    if exclude_ids:
        stmt = stmt.where(~Article.id.in_(exclude_ids))
    return list(session.scalars(stmt.order_by(
        Article.scraped_at.desc().nullslast(), Article.id.desc()
    ).limit(limit)).all())


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


def run_embedding_stage(session, model, articles):
    print_header("STAGE 1 — EMBEDDINGS")
    if not articles:
        print("No articles require embeddings.")
        return 0
    print(f"Articles to embed: {len(articles)}")
    texts = [build_article_text(a) for a in articles]
    with torch.inference_mode():
        vectors = model.encode(
            texts, task=EMBEDDING_TASK, batch_size=BATCH_SIZE,
            normalize_embeddings=True, show_progress_bar=True,
            convert_to_numpy=True,
        )
    if vectors.shape != (len(articles), DIMENSIONS):
        raise RuntimeError(f"Unexpected embedding shape: {vectors.shape}")
    for article, vector in zip(articles, vectors):
        session.add(ArticleEmbedding(
            article_id=article.id, model=EMBEDDING_MODEL,
            task=EMBEDDING_TASK, dimensions=DIMENSIONS,
            embedding=vector.tolist(),
        ))
    session.commit()
    print(f"Embeddings saved: {len(articles)}")
    del vectors, texts
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
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


def prepare_ner_articles(session, main_cohort, catchup_limit):
    main_ids = {a.id for a in main_cohort}
    done = get_ner_done_ids(session, main_ids)
    needed = [a for a in main_cohort if a.id not in done]
    return needed + get_missing_ner_catchup(session, catchup_limit, main_ids)


def prepare_event_articles(session, main_cohort, ner_articles, catchup_limit):
    candidates = {a.id: a for a in main_cohort + ner_articles}
    ids = set(candidates)
    ready_ids = (get_embedded_ids(session, ids)
                 & get_ner_done_ids(session, ids)) - get_assigned_ids(session, ids)
    ready = [a for article_id, a in candidates.items()
             if article_id in ready_ids
             and (a.published_at or a.scraped_at) >= EVENT_BACKFILL_START]
    catchup = get_event_catchup_articles(session, catchup_limit, ids)
    return list({a.id: a for a in ready + catchup}.values())


def main():
    parser = argparse.ArgumentParser(
        description="Incremental Paraguay News article processing pipeline."
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help="Main cohort size and independent catch-up batch size.")
    parser.add_argument("--skip-drafts", action="store_true",
                        help="Do not generate Qwen editorial drafts.")
    args = parser.parse_args()
    if args.limit <= 0:
        parser.error("--limit must be greater than zero")

    print_header("PARAGUAY NEWS — PRODUCTION PIPELINE")
    print(f"Main cohort limit: {args.limit}")
    print(f"Catch-up limit: {args.limit}")
    print(f"Generate drafts: {not args.skip_drafts}")
    print(f"Excluded sources: {', '.join(sorted(EXCLUDED_SOURCES)) or '(none)'}")

    session = SessionLocal()
    try:
        missing_embeddings = count_missing_embeddings(session)
        missing_ner = count_missing_ner(session)
        unassigned = count_unassigned(session)
    finally:
        session.close()

    print("\nCurrent backlog (excluding disabled sources):")
    print(f"  Missing embeddings: {missing_embeddings}")
    print(f"  Missing NER: {missing_ner}")
    print(f"  Unassigned: {unassigned}")
    if not (missing_embeddings or missing_ner or unassigned):
        print("\nNothing to process.")
        return

    session = SessionLocal()
    try:
        main_cohort = get_new_article_cohort(session, args.limit)
        print(f"\nMain cohort: {len(main_cohort)} articles")
        if main_cohort:
            times = [a.scraped_at for a in main_cohort if a.scraped_at is not None]
            if times:
                print(f"  Newest scraped_at: {max(times)}")
                print(f"  Oldest scraped_at: {min(times)}")

        if main_cohort:
            model = load_embedding_model()
            try:
                embedding_count = run_embedding_stage(session, model, main_cohort)
            finally:
                del model
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
        else:
            print_header("STAGE 1 — EMBEDDINGS")
            print("No articles require embeddings.")
            embedding_count = 0

        ner_articles = prepare_ner_articles(session, main_cohort, args.limit)
        if ner_articles:
            ner_model = load_ner()
            try:
                ner_result = run_ner_stage(session, ner_model, ner_articles)
            finally:
                del ner_model
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
        else:
            print_header("STAGE 2 — NER")
            print("No articles require NER.")
            ner_result = {"processed": 0, "entities": 0, "zero_entities": 0}

        event_articles = prepare_event_articles(
            session, main_cohort, ner_articles, args.limit
        )
        if event_articles:
            matcher = load_matcher()
            event_result = run_event_stage(session, matcher, event_articles)
        else:
            print_header("STAGE 3 — EVENT ASSIGNMENT")
            print("No articles require event assignment.")
            event_result = {"processed": 0, "new_events": 0,
                            "existing_events": 0, "skipped": 0,
                            "affected_event_ids": set()}

        representatives = update_representatives(
            session, event_result["affected_event_ids"]
        )
        if args.skip_drafts:
            print_header("STAGE 5 — EVENT DRAFTS")
            print("Draft generation skipped.")
            drafts = {"generated": 0, "failed": 0, "protected": Counter()}
        else:
            drafts = generate_new_drafts(
                session, representatives["multi_article_event_ids"]
            )

        print_header("PIPELINE COMPLETE")
        print(f"Main cohort: {len(main_cohort)}")
        print(f"Embeddings created: {embedding_count}")
        print(f"NER processed: {ner_result['processed']}")
        print(f"Event assignments: {event_result['processed']}")
        print(f"  New events: {event_result['new_events']}")
        print(f"  Existing events: {event_result['existing_events']}")
        print(f"  Skipped: {event_result['skipped']}")
        print(f"Representatives updated: {representatives['updated']}")
        print(f"Multi-article affected events: {len(representatives['multi_article_event_ids'])}")
        print(f"Drafts generated: {drafts['generated']}")
        if drafts['failed']:
            print(f"Draft failures: {drafts['failed']}")
        print("\nRemaining backlog (excluding disabled sources):")
        print(f"  Missing embeddings: {count_missing_embeddings(session)}")
        print(f"  Missing NER: {count_missing_ner(session)}")
        print(f"  Unassigned: {count_unassigned(session)}")
        if args.skip_drafts:
            print("\nDraft generation was skipped.")
        elif drafts["generated"]:
            print(f"\n{drafts['generated']} new draft(s) are available in Streamlit.")
        else:
            print("\nNo new editorial drafts were generated.")
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