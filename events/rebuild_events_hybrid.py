"""Isolated chronological event rebuild into PostgreSQL staging tables.

Run from repository root:
  python -m events.rebuild_events_clean --from-date 2026-11-01 --to-date 2026-11-17
  python -m events.rebuild_events_clean --from-date 2026-11-01 --to-date 2026-11-17 --stage

No production events, assignments, or editorial records are modified. The --stage
operation writes a NEW, isolated run into event_rebuild_stage.* tables only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import numpy as np
from sqlalchemy import func, select, text

from database.models import Article, ArticleEmbedding, ArticleEntity, EventArticle, EventContent, Source
from events import assign_events as matching
from events.crisis_assignment import ANCHORS, ANCHOR_BY_KEY, classify as classify_crisis

SCHEMA = "event_rebuild_stage"


def utc_day(s):
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def fetch_data(session, start, end):
    effective = func.coalesce(Article.published_at, Article.scraped_at)
    articles = list(session.scalars(select(Article).join(Source, Source.id == Article.source_id).where(effective >= start, effective < end, Source.name != "Más Encarnación")
                                    .order_by(effective, Article.id)).all())
    ids = [a.id for a in articles]
    vectors = {}
    entities = defaultdict(matching.empty_entities)
    # Avoid huge IN queries by reading in chunks.
    for offset in range(0, len(ids), 1000):
        chunk = ids[offset:offset + 1000]
        for aid, embedding in session.execute(select(ArticleEmbedding.article_id, ArticleEmbedding.embedding).where(
            ArticleEmbedding.article_id.in_(chunk),
            ArticleEmbedding.model == matching.EMBEDDING_MODEL,
            ArticleEmbedding.task == matching.EMBEDDING_TASK)):
            vectors[int(aid)] = matching.embedding_to_numpy(embedding)
        for aid, entity_type, normalized in session.execute(select(
            ArticleEntity.article_id, ArticleEntity.entity_type, ArticleEntity.normalized_text).where(
                ArticleEntity.article_id.in_(chunk), ArticleEntity.model == matching.NER_MODEL,
                ArticleEntity.entity_type.in_(["PER", "ORG", "LOC"]))):
            if not matching.is_media_entity(normalized):
                entities[int(aid)][entity_type].add(normalized)
    return articles, vectors, entities


def preview(session, start, end):
    effective = func.coalesce(Article.published_at, Article.scraped_at)
    total = session.scalar(select(func.count()).select_from(Article).join(Source, Source.id == Article.source_id).where(effective >= start, effective < end, Source.name != "Más Encarnación"))
    embedded = session.scalar(select(func.count()).select_from(Article).join(Source, Source.id == Article.source_id).where(
        effective >= start, effective < end, Source.name != "Más Encarnación",
        select(ArticleEmbedding.id).where(
            ArticleEmbedding.article_id == Article.id,
            ArticleEmbedding.model == matching.EMBEDDING_MODEL,
            ArticleEmbedding.task == matching.EMBEDDING_TASK).exists()))
    affected = session.scalar(select(func.count(func.distinct(EventArticle.event_id)))
                              .select_from(EventArticle).join(Article, Article.id == EventArticle.article_id)
                              .where(effective >= start, effective < end))
    cross_boundary = session.scalar(select(func.count(func.distinct(EventArticle.event_id)))
        .select_from(EventArticle).join(Article, Article.id == EventArticle.article_id)
        .where(effective >= start, effective < end,
               EventArticle.event_id.in_(select(EventArticle.event_id).join(
                   Article, Article.id == EventArticle.article_id).where(effective < start))))
    print(f"UTC period: {start.date()} through {(end-timedelta(days=1)).date()} inclusive")
    print(f"Articles in period: {total:,}; with required embeddings: {embedded:,}; missing: {total-embedded:,}")
    print(f"Production events intersecting period (not modified): {affected:,}")
    print(f"Of those, events with pre-period article membership: {cross_boundary:,}")
    print("PREVIEW ONLY: no changes made. Use --stage to create a separate reconstruction.")


def simulate(articles, vectors, entities, matcher, hybrid=False):
    # Active 48-hour history contains only articles already staged in this run.
    active = deque()  # (effective_time, article_id, normalized_embedding)
    memberships = {}  # article_id -> stage_event_id
    event_info = {}   # stage_event_id -> dict
    staged_memberships = []
    next_event_id = 1
    fixed_event_ids = {}
    if hybrid:
        for anchor in ANCHORS:
            eid = next_event_id
            next_event_id += 1
            fixed_event_ids[anchor.key] = eid
    decisions = Counter()
    missing = []

    for index, article in enumerate(articles, 1):
        aid = int(article.id)
        when = matching.get_effective_time(article)
        vector = vectors.get(aid)
        if vector is None:
            missing.append(aid)
            continue
        # A direct anchor assignment never participates in ordinary candidate
        # retrieval. This prevents chain-growth into fixed clusters.
        anchor_key = classify_crisis(article) if hybrid else None
        if anchor_key is not None:
            eid = fixed_event_ids[anchor_key]
            if eid not in event_info:
                event_info[eid] = {"title": ANCHOR_BY_KEY[anchor_key].title,
                                   "representative_article_id": aid,
                                   "first_seen_at": when, "last_seen_at": when,
                                   "article_count": 0}
            event_info[eid]["article_count"] += 1
            event_info[eid]["last_seen_at"] = when
            memberships[aid] = eid
            staged_memberships.append({"event_id": eid, "article_id": aid,
                                       "match_probability": None,
                                       "similarity": None,
                                       "is_seed": event_info[eid]["article_count"] == 1})
            decisions[anchor_key] += 1
            continue

        cutoff = when - timedelta(hours=matching.CANDIDATE_WINDOW_HOURS)
        while active and active[0][0] < cutoff:
            active.popleft()

        candidates = []
        if active:
            # All active entries are earlier in (effective timestamp, article ID) order.
            matrix = np.stack([item[2] for item in active])
            similarities = matrix @ vector
            for i in np.flatnonzero(similarities >= matching.MIN_RETRIEVAL_SIMILARITY):
                candidates.append((active[int(i)][1], float(similarities[i])))
            candidates.sort(key=lambda item: (-item[1], item[0]))
            candidates = candidates[:matching.TOP_K_NEIGHBORS]

        grouped = defaultdict(list)
        for candidate_id, similarity in candidates:
            pair = matching.score_pair(matcher, similarity,
                entities.get(aid, matching.empty_entities()),
                entities.get(candidate_id, matching.empty_entities()))
            pair["candidate_article_id"] = candidate_id
            grouped[memberships[candidate_id]].append(pair)

        selected_id, evidence = matching.choose_event(grouped, {
            eid: event_info[eid]["article_count"] for eid in grouped}) if grouped else (None, None)

        if selected_id is None:
            eid = next_event_id
            next_event_id += 1
            event_info[eid] = {"title": article.title, "representative_article_id": aid,
                               "first_seen_at": when, "last_seen_at": when, "article_count": 1}
            probability, similarity, is_seed = None, None, True
            decisions["new_event"] += 1
        else:
            eid = selected_id
            event_info[eid]["article_count"] += 1
            event_info[eid]["last_seen_at"] = when
            probability = evidence["max_probability"]
            similarity = evidence["best_similarity"]
            is_seed = False
            decisions["existing_event"] += 1

        memberships[aid] = eid
        staged_memberships.append({"event_id": eid, "article_id": aid,
                                   "match_probability": probability,
                                   "similarity": similarity, "is_seed": is_seed})
        active.append((when, aid, vector))
        if index % 500 == 0:
            print(f"Processed {index:,}/{len(articles):,}: {dict(decisions)}", flush=True)
    assert len(memberships) == len(staged_memberships)
    assert sum(e["article_count"] for e in event_info.values()) == len(staged_memberships)
    return event_info, staged_memberships, decisions, missing


def create_staging_tables(session):
    # Separate schema, not mapped production tables. No destructive DDL.
    session.execute(text(f'CREATE SCHEMA IF NOT EXISTS {SCHEMA}'))
    session.execute(text(f'''CREATE TABLE IF NOT EXISTS {SCHEMA}.runs (
        run_id uuid PRIMARY KEY, from_date date NOT NULL, to_date date NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        article_count integer NOT NULL, event_count integer NOT NULL,
        embedding_model text NOT NULL, matcher_file text NOT NULL)'''))
    session.execute(text(f'''CREATE TABLE IF NOT EXISTS {SCHEMA}.events (
        run_id uuid NOT NULL REFERENCES {SCHEMA}.runs(run_id) ON DELETE CASCADE,
        stage_event_id integer NOT NULL, title text NOT NULL,
        representative_article_id bigint NOT NULL,
        first_seen_at timestamptz NOT NULL, last_seen_at timestamptz NOT NULL,
        article_count integer NOT NULL,
        PRIMARY KEY (run_id, stage_event_id))'''))
    session.execute(text(f'''CREATE TABLE IF NOT EXISTS {SCHEMA}.event_articles (
        run_id uuid NOT NULL REFERENCES {SCHEMA}.runs(run_id) ON DELETE CASCADE,
        stage_event_id integer NOT NULL,
        article_id bigint NOT NULL,
        match_probability double precision, similarity double precision,
        is_seed boolean NOT NULL,
        PRIMARY KEY (run_id, article_id),
        FOREIGN KEY (run_id, stage_event_id) REFERENCES {SCHEMA}.events(run_id, stage_event_id))'''))


def save_staging(session, run_id, start, end, event_info, memberships):
    create_staging_tables(session)
    session.execute(text(f'''INSERT INTO {SCHEMA}.runs
        (run_id, from_date, to_date, article_count, event_count, embedding_model, matcher_file)
        VALUES (:run_id, :from_date, :to_date, :article_count, :event_count, :embedding_model, :matcher_file)'''),
        {"run_id": run_id, "from_date": start.date(), "to_date": (end-timedelta(days=1)).date(),
         "article_count": len(memberships), "event_count": len(event_info),
         "embedding_model": matching.EMBEDDING_MODEL, "matcher_file": str(matching.MODEL_FILE)})
    ev_sql = text(f'''INSERT INTO {SCHEMA}.events
        (run_id, stage_event_id, title, representative_article_id, first_seen_at, last_seen_at, article_count)
        VALUES (:run_id, :stage_event_id, :title, :representative_article_id,
                :first_seen_at, :last_seen_at, :article_count)''')
    for offset in range(0, len(event_info), 1000):
        batch = list(event_info.items())[offset:offset+1000]
        session.execute(ev_sql, [{"run_id": run_id, "stage_event_id": eid, **info} for eid, info in batch])
    mem_sql = text(f'''INSERT INTO {SCHEMA}.event_articles
        (run_id, stage_event_id, article_id, match_probability, similarity, is_seed)
        VALUES (:run_id, :event_id, :article_id, :match_probability, :similarity, :is_seed)''')
    for offset in range(0, len(memberships), 1000):
        session.execute(mem_sql, [{"run_id": run_id, **m} for m in memberships[offset:offset+1000]])
    actual = session.scalar(text(f'SELECT count(*) FROM {SCHEMA}.event_articles WHERE run_id=:run_id'),
                            {"run_id": run_id})
    if actual != len(memberships):
        raise RuntimeError(f"Staging count mismatch: {actual} != {len(memberships)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--stage", action="store_true", help="Create an isolated staging run; NEVER modifies production clusters")
    parser.add_argument("--hybrid", action="store_true", help="Use conservative Ueno crisis anchors plus normal matcher")
    args = parser.parse_args()
    start = utc_day(args.from_date)
    end = utc_day(args.to_date) + timedelta(days=1)
    if start >= end:
        parser.error("--to-date must not precede --from-date")
    if start < matching.EVENT_BACKFILL_START:
        parser.error("start precedes configured EVENT_BACKFILL_START")

    session = matching.SessionLocal()
    try:
        if not args.stage:
            preview(session, start, end)
            session.rollback()
            return
        print("Loading input articles, embeddings and named entities...")
        articles, vectors, entities = fetch_data(session, start, end)
        if not articles:
            raise RuntimeError("No articles found for requested period")
        if len(vectors) != len(articles):
            missing = sorted({a.id for a in articles} - set(vectors))
            raise RuntimeError(f"{len(missing)} articles lack required embeddings. Examples: {missing[:15]}. "
                               "Run embedding generation first or narrow the scope.")
        matcher = matching.load_matcher()
        print(f"Simulating {len(articles):,} articles with NO production event candidates...")
        event_info, memberships, decisions, missing = simulate(articles, vectors, entities, matcher, hybrid=args.hybrid)
        run_id = str(uuid4())
        print(f"Staging run {run_id}: {len(event_info):,} events, {len(memberships):,} assignments")
        save_staging(session, run_id, start, end, event_info, memberships)
        session.commit()
        print("STAGING COMMITTED; PRODUCTION UNCHANGED")
        print(f"run_id: {run_id}")
        print(f"Decisions: {dict(decisions)}")
        if args.hybrid:
            print("Fixed-anchor assignments:")
            for anchor in ANCHORS:
                print(f"  {anchor.key}: {decisions[anchor.key]:,} — {anchor.title}")
        largest = sorted(event_info.items(), key=lambda x: (-x[1]["article_count"], x[0]))[:10]
        print("Top 10 staged clusters (stage_event_id, article_count, title):")
        for eid, info in largest:
            print(f"  {eid:>6}  {info['article_count']:>5}  {info['title'][:110]}")
        print("Inspect staging results before designing any production promotion step.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
