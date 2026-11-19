#!/usr/bin/env python3
"""Compare the 10 largest event clusters across benchmark methodologies.

Run:
 python events/compare_top_events.py --results benchmark_results_v2 --output event_review

Writes:
  top10_each_method.csv   : top 10 clusters for each methodology
  aligned_top_events.csv  : each quality-first top-10 event aligned to closest cluster in other methods
  article_membership.csv  : full article-level membership in the aligned comparison
  review.html             : readable side-by-side review in a browser

Alignment is based on shared article IDs, not event seed IDs. No DB writes.
"""
import argparse
import csv
import html
from collections import defaultdict
from pathlib import Path

MODES = ['baseline', 'quality_first', 'quality_72h', 'quality_seed', 'quality_centroid']


def read_clusters(path):
    groups = defaultdict(dict)
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        needed = {'article_id', 'simulated_event_seed_article_id', 'title'}
        if not needed.issubset(reader.fieldnames or []):
            raise ValueError(f'{path}: missing {needed - set(reader.fieldnames or [])}')
        for r in reader:
            aid = int(r['article_id'])
            eid = int(r['simulated_event_seed_article_id'])
            groups[eid][aid] = r.get('title') or ''
    return dict(groups)


def top_clusters(clusters, n=10):
    return sorted(clusters.items(), key=lambda x: (-len(x[1]), x[0]))[:n]


def best_match(anchor_ids, clusters):
    # Select by maximum intersection, then Jaccard, then deterministic ID.
    matches = []
    for eid, members in clusters.items():
        overlap = len(anchor_ids & members.keys())
        if overlap:
            union = len(anchor_ids) + len(members) - overlap
            matches.append((overlap, overlap / union, -eid, eid, members))
    if not matches:
        return None, {}, 0, 0.0
    overlap, jaccard, _, eid, members = max(matches)
    return eid, members, overlap, jaccard


def write_csv(path, rows, columns):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results', default='benchmark_results_v2')
    p.add_argument('--output', default='event_review')
    p.add_argument('--top', type=int, default=10)
    args = p.parse_args()
    results = Path(args.results)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    clusters = {}
    for mode in MODES:
        path = results / f'{mode}_assignments.csv'
        if not path.exists():
            raise FileNotFoundError(f'Missing {path}; run the full benchmark first')
        clusters[mode] = read_clusters(path)

    article_sets = [set().union(*(set(x) for x in c.values())) for c in clusters.values()]
    if any(ids != article_sets[0] for ids in article_sets[1:]):
        raise ValueError('The methodologies have different article universes; cannot compare directly')

    rows_top = []
    for mode in MODES:
        for rank, (eid, members) in enumerate(top_clusters(clusters[mode], args.top), 1):
            titles = list(members.values())
            rows_top.append(dict(method=mode, rank=rank, event_seed_article_id=eid,
                                 article_count=len(members), sample_titles=' | '.join(titles[:6])))
    write_csv(output / 'top10_each_method.csv', rows_top,
              ['method', 'rank', 'event_seed_article_id', 'article_count', 'sample_titles'])

    anchor = top_clusters(clusters['quality_first'], args.top)
    rows_aligned = []
    rows_articles = []
    blocks = []
    for rank, (anchor_eid, anchor_members) in enumerate(anchor, 1):
        anchor_ids = set(anchor_members)
        comparisons = {}
        for mode in MODES:
            eid, members, overlap, jaccard = best_match(anchor_ids, clusters[mode])
            comparisons[mode] = (eid, members, overlap, jaccard)
            rows_aligned.append(dict(reference_rank=rank, reference_event_id=anchor_eid,
                                     reference_size=len(anchor_ids), method=mode,
                                     matched_event_id=eid or '', matched_event_size=len(members),
                                     shared_articles=overlap,
                                     missing_from_matched=len(anchor_ids) - overlap,
                                     additional_in_matched=len(members) - overlap,
                                     jaccard=round(jaccard, 3),
                                     sample_titles=' | '.join(list(members.values())[:5])))
        # Every article in union of the five aligned clusters, including extras.
        union_ids = set().union(*(set(members) for _, members, _, _ in comparisons.values()))
        for aid in sorted(union_ids):
            title = next((members[aid] for _, members, _, _ in comparisons.values() if aid in members), '')
            row = dict(reference_rank=rank, reference_event_id=anchor_eid,
                       article_id=aid, title=title,
                       in_quality_first_reference=int(aid in anchor_ids))
            for mode, (_, members, _, _) in comparisons.items():
                row[f'in_{mode}_matched_event'] = int(aid in members)
            rows_articles.append(row)
        blocks.append((rank, anchor_eid, len(anchor_ids), comparisons, list(anchor_members.values())[:8]))

    write_csv(output / 'aligned_top_events.csv', rows_aligned,
              ['reference_rank', 'reference_event_id', 'reference_size', 'method',
               'matched_event_id', 'matched_event_size', 'shared_articles',
               'missing_from_matched', 'additional_in_matched', 'jaccard', 'sample_titles'])
    write_csv(output / 'article_membership.csv', rows_articles,
              ['reference_rank', 'reference_event_id', 'article_id', 'title',
               'in_quality_first_reference'] + [f'in_{mode}_matched_event' for mode in MODES])

    h = ['<!doctype html><html lang="en"><meta charset="utf-8"><title>Event clustering review</title>',
         '<style>body{font:15px system-ui,Arial;max-width:1250px;margin:35px auto;padding:0 20px;color:#17212c}h1{font-size:28px}h2{margin-top:36px;border-top:1px solid #ddd;padding-top:24px}table{border-collapse:collapse;width:100%;font-size:13px;margin:12px 0}th,td{border:1px solid #ddd;padding:9px;text-align:left;vertical-align:top}th{background:#eaf1f7}tr:nth-child(even){background:#f8fafc}.muted{color:#596879}code{background:#eef2f6;padding:2px 4px}li{margin:5px 0}</style>',
         '<h1>Event matching: top clusters comparison</h1>',
         '<p>Anchor: top events in <b>quality_first</b>. Other methods are matched by greatest shared article membership. '
         'A matching seed ID is <em>not</em> required. High Jaccard means similar article membership; it does not establish semantic correctness.</p>',
         '<p class="muted">Review each group as a real news development. Counts alone are not accuracy measures.</p>']
    for rank, eid, size, comparisons, titles in blocks:
        h.append(f'<h2>#{rank} — reference event {eid} ({size} articles)</h2>')
        h.append('<ul>' + ''.join(f'<li>{html.escape(t)}</li>' for t in titles) + '</ul>')
        h.append('<table><tr><th>Method</th><th>Best matching event</th><th>Size</th><th>Shared</th><th>Missing</th><th>Additional</th><th>Jaccard</th></tr>')
        for mode, (mid, members, shared, jac) in comparisons.items():
            h.append(f'<tr><td>{html.escape(mode)}</td><td>{mid or "—"}</td><td>{len(members)}</td><td>{shared}</td>'
                     f'<td>{size-shared}</td><td>{len(members)-shared}</td><td>{jac:.3f}</td></tr>')
        h.append('</table>')
    h.append('<h2>All top-ten clusters in each method</h2><table><tr><th>Method</th><th>Rank</th><th>Seed</th><th>Size</th><th>Headlines</th></tr>')
    for r in rows_top:
        h.append(f'<tr><td>{r["method"]}</td><td>{r["rank"]}</td><td>{r["event_seed_article_id"]}</td>'
                 f'<td>{r["article_count"]}</td><td>{html.escape(r["sample_titles"])}</td></tr>')
    h.append('</table></html>')
    (output / 'review.html').write_text('\n'.join(h), encoding='utf-8')
    print(f'Compared {len(article_sets[0])} articles across {len(MODES)} methods.')
    print(f'Files written to {output.resolve()}')
    print('Open review.html in your browser; article_membership.csv contains full membership details.')


if __name__ == '__main__':
    main()
