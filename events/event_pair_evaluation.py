"""Generate a reproducible human-labeling sample and evaluate two event clusterings.

Only reads benchmark CSVs; never connects to or modifies the production database.

Usage:
 python event_pair_evaluation.py sample --results benchmark_results_v2 --output evaluation --n 200
 # Fill human_label column: 1=same development, 0=different, ?=uncertain
 python event_pair_evaluation.py score --results benchmark_results_v2 --labels evaluation/pairs_to_label.csv
"""
import argparse
import csv
import random
import re
from collections import defaultdict
from pathlib import Path

MODES = ('baseline', 'quality_first')
STOP = {'de','la','el','en','y','a','por','para','del','los','las','un','una','con','que','al','se','su','the','and','of','to','in','on'}


def read_assignments(folder, mode):
    path = folder / f'{mode}_assignments.csv'
    with path.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    required = {'article_id', 'simulated_event_seed_article_id', 'title'}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f'{path}: missing expected columns')
    out = {}
    for row in rows:
        aid = int(row['article_id'])
        if aid in out:
            raise ValueError(f'Duplicate article {aid} in {path}')
        out[aid] = (int(row['simulated_event_seed_article_id']), row['title'])
    return out


def tokens(s):
    return set(t for t in re.findall(r'[^\W_]+', (s or '').lower()) if len(t) > 2 and t not in STOP)


def similarity(x, y):
    a, b = tokens(x), tokens(y)
    return len(a & b) / len(a | b) if a and b else 0


def build_sample(folder, output, n, seed):
    base, quality = (read_assignments(folder, m) for m in MODES)
    if set(base) != set(quality):
        raise ValueError('Baseline and quality-first do not contain identical article IDs')
    ids = sorted(base)
    groups = defaultdict(list)
    for aid in ids:
        groups[quality[aid][0]].append(aid)
    rng = random.Random(seed)
    buckets = defaultdict(dict)

    def add(i, j):
        if i == j: return
        i, j = sorted((i, j))
        bs = base[i][0] == base[j][0]
        qs = quality[i][0] == quality[j][0]
        overlap = similarity(quality[i][1], quality[j][1])
        if bs != qs:
            category = 'disagreement'
        elif bs and qs:
            category = 'both_same'
        elif overlap >= .28:
            category = 'both_different_similar_titles'
        else:
            category = 'both_different_random'
        buckets[category][(i,j)] = overlap

    # Positive candidates: sample within clusters, including large clusters.
    for members in groups.values():
        if len(members) < 2: continue
        pairs = [(members[i], members[j]) for i in range(len(members)) for j in range(i+1,len(members))]
        for i,j in rng.sample(pairs, min(len(pairs), max(10, n // 5))): add(i,j)

    # Catch disagreements even when they are in different quality-first clusters.
    base_groups = defaultdict(list)
    for aid in ids: base_groups[base[aid][0]].append(aid)
    for members in base_groups.values():
        if len(members) < 2: continue
        pairs = [(members[i], members[j]) for i in range(len(members)) for j in range(i+1,len(members))]
        for i,j in rng.sample(pairs, min(len(pairs), max(10, n // 5))): add(i,j)

    # Hard negatives: compare articles with high title overlap, irrespective of clusters.
    # Blocking avoids scanning all O(N^2) pairs.
    inverted = defaultdict(list)
    for aid in ids:
        for token in tokens(quality[aid][1]): inverted[token].append(aid)
    candidate_pairs = set()
    for postings in inverted.values():
        if 2 <= len(postings) <= 120:
            for i in postings:
                for j in postings:
                    if i < j: candidate_pairs.add((i,j))
    ranked = sorted(candidate_pairs, key=lambda ij: similarity(quality[ij[0]][1], quality[ij[1]][1]), reverse=True)
    for i,j in ranked[:max(n * 12, 1500)]: add(i,j)
    for _ in range(n * 15):
        i,j = rng.sample(ids, 2)
        add(i,j)

    targets = {'disagreement': .30, 'both_same': .30,
               'both_different_similar_titles': .30, 'both_different_random': .10}
    selected = []
    chosen = set()
    for category, share in targets.items():
        candidates = list(buckets[category].items())
        rng.shuffle(candidates)
        if category == 'both_different_similar_titles':
            candidates.sort(key=lambda item: -item[1])
        for (i,j), overlap in candidates:
            if len([x for x in selected if x[0] == category]) >= round(n*share): break
            if (i,j) in chosen: continue
            selected.append((category,i,j,overlap)); chosen.add((i,j))
    # Backfill from remaining categories if there are too few disagreements.
    remaining = [(category,i,j,overlap) for category, values in buckets.items()
                 for (i,j),overlap in values.items() if (i,j) not in chosen]
    rng.shuffle(remaining)
    selected += remaining[:max(0,n-len(selected))]
    selected = selected[:n]
    rng.shuffle(selected)
    output.mkdir(parents=True, exist_ok=True)
    path = output / 'pairs_to_label.csv'
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        fields = ['pair_id','category','article_id_1','title_1','article_id_2','title_2',
                  'title_jaccard','baseline_same','quality_first_same','human_label','notes']
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for k,(cat,i,j,overlap) in enumerate(selected,1):
            w.writerow(dict(pair_id=k,category=cat,article_id_1=i,title_1=quality[i][1],
                            article_id_2=j,title_2=quality[j][1],title_jaccard=round(overlap,3),
                            baseline_same=int(base[i][0]==base[j][0]),
                            quality_first_same=int(quality[i][0]==quality[j][0]),
                            human_label='',notes=''))
    print(f'Created {len(selected)} pairs: {path}')
    print('Sample counts:', dict((cat,sum(x[0]==cat for x in selected)) for cat in targets))
    print('LABELING RULE: 1=same specific development; 0=different development; ?=uncertain.')
    print('Do not use the algorithm prediction columns to decide labels.')
    print('IMPORTANT: This is a deliberately enriched sample, not a random population sample.')


def scores(tp, fp, fn, tn):
    precision = tp/(tp+fp) if tp+fp else None
    recall = tp/(tp+fn) if tp+fn else None
    f1 = 2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else None
    return precision, recall, f1, (tp+tn)/(tp+tn+fp+fn)


def evaluate(folder, path):
    base, quality = (read_assignments(folder, m) for m in MODES)
    with path.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    labeled = []
    for row in rows:
        label = (row.get('human_label') or '').strip().lower()
        if label not in ('0','1'): continue
        i,j = int(row['article_id_1']), int(row['article_id_2'])
        if i not in base or j not in base or i not in quality or j not in quality:
            raise ValueError(f'Article missing from benchmark: {i}, {j}')
        labeled.append((i,j,int(label),row.get('category','')))
    if not labeled:
        print('No valid human labels found yet. Fill human_label with 0 or 1.'); return
    print(f'Human-labeled pairs: {len(labeled)} / {len(rows)}; excluded blank/? labels: {len(rows)-len(labeled)}')
    for mode, mapping in [('baseline',base),('quality_first',quality)]:
        tp=fp=fn=tn=0
        for i,j,y,_ in labeled:
            predicted = int(mapping[i][0] == mapping[j][0])
            if predicted and y: tp+=1
            elif predicted and not y: fp+=1
            elif not predicted and y: fn+=1
            else: tn+=1
        p,r,f1,acc = scores(tp,fp,fn,tn)
        fmt = lambda x: 'N/A' if x is None else f'{x:.3f}'
        print(f'\n{mode}: TP={tp}, FP={fp}, FN={fn}, TN={tn}')
        print(f'  Precision={fmt(p)}, Recall={fmt(r)}, F1={fmt(f1)}, Accuracy={fmt(acc)}')
    disagree = [(i,j,y) for i,j,y,_ in labeled if (base[i][0]==base[j][0]) != (quality[i][0]==quality[j][0])]
    print(f'\nLabeled pairs where models disagree: {len(disagree)}')
    if disagree:
        base_wins = sum(int(base[i][0]==base[j][0]) == y for i,j,y in disagree)
        print(f'  Baseline correct: {base_wins}; Quality-first correct: {len(disagree)-base_wins}')
    print('\nCaution: sampling deliberately oversamples difficult cases; metrics are sample-specific,')
    print('not unbiased population pairwise precision/recall or full-clustering accuracy.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('sample'); s.add_argument('--results',type=Path,required=True)
    s.add_argument('--output',type=Path,default=Path('evaluation'))
    s.add_argument('--n',type=int,default=200); s.add_argument('--seed',type=int,default=42)
    e=sub.add_parser('score'); e.add_argument('--results',type=Path,required=True)
    e.add_argument('--labels',type=Path,required=True)
    args=p.parse_args()
    if args.command=='sample':
        if args.n < 4: p.error('--n must be at least 4')
        build_sample(args.results,args.output,args.n,args.seed)
    else: evaluate(args.results,args.labels)

if __name__=='__main__': main()
