"""Safely rebuild event clusters intersecting a UTC date interval.

Dry-run by default. Commit requires a separately verified PostgreSQL backup.
Run from the repository root: python -m events.rebuild_events ...
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, exists, func, inspect, select, text

from database.models import Article, Event, EventArticle, EventContent
from events import assign_events as assignment


def utc_day(value):
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--commit", action="store_true", help="Persist changes (default: preview only)")
    parser.add_argument("--backup-verified", action="store_true", help="Confirm a restorable PostgreSQL backup exists")
    parser.add_argument("--max-events", type=int, default=1500, help="Safety cap on selected event count")
    parser.add_argument("--allow-protected", action="store_true", help="NOT IMPLEMENTED: protected events always excluded")
    args = parser.parse_args()
    if args.allow_protected:
        parser.error("Protected-event rebuilding is not supported. Handle editorial records separately.")
    if args.commit and not args.backup_verified:
        parser.error("--commit requires --backup-verified after verifying an external database backup")
    if args.max_events < 1:
        parser.error("--max-events must be positive")
    start = utc_day(args.from_date)
    end = utc_day(args.to_date) + timedelta(days=1)
    if start >= end:
        parser.error("--to-date must not precede --from-date")

    session = assignment.SessionLocal()
    try:
        # Serialize concurrent rebuilds. This does not block other writers: pause
        # ingestion, event assignment and editorial processes during a commit run.
        if args.commit:
            acquired = session.scalar(text("SELECT pg_try_advisory_xact_lock(716291, 20261104)"))
            if not acquired:
                raise RuntimeError("Another rebuild is already running")

        # Confirm that the tables expected by this script exist.
        db_tables = set(inspect(session.get_bind()).get_table_names())
        required = {"events", "event_articles", "event_content", "event_content_history", "event_update_proposals"}
        missing = required - db_tables
        if missing:
            raise RuntimeError(f"Missing expected tables: {sorted(missing)}")

        effective = func.coalesce(Article.published_at, Article.scraped_at)
        affected_stmt = (
            select(EventArticle.event_id)
            .join(Article, Article.id == EventArticle.article_id)
            .where(effective >= start, effective < end)
            .distinct()
        )
        affected_ids = set(session.scalars(affected_stmt).all())
        if len(affected_ids) > args.max_events:
            raise RuntimeError(f"Scope has {len(affected_ids)} events, above --max-events={args.max_events}")

        # All editorial history and proposals are protected, even for draft content.
        history_ids = set(session.scalars(text("SELECT DISTINCT event_id FROM event_content_history")).all())
        proposal_ids = set(session.scalars(text("SELECT DISTINCT event_id FROM event_update_proposals")).all())
        edited_ids = set(session.scalars(select(EventContent.event_id).where(
            (EventContent.status != "draft") |
            EventContent.final_title.is_not(None) |
            EventContent.final_summary.is_not(None) |
            EventContent.reviewed_at.is_not(None)
        )).all())
        protected_ids = affected_ids & (history_ids | proposal_ids | edited_ids)
        rebuild_ids = sorted(affected_ids - protected_ids)

        # Exclude any event with extra direct references not explicitly handled.
        foreign_keys = inspect(session.get_bind()).get_foreign_keys
        expected_dependents = {"event_articles", "event_content", "event_content_history", "event_update_proposals"}
        for table_name in db_tables:
            for fk in foreign_keys(table_name):
                if fk.get("referred_table") == "events" and table_name not in expected_dependents:
                    raise RuntimeError(f"Unexpected events foreign key from {table_name}; review schema before rebuild")

        if rebuild_ids:
            memberships = session.execute(
                select(EventArticle.event_id, EventArticle.article_id)
                .where(EventArticle.event_id.in_(rebuild_ids))
            ).all()
            replay_ids = sorted({int(article_id) for _, article_id in memberships})
        else:
            memberships, replay_ids = [], []

        content_ids = set(session.scalars(
            select(EventContent.event_id).where(EventContent.event_id.in_(rebuild_ids))
        ).all()) if rebuild_ids else set()

        print("=" * 68)
        print("EVENT REBUILD PREVIEW")
        print(f"UTC dates: {args.from_date} through {args.to_date} inclusive")
        print(f"Affected events:       {len(affected_ids)}")
        print(f"Protected events:      {len(protected_ids)}")
        print(f"Rebuildable events:    {len(rebuild_ids)}")
        print(f"Assignments removed:   {len(memberships)}")
        print(f"Distinct replay IDs:   {len(replay_ids)}")
        print(f"Drafts to remove:      {len(content_ids)}")
        print(f"Protected event IDs:   {sorted(protected_ids)}")
        print("=" * 68)

        if not args.commit:
            print("DRY RUN: no changes made. Use --commit --backup-verified to execute.")
            session.rollback()
            return
        if not rebuild_ids:
            print("Nothing to rebuild.")
            session.rollback()
            return

        # Ensure all replay articles have embeddings for the exact configured model/task.
        embedded = set(session.scalars(
            select(assignment.ArticleEmbedding.article_id).where(
                assignment.ArticleEmbedding.article_id.in_(replay_ids),
                assignment.ArticleEmbedding.model == assignment.EMBEDDING_MODEL,
                assignment.ArticleEmbedding.task == assignment.EMBEDDING_TASK,
            )
        ).all())
        missing_embeddings = set(replay_ids) - embedded
        if missing_embeddings:
            raise RuntimeError(f"Missing required embeddings for {len(missing_embeddings)} replay articles; examples: {sorted(missing_embeddings)[:15]}")

        articles = list(session.scalars(
            select(Article).where(Article.id.in_(replay_ids)).order_by(
                func.coalesce(Article.published_at, Article.scraped_at), Article.id
            )
        ).all())
        if len(articles) != len(replay_ids):
            raise RuntimeError("Some replay articles were not found")
        if any(assignment.get_effective_time(a) is None for a in articles):
            raise RuntimeError("Some replay articles have no effective timestamp")
        if any(assignment.get_effective_time(a) < assignment.EVENT_BACKFILL_START for a in articles):
            raise RuntimeError("Replay includes articles before EVENT_BACKFILL_START; refusing")

        print("Loading event matcher...")
        matcher = assignment.load_matcher()
        print("Deleting selected events (and cascading dependents) within transaction...")
        session.execute(delete(Event).where(Event.id.in_(rebuild_ids)))
        session.flush()

        counts = Counter()
        new_ids = set()
        for idx, article in enumerate(articles, 1):
            result = assignment.process_article(session, matcher, article, dry_run=False)
            decision = result.get("decision")
            if decision not in {"new_event", "existing_event"}:
                raise RuntimeError(f"Replay failed for article {article.id}: {result}")
            counts[decision] += 1
            if decision == "new_event":
                new_ids.add(int(result["event_id"]))
            # Querying ORM objects after writes triggers autoflush; explicit flush
            # also ensures newly created assignments are visible to next article.
            session.flush()
            if idx % 100 == 0:
                print(f"Replayed {idx}/{len(articles)}: {dict(counts)}")

        # Every replay article must be assigned exactly once; don't silently accept
        # accidental duplicate memberships caused by pre-existing overlaps.
        assignments = session.execute(
            select(EventArticle.article_id, func.count())
            .where(EventArticle.article_id.in_(replay_ids))
            .group_by(EventArticle.article_id)
        ).all()
        by_article = dict(assignments)
        bad = [aid for aid in replay_ids if by_article.get(aid) != 1]
        if bad:
            raise RuntimeError(f"Assignment validation failed for {len(bad)} articles: {bad[:15]}")

        # Validate counts for ALL events touched by the replay, including older
        # events to which a replay article may have attached.
        touched = set(session.scalars(
            select(EventArticle.event_id).where(EventArticle.article_id.in_(replay_ids))
        ).all())
        actual_counts = dict(session.execute(
            select(EventArticle.event_id, func.count())
            .where(EventArticle.event_id.in_(touched))
            .group_by(EventArticle.event_id)
        ).all())
        events = list(session.scalars(select(Event).where(Event.id.in_(touched))).all())
        mismatched = [(e.id, e.article_count, actual_counts.get(e.id, 0))
                      for e in events if e.article_count != actual_counts.get(e.id, 0)]
        if mismatched:
            raise RuntimeError(f"Event count mismatch: {mismatched[:15]}")

        print(f"Replay complete: {len(articles)} articles; {dict(counts)}")
        print(f"New event IDs: {len(new_ids)}; touched event IDs: {len(touched)}")
        print("WARNING: Drafts for deleted events are removed; regenerate after reviewing event quality.")
        session.commit()
        print("COMMITTED SUCCESSFULLY")
    except Exception:
        session.rollback()
        print("ROLLED BACK: no partial rebuild committed by this script")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
