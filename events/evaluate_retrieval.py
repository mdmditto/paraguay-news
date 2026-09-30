import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text


# =========================================================
# PROJECT
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from database.db import engine


# =========================================================
# CONFIG
# =========================================================

DATASET_FILE = (
    PROJECT_ROOT
    / "entities"
    / "event_training_dataset.csv"
)

EMBEDDING_MODEL = "jinaai/jina-embeddings-v5-text-small"
EMBEDDING_TASK = "text-matching"

K_VALUES = [
    5,
    10,
    20,
    30,
    50,
    100,
]

TIME_WINDOWS_HOURS = [
    24,
    48,
    72,
    120,
    168,   # 7 days
    None,  # no temporal restriction
]


# =========================================================
# LOAD LABELED SAME-EVENT PAIRS
# =========================================================

def load_same_event_pairs():
    df = pd.read_csv(DATASET_FILE)

    df = df[
        df["event_label"] == 2
    ].copy()

    pairs = []

    for row in df.itertuples():
        pairs.append(
            (
                int(row.target_id),
                int(row.candidate_id),
            )
        )

    return pairs


# =========================================================
# LOAD ARTICLE METADATA
# =========================================================

def load_articles(article_ids):
    query = text(
        """
        SELECT
            a.id,
            a.published_at
        FROM articles a
        WHERE a.id = ANY(:article_ids)
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(
            query,
            {
                "article_ids": list(article_ids)
            },
        ).mappings().all()

    return {
        int(row["id"]): row["published_at"]
        for row in rows
    }


# =========================================================
# LOAD EMBEDDINGS
# =========================================================

def load_embeddings():
    """
    Load all embeddings once.

    ~20k x 1024 float32 is around 80 MB,
    so this is reasonable for the current dataset.
    """

    query = text(
        """
        SELECT
            article_id,
            embedding
        FROM article_embeddings
        WHERE model = :model
          AND task = :task
        ORDER BY article_id
        """
    )

    ids = []
    vectors = []

    with engine.connect() as conn:
        rows = conn.execute(
            query,
            {
                "model": EMBEDDING_MODEL,
                "task": EMBEDDING_TASK,
            },
        )

        for row in rows:
            ids.append(
                int(row.article_id)
            )

            embedding = row.embedding

            # pgvector may arrive as a string depending
            # on the driver/query path.
            if isinstance(embedding, str):
                embedding = np.fromstring(
                    embedding.strip("[]"),
                    sep=",",
                    dtype=np.float32,
                )

            else:
                embedding = np.asarray(
                    embedding,
                    dtype=np.float32,
                )

            vectors.append(
                embedding
            )

    ids = np.asarray(
        ids,
        dtype=np.int64,
    )

    matrix = np.vstack(
        vectors
    ).astype(
        np.float32
    )

    # Jina embeddings should already be normalized,
    # but normalize again defensively.
    norms = np.linalg.norm(
        matrix,
        axis=1,
        keepdims=True,
    )

    norms[
        norms == 0
    ] = 1

    matrix = matrix / norms

    id_to_index = {
        int(article_id): index
        for index, article_id
        in enumerate(ids)
    }

    print(
        f"Embeddings loaded: {len(ids)}"
    )

    return (
        ids,
        matrix,
        id_to_index,
    )


# =========================================================
# BUILD SAME-EVENT PARTNER MAP
# =========================================================

def build_partner_map(pairs):
    """
    If A-B is labeled same-event, then A is a known
    partner of B and B is a known partner of A.
    """

    partners = defaultdict(set)

    for article_a, article_b in pairs:
        partners[
            article_a
        ].add(
            article_b
        )

        partners[
            article_b
        ].add(
            article_a
        )

    return partners


# =========================================================
# EVALUATE
# =========================================================

def evaluate_window(
    window_hours,
    ids,
    matrix,
    id_to_index,
    published_at,
    partners,
):
    results = []

    for target_id, known_partners in partners.items():

        if target_id not in id_to_index:
            continue

        target_time = published_at.get(
            target_id
        )

        if target_time is None:
            continue

        # ---------------------------------------------
        # Only earlier known same-event partners count.
        #
        # This simulates incremental production:
        # future articles cannot be retrieved.
        # ---------------------------------------------

        earlier_partners = []

        for partner_id in known_partners:

            partner_time = published_at.get(
                partner_id
            )

            if partner_time is None:
                continue

            # Deterministic tie breaking by ID when two
            # timestamps are identical.
            if (
                partner_time < target_time
                or (
                    partner_time == target_time
                    and partner_id < target_id
                )
            ):
                earlier_partners.append(
                    partner_id
                )

        if not earlier_partners:
            continue

        target_index = id_to_index[
            target_id
        ]

        target_vector = matrix[
            target_index
        ]

        # ---------------------------------------------
        # Candidate mask
        # ---------------------------------------------

        candidate_indices = []

        for index, article_id in enumerate(ids):

            article_id = int(
                article_id
            )

            if article_id == target_id:
                continue

            candidate_time = published_at.get(
                article_id
            )

            if candidate_time is None:
                continue

            # Must already exist at target time.
            if (
                candidate_time > target_time
            ):
                continue

            if (
                candidate_time == target_time
                and article_id >= target_id
            ):
                continue

            if window_hours is not None:

                delta_hours = (
                    target_time
                    - candidate_time
                ).total_seconds() / 3600

                if (
                    delta_hours < 0
                    or delta_hours > window_hours
                ):
                    continue

            candidate_indices.append(
                index
            )

        if not candidate_indices:
            continue

        candidate_indices = np.asarray(
            candidate_indices,
            dtype=np.int64,
        )

        similarities = (
            matrix[
                candidate_indices
            ]
            @ target_vector
        )

        order = np.argsort(
            -similarities
        )

        ranked_indices = (
            candidate_indices[
                order
            ]
        )

        ranked_ids = [
            int(ids[index])
            for index in ranked_indices
        ]

        rank_lookup = {
            article_id: rank
            for rank, article_id
            in enumerate(
                ranked_ids,
                start=1,
            )
        }

        partner_ranks = []

        eligible_partners = []

        for partner_id in earlier_partners:

            partner_time = published_at.get(
                partner_id
            )

            if window_hours is not None:

                delta_hours = (
                    target_time
                    - partner_time
                ).total_seconds() / 3600

                if delta_hours > window_hours:
                    continue

            eligible_partners.append(
                partner_id
            )

            rank = rank_lookup.get(
                partner_id
            )

            if rank is not None:
                partner_ranks.append(
                    rank
                )

        # There was a previous same-event article,
        # but the time window itself excluded all of them.
        window_has_partner = (
            len(eligible_partners) > 0
        )

        best_rank = (
            min(partner_ranks)
            if partner_ranks
            else None
        )

        results.append(
            {
                "target_id": target_id,
                "known_previous_partners": len(
                    earlier_partners
                ),
                "eligible_partners": len(
                    eligible_partners
                ),
                "window_has_partner": (
                    window_has_partner
                ),
                "best_rank": best_rank,
            }
        )

    return pd.DataFrame(
        results
    )


# =========================================================
# REPORT
# =========================================================

def report_window(
    window_hours,
    results,
):
    if results.empty:
        return

    label = (
        "ALL"
        if window_hours is None
        else f"{window_hours}h"
    )

    total = len(
        results
    )

    window_recall = (
        results[
            "window_has_partner"
        ].mean()
    )

    print()
    print("=" * 78)
    print(
        f"TIME WINDOW: {label}"
    )
    print("=" * 78)

    print(
        f"Targets evaluated: {total}"
    )

    print(
        "Window contains >=1 known "
        f"same-event partner: "
        f"{window_recall:.2%}"
    )

    print()

    print(
        "Retrieval recall:"
    )

    for k in K_VALUES:

        retrieved = (
            results[
                "best_rank"
            ].notna()
            & (
                results[
                    "best_rank"
                ] <= k
            )
        )

        recall = retrieved.mean()

        print(
            f"  K={k:<3d} "
            f"{recall:.2%}"
        )

    valid_ranks = (
        results[
            "best_rank"
        ].dropna()
    )

    if len(valid_ranks) > 0:

        print()
        print(
            "Best same-event partner rank:"
        )

        print(
            f"  median: "
            f"{valid_ranks.median():.1f}"
        )

        print(
            f"  p90:    "
            f"{valid_ranks.quantile(0.90):.1f}"
        )

        print(
            f"  p95:    "
            f"{valid_ranks.quantile(0.95):.1f}"
        )

        print(
            f"  max:    "
            f"{valid_ranks.max():.0f}"
        )


# =========================================================
# TIME-DIFFERENCE REPORT
# =========================================================

def report_pair_time_differences(
    pairs,
    published_at,
):
    differences = []

    for article_a, article_b in pairs:

        time_a = published_at.get(
            article_a
        )

        time_b = published_at.get(
            article_b
        )

        if (
            time_a is None
            or time_b is None
        ):
            continue

        hours = abs(
            (
                time_a - time_b
            ).total_seconds()
        ) / 3600

        differences.append(
            hours
        )

    values = np.asarray(
        differences,
        dtype=float,
    )

    print()
    print("=" * 78)
    print(
        "SAME-EVENT TEMPORAL DISTANCE"
    )
    print("=" * 78)

    print(
        f"Pairs: {len(values)}"
    )

    if len(values) == 0:
        return

    print(
        f"Median: "
        f"{np.median(values):.2f} h"
    )

    print(
        f"P75:    "
        f"{np.quantile(values, 0.75):.2f} h"
    )

    print(
        f"P90:    "
        f"{np.quantile(values, 0.90):.2f} h"
    )

    print(
        f"P95:    "
        f"{np.quantile(values, 0.95):.2f} h"
    )

    print(
        f"P99:    "
        f"{np.quantile(values, 0.99):.2f} h"
    )

    print(
        f"Max:    "
        f"{np.max(values):.2f} h"
    )


# =========================================================
# MAIN
# =========================================================

def main():

    pairs = load_same_event_pairs()

    print(
        f"Same-event labeled pairs: "
        f"{len(pairs)}"
    )

    labeled_article_ids = set()

    for article_a, article_b in pairs:
        labeled_article_ids.add(
            article_a
        )
        labeled_article_ids.add(
            article_b
        )

    # We need timestamps for all embedded articles because
    # they form the retrieval candidate pool.

    (
        ids,
        matrix,
        id_to_index,
    ) = load_embeddings()

    published_at = load_articles(
        set(
            int(article_id)
            for article_id in ids
        )
    )

    partners = build_partner_map(
        pairs
    )

    report_pair_time_differences(
        pairs,
        published_at,
    )

    summary_rows = []

    for window_hours in TIME_WINDOWS_HOURS:

        results = evaluate_window(
            window_hours=window_hours,
            ids=ids,
            matrix=matrix,
            id_to_index=id_to_index,
            published_at=published_at,
            partners=partners,
        )

        report_window(
            window_hours,
            results,
        )

        label = (
            "ALL"
            if window_hours is None
            else str(window_hours)
        )

        for k in K_VALUES:

            if results.empty:
                recall = np.nan

            else:

                retrieved = (
                    results[
                        "best_rank"
                    ].notna()
                    & (
                        results[
                            "best_rank"
                        ] <= k
                    )
                )

                recall = (
                    retrieved.mean()
                )

            summary_rows.append(
                {
                    "window_hours": label,
                    "k": k,
                    "retrieval_recall": recall,
                }
            )

    output = pd.DataFrame(
        summary_rows
    )

    output_file = (
        PROJECT_ROOT
        / "events"
        / "retrieval_evaluation.csv"
    )

    output.to_csv(
        output_file,
        index=False,
    )

    print()
    print("=" * 78)
    print("DONE")
    print("=" * 78)

    print(
        f"Saved: {output_file}"
    )


if __name__ == "__main__":
    main()
