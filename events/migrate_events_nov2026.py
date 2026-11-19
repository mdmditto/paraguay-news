"""Selective November 3-17 event migration from a verified staging run.

Run from repository root: python -m events.migrate_events_nov2026 [--apply]
Default is a FULL SQL rehearsal followed by ROLLBACK. --apply commits.
Requires an independent verified pg_dump backup and paused event-related workers.
Old events/content/history/proposals are NEVER deleted; emptied old events remain.
"""
from __future__ import annotations

import argparse
from sqlalchemy import text
from database.db import SessionLocal

RUN = '539be3e7-f129-4b55-9e11-454fade43695'
START = '2026-11-03 00:00:00'
END = '2026-11-18 00:00:00'
EXPECTED = 10167
EXPECTED_EVENTS = 6341


def scalar(s, query, **params):
    return s.execute(text(query), params).scalar_one()


def assert_equal(actual, expected, label):
    if actual != expected:
        raise RuntimeError(f'{label}: expected {expected}, found {actual}; transaction will roll back')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply', action='store_true', help='COMMIT changes; default rolls back')
    p.add_argument('--run-id', default=RUN)
    args = p.parse_args()
    params = {'run': args.run_id, 'start': START, 'end': END}
    session = SessionLocal()
    try:
        # Block concurrent event writes throughout the transaction. Pause all workers first.
        session.execute(text('SET LOCAL lock_timeout = \'15s\''))
        session.execute(text('SET LOCAL statement_timeout = \'10min\''))
        session.execute(text('LOCK TABLE public.event_articles, public.events, public.event_content, public.event_content_history, public.event_update_proposals IN SHARE ROW EXCLUSIVE MODE'))
        session.execute(text('LOCK TABLE event_rebuild_stage.event_articles, event_rebuild_stage.events, event_rebuild_stage.runs IN SHARE MODE'))
        session.execute(text('CREATE TEMP TABLE target AS SELECT a.id AS article_id, coalesce(a.published_at,a.scraped_at) AS article_time FROM public.articles a WHERE (coalesce(a.published_at,a.scraped_at) AT TIME ZONE \'America/Asuncion\') >= CAST(:start AS timestamp) AND (coalesce(a.published_at,a.scraped_at) AT TIME ZONE \'America/Asuncion\') < CAST(:end AS timestamp) AND EXISTS (SELECT 1 FROM public.event_articles ea WHERE ea.article_id=a.id)'), params)
        session.execute(text('CREATE UNIQUE INDEX ON target(article_id)'))
        session.execute(text('CREATE TEMP TABLE desired AS SELECT sea.stage_event_id, sea.article_id, sea.match_probability, sea.similarity, sea.is_seed, t.article_time FROM event_rebuild_stage.event_articles sea JOIN target t ON t.article_id=sea.article_id WHERE sea.run_id=CAST(:run AS uuid)'), params)
        session.execute(text('CREATE UNIQUE INDEX ON desired(article_id)'))
        session.execute(text('CREATE TEMP TABLE before_target AS SELECT ea.* FROM public.event_articles ea JOIN target t ON t.article_id=ea.article_id'))
        session.execute(text('CREATE TEMP TABLE before_outside AS SELECT ea.* FROM public.event_articles ea WHERE NOT EXISTS (SELECT 1 FROM target t WHERE t.article_id=ea.article_id)'))
        target_n = scalar(session,'SELECT count(*) FROM target')
        desired_n = scalar(session,'SELECT count(*) FROM desired')
        events_n = scalar(session,'SELECT count(DISTINCT stage_event_id) FROM desired')
        old_n = scalar(session,'SELECT count(*) FROM before_target')
        print(f'Preflight: target={target_n}, staged={desired_n}, staged_events={events_n}, existing_assignments={old_n}')
        for actual, expected, name in [(target_n,EXPECTED,'target count'),(desired_n,EXPECTED,'staging coverage'),(events_n,EXPECTED_EVENTS,'staged events'),(old_n,EXPECTED,'existing assignment count')]:
            assert_equal(actual,expected,name)
        assert_equal(scalar(session,'SELECT count(*) FROM (SELECT article_id FROM before_target GROUP BY article_id HAVING count(*) <> 1) x'),0,'existing duplicate assignments')
        assert_equal(scalar(session,'SELECT count(*) FROM desired d LEFT JOIN event_rebuild_stage.events se ON se.run_id=CAST(:run AS uuid) AND se.stage_event_id=d.stage_event_id WHERE se.stage_event_id IS NULL', **params),0,'missing staged event metadata')
        assert_equal(scalar(session,'SELECT count(*) FROM desired WHERE article_time IS NULL'),0,'null timestamps')
        # Every staged group gets a NEW event ID. The representative is chosen INSIDE the replacement window.
        # No existing event, content, revision, or proposal is deleted.
        session.execute(text('''CREATE TEMP TABLE stage_groups AS
            SELECT d.stage_event_id, min(d.article_time) AS first_seen_at,
                   max(d.article_time) AS last_seen_at, count(*)::integer AS article_count,
                   (array_agg(d.article_id ORDER BY d.article_time,d.article_id))[1] AS representative_article_id
            FROM desired d GROUP BY d.stage_event_id'''))
        session.execute(text('''CREATE TEMP TABLE mapping (stage_event_id integer PRIMARY KEY, new_event_id bigint NOT NULL UNIQUE)'''))
        # Explicit allocation avoids relying on INSERT RETURNING row order.
        session.execute(text('''INSERT INTO mapping(stage_event_id,new_event_id)
            SELECT stage_event_id, nextval(pg_get_serial_sequence('public.events','id'))
            FROM stage_groups ORDER BY stage_event_id'''))
        session.execute(text('''INSERT INTO public.events
            (id,title,first_seen_at,last_seen_at,article_count,created_at,updated_at,representative_article_id)
            SELECT m.new_event_id,se.title,g.first_seen_at,g.last_seen_at,g.article_count,
                   now(),now(),g.representative_article_id
            FROM mapping m JOIN stage_groups g USING(stage_event_id)
            JOIN event_rebuild_stage.events se ON se.stage_event_id=g.stage_event_id AND se.run_id=CAST(:run AS uuid)'''),params)
        # Remove only in-period assignments, never outside-period assignments.
        session.execute(text('DELETE FROM public.event_articles ea USING target t WHERE ea.article_id=t.article_id'))
        session.execute(text('''INSERT INTO public.event_articles
            (event_id,article_id,match_probability,similarity,is_seed,created_at)
            SELECT m.new_event_id,d.article_id,d.match_probability,d.similarity,
                   (d.article_id = g.representative_article_id),now()
            FROM desired d JOIN mapping m USING(stage_event_id)
            JOIN stage_groups g USING(stage_event_id)'''))
        # Recalculate OLD affected event metadata. Empty events are retained with count=0;
        # their old content/history/proposals remain untouched for archival review.
        session.execute(text('''CREATE TEMP TABLE affected_old AS
            SELECT DISTINCT event_id FROM before_target'''))
        session.execute(text('''UPDATE public.events e SET
            article_count = coalesce(stats.n,0),
            first_seen_at = coalesce(stats.first_at,e.first_seen_at),
            last_seen_at = coalesce(stats.last_at,e.last_seen_at),
            representative_article_id = CASE WHEN stats.n IS NULL THEN NULL
                WHEN EXISTS (SELECT 1 FROM public.event_articles x WHERE x.event_id=e.id AND x.article_id=e.representative_article_id)
                THEN e.representative_article_id ELSE stats.first_article END,
            updated_at=now()
            FROM affected_old ao LEFT JOIN LATERAL (
                SELECT count(*)::integer AS n, min(coalesce(a.published_at,a.scraped_at)) AS first_at,
                    max(coalesce(a.published_at,a.scraped_at)) AS last_at,
                    (array_agg(a.id ORDER BY coalesce(a.published_at,a.scraped_at),a.id))[1] AS first_article
                FROM public.event_articles ea JOIN public.articles a ON a.id=ea.article_id
                WHERE ea.event_id=ao.event_id
            ) stats ON true
            WHERE e.id=ao.event_id'''))
        # Safety checks performed before COMMIT.
        assert_equal(scalar(session,'SELECT count(*) FROM public.event_articles ea JOIN target t ON t.article_id=ea.article_id'),EXPECTED,'post-migration target assignments')
        assert_equal(scalar(session,'SELECT count(*) FROM (SELECT ea.article_id FROM public.event_articles ea JOIN target t ON t.article_id=ea.article_id GROUP BY ea.article_id HAVING count(*) <> 1) x'),0,'post-migration duplicate target assignments')
        assert_equal(scalar(session,'SELECT count(*) FROM (SELECT * FROM before_outside EXCEPT ALL SELECT ea.* FROM public.event_articles ea WHERE NOT EXISTS (SELECT 1 FROM target t WHERE t.article_id=ea.article_id)) x'),0,'lost/modified outside assignments')
        assert_equal(scalar(session,'SELECT count(*) FROM (SELECT ea.* FROM public.event_articles ea WHERE NOT EXISTS (SELECT 1 FROM target t WHERE t.article_id=ea.article_id) EXCEPT ALL SELECT * FROM before_outside) x'),0,'added outside assignments')
        assert_equal(scalar(session,'SELECT count(*) FROM mapping'),EXPECTED_EVENTS,'new event mapping count')
        assert_equal(scalar(session,'SELECT count(*) FROM public.event_articles ea JOIN mapping m ON m.new_event_id=ea.event_id'),EXPECTED,'new event membership')
        empty = scalar(session,'SELECT count(*) FROM public.events e JOIN affected_old ao ON ao.event_id=e.id WHERE e.article_count=0')
        print(f'Validation passed. New events: {events_n}; moved assignments: {desired_n}; old events now empty: {empty}')
        print('NOTE: Old empty events and all content/history/proposals are retained. Hide empty events in public queries.')
        if args.apply:
            session.commit()
            print('COMMITTED. Verify post-migration SQL checks and refresh editorial content before publishing.')
        else:
            session.rollback()
            print('DRY RUN ROLLED BACK. Production unchanged (PostgreSQL sequences may advance).')
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == '__main__':
    main()
