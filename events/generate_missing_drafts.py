"""Generate missing editorial drafts for selected news events.

Run from project root: python -m events.generate_missing_drafts --limit 1 --order largest
"""
from __future__ import annotations

import argparse
from sqlalchemy import select, func, exists

from database.db import SessionLocal
from database.models import Article, Event, EventArticle, EventContent
from events.build_event_context import load_event_articles, select_context_articles, build_context
from events.generate_event_content import (
    MAX_CONTEXT_ARTICLES,
    OLLAMA_MODEL,
    build_llm_prompt,
    call_ollama,
    save_event_draft,
)


def eligible_events_query(args):
    """Select only events without ANY content, regardless of review status."""
    content_exists = exists(select(EventContent.event_id).where(EventContent.event_id == Event.id))
    query = select(Event).where(
        Event.article_count >= args.min_articles,
        Event.representative_article_id.is_not(None),
        ~content_exists,
    )
    if args.max_articles is not None:
        query = query.where(Event.article_count <= args.max_articles)
    if args.event_id is not None:
        query = query.where(Event.id == args.event_id)

    if args.order == "largest":
        query = query.order_by(Event.article_count.desc(), Event.id.asc())
    elif args.order == "smallest":
        query = query.order_by(Event.article_count.asc(), Event.id.asc())
    elif args.order == "newest":
        query = query.order_by(Event.last_seen_at.desc().nullslast(), Event.id.desc())
    else:
        query = query.order_by(Event.last_seen_at.asc().nullsfirst(), Event.id.asc())
    return query.limit(args.limit)


def source_count_for_event(session, event_id):
    return session.scalar(
        select(func.count(func.distinct(Article.source_id)))
        .join(EventArticle, EventArticle.article_id == Article.id)
        .where(EventArticle.event_id == event_id)
    ) or 0


def main():
    parser = argparse.ArgumentParser(description="Generate missing event drafts using the existing Qwen workflow.")
    parser.add_argument("--limit", type=int, default=1, help="Maximum events to select (default: 1).")
    parser.add_argument("--order", choices=("largest", "smallest", "newest", "oldest"), default="largest")
    parser.add_argument("--min-articles", type=int, default=2, help="Minimum event article count (default: 2).")
    parser.add_argument("--max-articles", type=int, default=None, help="Maximum event article count (filter, not LLM context size).")
    parser.add_argument("--event-id", type=int, default=None, help="Generate for a particular eligible event.")
    parser.add_argument("--max-context-articles", type=int, default=MAX_CONTEXT_ARTICLES,
                        help="Maximum articles supplied to Qwen (default: 6).")
    parser.add_argument("--dry-run", action="store_true", help="Preview events without calling Ollama or saving anything.")
    args = parser.parse_args()
    if args.limit < 1 or args.min_articles < 2 or args.max_context_articles < 1:
        parser.error("--limit must be >= 1, --min-articles >= 2, and --max-context-articles >= 1")
    if args.max_articles is not None and args.max_articles < args.min_articles:
        parser.error("--max-articles must be >= --min-articles")
    if args.event_id is not None and args.event_id < 1:
        parser.error("--event-id must be positive")

    session = SessionLocal()
    try:
        events = list(session.scalars(eligible_events_query(args)).all())
        print("=" * 72)
        print("MISSING EVENT DRAFTS")
        print("=" * 72)
        print(f"Model: {OLLAMA_MODEL} | Order: {args.order} | Selected: {len(events)}")
        print(f"Event size: {args.min_articles} to {args.max_articles or 'unlimited'} articles")
        print(f"LLM context: up to {args.max_context_articles} articles")
        if args.dry_run:
            print("DRY RUN: no Ollama requests or database writes")
        if not events:
            print("No eligible events found. Existing draft/approved/rejected content is never overwritten.")
            return

        generated = failed = skipped = 0
        for i, selected_event in enumerate(events, 1):
            event_id = selected_event.id
            # Refresh after any prior rollback/commit; verify protection immediately before generation.
            event = session.get(Event, event_id)
            if event is None:
                skipped += 1
                continue
            headline = session.scalar(select(Article.title).where(Article.id == event.representative_article_id))
            n_sources = source_count_for_event(session, event_id)
            print(f"\n[{i}/{len(events)}] Event {event_id} | {event.article_count} articles | {n_sources} sources")
            print(f"Representative: {headline or '(untitled)'}")
            if args.dry_run:
                continue
            try:
                already_exists = session.scalar(
                    select(EventContent.event_id).where(EventContent.event_id == event_id).limit(1)
                )
                if already_exists is not None:
                    print("SKIP: event content already exists; protected.")
                    skipped += 1
                    continue
                articles = load_event_articles(session, event_id)
                if not articles:
                    raise RuntimeError("No articles with the required embeddings were found")
                selected = select_context_articles(
                    articles, event.representative_article_id,
                    max_articles=args.max_context_articles,
                )
                if not selected:
                    raise RuntimeError("No context articles selected")
                context = build_context(event, articles, selected)
                prompt = build_llm_prompt(context)
                result = call_ollama(prompt)
                # Protect against content created during the LLM request.
                session.expire_all()
                if session.scalar(select(EventContent.event_id).where(EventContent.event_id == event_id).limit(1)) is not None:
                    print("SKIP: content appeared while generating; no overwrite.")
                    skipped += 1
                    continue
                save_event_draft(session=session, event=event, context=context, result=result)
                generated += 1
                print(f"Saved draft: {result['title']}")
                print(f"Summary: {result['summary']}")
                print(f"Context: {context['context_article_count']} articles / {context['context_source_count']} sources")
            except KeyboardInterrupt:
                session.rollback()
                print("\nInterrupted; previously saved drafts remain committed.")
                raise SystemExit(130)
            except Exception as exc:
                session.rollback()
                failed += 1
                print(f"ERROR event {event_id}: {exc}")
        print("\n" + "=" * 72)
        print(f"Finished: generated={generated}, failed={failed}, skipped={skipped}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
