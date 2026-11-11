"""Read-only chronological event-clustering benchmark.

Run: python -m events.benchmark_event_matching --from-date 2026-11-04 --to-date 2026-11-06
Copy this file to events/benchmark_event_matching.py first.

Runs baseline, quality-first, and quality-first+72h on identical articles.
Does NOT change PostgreSQL assignments. Uses the production trained matcher,
embeddings, entity loader, and event-evidence functions.
"""
import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import func, select

from database.models import Article
from events import assign_events as a


def utc_date(value):
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def summarize_clusters(members, times):
    sizes = [len(ids) for ids in members.values()]
    spans = [
        (max(times[i] for i in ids) - min(times[i] for i in ids)).total_seconds() / 3600
        for ids in members.values()
    ]
    return {
        "events": len(sizes),
        "singletons": sum(s == 1 for s in sizes),
        "multi_article": sum(s >= 2 for s in sizes),
        "max_size": max(sizes, default=0),
        "mean_size": round(float(np.mean(sizes)), 2) if sizes else 0,
        "p95_size": round(float(np.percentile(sizes, 95)), 2) if sizes else 0,
        "max_span_hours": round(max(spans, default=0), 1),
        "p95_span_hours": round(float(np.percentile(spans, 95)), 1) if spans else 0,
    }


def select_event(grouped, sizes, first_times, target_time, mode, max_span):
    accepted = []
    for eid, pairs in grouped.items():
        evidence = a.summarize_event_evidence(pairs)
        if not a.event_is_acceptable(evidence, sizes[eid]):
            continue
        if mode == "quality_72h":
            hours = (target_time - first_times[eid]).total_seconds() / 3600
            if hours < 0 or hours > max_span:
                continue
        if mode == "baseline":
            rank = (evidence["strong_matches"], evidence["top_two_mean"],
                    evidence["max_probability"], evidence["mean_probability"], -eid)
        else:
            rank = (evidence["top_two_mean"], evidence["max_probability"],
                    evidence["mean_probability"], evidence["strong_matches"], -eid)
        accepted.append((rank, eid))
    return max(accepted)[1] if accepted else None


def run_variant(records, vectors, neighbor_ids, pair_scores, mode, max_span):
    members = defaultdict(list)
    article_to_event = {}
    first_times = {}
    decisions = Counter()
    for idx, record in enumerate(records):
        aid, ts = record["id"], record["time"]
        grouped = defaultdict(list)
        for candidate_idx, similarity in neighbor_ids[idx]:
            candidate_id = records[candidate_idx]["id"]
            eid = article_to_event.get(candidate_id)
            if eid is None:
                continue
            key = (idx, candidate_idx)
            if key not in pair_scores:
                pair_scores[key] = a.score_pair(
                    record["matcher"],
                    similarity,
                    record["entities"],
                    records[candidate_idx]["entities"],
                )
            pair = dict(pair_scores[key])
            pair["candidate_article_id"] = candidate_id
            grouped[eid].append(pair)
        eid = select_event(grouped, {e: len(v) for e, v in members.items()},
                           first_times, ts, mode, max_span)
        if eid is None:
            eid = aid  # Stable simulated event identifier: seed article ID
            first_times[eid] = ts
            decisions["new_event"] += 1
        else:
            decisions["existing_event"] += 1
        article_to_event[aid] = eid
        members[eid].append(aid)
    return members, article_to_event, decisions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--max-span-hours", type=int, default=72)
    parser.add_argument("--output-dir", default="benchmark_results")
    parser.add_argument("--max-articles", type=int, default=None,
                        help="Optional smoke test; uses earliest N articles")
    args = parser.parse_args()
    start, end = utc_date(args.from_date), utc_date(args.to_date) + timedelta(days=1)
    if end <= start:
        parser.error("Invalid date interval")
    if args.max_span_hours <= 0:
        parser.error("--max-span-hours must be positive")

    session = a.SessionLocal()
    try:
        # Session stays read-only: no adds, deletes, updates, or commits.
        effective = func.coalesce(Article.published_at, Article.scraped_at)
        stmt = (select(Article)
                .join(a.ArticleEmbedding, a.ArticleEmbedding.article_id == Article.id)
                .where(effective >= start, effective < end,
                       a.ArticleEmbedding.model == a.EMBEDDING_MODEL,
                       a.ArticleEmbedding.task == a.EMBEDDING_TASK)
                .order_by(effective, Article.id))
        # ArticleEmbedding is expected to be unique for (article, model, task).
        articles = list(session.scalars(stmt).unique().all())
        if args.max_articles is not None:
            articles = articles[:args.max_articles]
        if not articles:
            raise RuntimeError("No embedded articles in the selected period")

        ids = [int(article.id) for article in articles]
        if len(ids) != len(set(ids)):
            raise RuntimeError("Duplicate article IDs")

        print(f"Loading {len(ids)} embeddings...")
        rows = session.execute(
            select(a.ArticleEmbedding.article_id, a.ArticleEmbedding.embedding)
            .where(a.ArticleEmbedding.article_id.in_(ids),
                   a.ArticleEmbedding.model == a.EMBEDDING_MODEL,
                   a.ArticleEmbedding.task == a.EMBEDDING_TASK)
        ).all()
        vectors_by_id = {}
        for aid, emb in rows:
            if aid in vectors_by_id:
                raise RuntimeError(f"Multiple embeddings for article {aid}")
            vectors_by_id[int(aid)] = a.embedding_to_numpy(emb)
        if set(ids) != set(vectors_by_id):
            raise RuntimeError("Some article embeddings are missing")
        matrix = np.vstack([vectors_by_id[i] for i in ids]).astype(np.float32)
        norms = np.linalg.norm(matrix, axis=1)
        if np.any(norms == 0):
            raise RuntimeError("Zero-length embedding encountered")
        matrix /= norms[:, None]

        print("Loading entities and trained matcher...")
        entity_map = a.load_entities(session, ids)
        matcher = a.load_matcher()
        records = [
            {"id": int(article.id), "time": a.get_effective_time(article),
             "entities": entity_map.get(int(article.id), set()), "matcher": matcher,
             "title": article.title}
            for article in articles
        ]
        times = {r["id"]: r["time"] for r in records}
        if any(t is None for t in times.values()):
            raise RuntimeError("An article has no effective time")

        # Candidate retrieval is independent of simulated event membership:
        # each run chooses from the same top-20 chronologically earlier articles.
        print("Preparing chronological nearest neighbors...")
        neighbors = []
        for i, r in enumerate(records):
            lower = r["time"] - timedelta(hours=a.CANDIDATE_WINDOW_HOURS)
            valid = [j for j in range(i) if records[j]["time"] >= lower]
            if not valid:
                neighbors.append([])
                continue
            sims = matrix[valid] @ matrix[i]
            candidates = [(j, float(s)) for j, s in zip(valid, sims)
                          if s >= a.MIN_RETRIEVAL_SIMILARITY]
            candidates.sort(key=lambda x: (-x[1], records[x[0]]["id"]))
            neighbors.append(candidates[:a.TOP_K_NEIGHBORS])

        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        pair_scores = {}
        summaries = []
        for mode in ("baseline", "quality_first", "quality_72h"):
            print(f"Running {mode}...")
            members, assignment, decisions = run_variant(
                records, matrix, neighbors, pair_scores, mode, args.max_span_hours)
            metrics = summarize_clusters(members, times)
            summaries.append({"mode": mode, "articles": len(ids), **metrics,
                              **dict(decisions)})
            with (out / f"{mode}_assignments.csv").open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["article_id", "simulated_event_seed_article_id", "title"])
                for r in records:
                    writer.writerow([r["id"], assignment[r["id"]], r["title"]])
            with (out / f"{mode}_largest_events.csv").open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["event_seed_article_id", "article_count", "span_hours", "sample_titles"])
                for eid, mids in sorted(members.items(), key=lambda x: -len(x[1]))[:30]:
                    span = (max(times[i] for i in mids) - min(times[i] for i in mids)).total_seconds()/3600
                    titles = " | ".join(r["title"] or "" for r in records if r["id"] in set(mids[:4]))
                    writer.writerow([eid, len(mids), round(span, 1), titles])
            print(mode, metrics, dict(decisions))

        with (out / "summary.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(summaries[0]))
            writer.writeheader()
            writer.writerows(summaries)
        print(f"Results written to {out.resolve()}")
        print("READ-ONLY: no event assignments were changed.")
    finally:
        session.rollback()
        session.close()


if __name__ == "__main__":
    main()
