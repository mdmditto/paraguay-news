import csv
import random
from collections import defaultdict
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from database.db import SessionLocal


# =========================================================
# CONFIGURATION
# =========================================================

MODEL_NAME = "jinaai/jina-embeddings-v5-text-small"
TASK = "text-matching"

# Previous labeled datasets.
#
# The script will use these files to:
#   1. exclude already-labeled pairs
#   2. avoid reusing old target articles when possible
#
PREVIOUS_FILES = [
    Path("embeddings/event_candidates_2.csv"),
]

OUTPUT_FILE = Path(
    "embeddings/event_candidates_3.csv"
)


# ---------------------------------------------------------
# Target sampling
# ---------------------------------------------------------

ANCHOR_SOURCES = [
    "ABC Color",
    "Última Hora",
    "La Nación",
    "Ñanduti",
    "HOY",
]

# Number of NEW target articles from each major source
TARGETS_PER_ANCHOR = 10

# Additional targets from all other sources
OTHER_TARGETS = 20

# 5 * 10 + 20 = 70 target articles maximum


# ---------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------

# Retrieve more neighbors than we ultimately need.
# This gives us room to select useful/difficult examples.
NEAREST_NEIGHBORS = 20

# Maximum number of candidate pairs kept for one target.
MAX_PAIRS_PER_TARGET = 4

# Approximate desired output.
TARGET_PAIR_COUNT = 220


# ---------------------------------------------------------
# Similarity ranges
# ---------------------------------------------------------

# We now care much more about difficult examples than
# obviously unrelated pairs.

MIN_SIMILARITY = 0.78

# Similarity bands:
#
# hard_high   = extremely similar
# hard_mid    = most interesting boundary region
# hard_low    = lower boundary region
# easy        = useful negatives, but fewer needed

SIMILARITY_BANDS = {
    "very_high": (0.95, 1.00001),
    "high":      (0.90, 0.95),
    "middle":    (0.85, 0.90),
    "low":       (0.80, 0.85),
    "very_low":  (0.78, 0.80),
}


# Desired approximate composition.
#
# These are weights, not strict quotas.
BAND_WEIGHTS = {
    "very_high": 0.15,
    "high":      0.30,
    "middle":    0.30,
    "low":       0.20,
    "very_low":  0.05,
}


RANDOM_SEED = 42

random.seed(RANDOM_SEED)


# =========================================================
# CSV LOADING
# =========================================================

def read_csv_safely(path: Path):
    """
    Read CSV files produced either directly by Python or
    edited/saved through Excel.

    Handles UTF-8, Windows-1252 and common delimiters.
    """

    encodings = [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin1",
    ]

    for encoding in encodings:

        try:

            with open(
                path,
                "r",
                encoding=encoding,
                newline="",
            ) as f:

                sample = f.read(10000)

            try:

                dialect = csv.Sniffer().sniff(
                    sample,
                    delimiters=",;\t|",
                )

                delimiter = dialect.delimiter

            except csv.Error:

                first_line = (
                    sample.splitlines()[0]
                )

                candidates = {
                    ",": first_line.count(","),
                    ";": first_line.count(";"),
                    "\t": first_line.count("\t"),
                    "|": first_line.count("|"),
                }

                delimiter = max(
                    candidates,
                    key=candidates.get,
                )

            df = pd.read_csv(
                path,
                encoding=encoding,
                sep=delimiter,
                engine="python",
            )

            print(
                f"Loaded {path}: "
                f"encoding={encoding}, "
                f"delimiter={repr(delimiter)}, "
                f"rows={len(df)}"
            )

            return df

        except UnicodeDecodeError:
            continue

        except pd.errors.ParserError:
            continue

    raise RuntimeError(
        f"Could not read CSV: {path}"
    )


# =========================================================
# PREVIOUS LABELS
# =========================================================

def load_previous_data():
    """
    Return:
      - previously used pairs
      - previously used target IDs

    Pair order is normalized so:
        A-B == B-A

    This prevents us from labeling the same article pair
    twice in reversed order.
    """

    previous_pairs = set()
    previous_targets = set()

    for path in PREVIOUS_FILES:

        if not path.exists():

            print(
                f"Previous file not found, skipping: "
                f"{path}"
            )

            continue

        df = read_csv_safely(
            path
        )

        required = {
            "target_id",
            "candidate_id",
        }

        if not required.issubset(
            df.columns
        ):

            print(
                f"Skipping {path}: "
                "missing target_id/candidate_id"
            )

            continue

        for _, row in df.iterrows():

            try:

                target_id = int(
                    row["target_id"]
                )

                candidate_id = int(
                    row["candidate_id"]
                )

            except (
                ValueError,
                TypeError,
            ):
                continue

            previous_targets.add(
                target_id
            )

            pair = tuple(
                sorted(
                    [
                        target_id,
                        candidate_id,
                    ]
                )
            )

            previous_pairs.add(
                pair
            )

    return (
        previous_pairs,
        previous_targets,
    )


# =========================================================
# GET TARGET ARTICLES
# =========================================================

def get_anchor_targets(
    session,
    source_name,
    previous_targets,
    limit,
):
    """
    Select new target articles from one anchor source.

    Only articles with embeddings are eligible.
    """

    stmt = text(
        """
        SELECT
            a.id,
            a.title,
            a.published_at,
            s.name AS source_name

        FROM articles a

        JOIN sources s
            ON s.id = a.source_id

        JOIN article_embeddings ae
            ON ae.article_id = a.id

        WHERE
            ae.model = :model
            AND ae.task = :task
            AND s.name = :source_name

        ORDER BY RANDOM()

        LIMIT :search_limit
        """
    )

    # Ask PostgreSQL for extra rows because some may have
    # been used as targets previously.
    rows = session.execute(
        stmt,
        {
            "model": MODEL_NAME,
            "task": TASK,
            "source_name": source_name,
            "search_limit": limit * 10,
        },
    ).mappings().all()

    selected = []

    for row in rows:

        article_id = int(
            row["id"]
        )

        if article_id in previous_targets:
            continue

        selected.append(
            dict(row)
        )

        if len(selected) >= limit:
            break

    return selected


def get_other_targets(
    session,
    previous_targets,
    already_selected,
    limit,
):
    """
    Select targets from sources outside the five major
    anchor outlets.
    """

    stmt = text(
        """
        SELECT
            a.id,
            a.title,
            a.published_at,
            s.name AS source_name

        FROM articles a

        JOIN sources s
            ON s.id = a.source_id

        JOIN article_embeddings ae
            ON ae.article_id = a.id

        WHERE
            ae.model = :model
            AND ae.task = :task
            AND s.name != ALL(:anchor_sources)

        ORDER BY RANDOM()

        LIMIT :search_limit
        """
    )

    rows = session.execute(
        stmt,
        {
            "model": MODEL_NAME,
            "task": TASK,
            "anchor_sources": ANCHOR_SOURCES,
            "search_limit": limit * 15,
        },
    ).mappings().all()

    selected = []

    excluded = (
        set(previous_targets)
        | set(already_selected)
    )

    for row in rows:

        article_id = int(
            row["id"]
        )

        if article_id in excluded:
            continue

        selected.append(
            dict(row)
        )

        excluded.add(
            article_id
        )

        if len(selected) >= limit:
            break

    return selected


def get_targets(
    session,
    previous_targets,
):
    """
    Construct a diverse set of NEW target articles.
    """

    targets = []

    selected_ids = set()

    print()
    print("Selecting anchor targets...")

    for source_name in ANCHOR_SOURCES:

        source_targets = (
            get_anchor_targets(
                session,
                source_name,
                previous_targets,
                TARGETS_PER_ANCHOR,
            )
        )

        for target in source_targets:

            article_id = int(
                target["id"]
            )

            if article_id in selected_ids:
                continue

            targets.append(
                target
            )

            selected_ids.add(
                article_id
            )

        print(
            f"  {source_name}: "
            f"{len(source_targets)}"
        )

    print()
    print(
        "Selecting targets from other sources..."
    )

    other_targets = get_other_targets(
        session,
        previous_targets,
        selected_ids,
        OTHER_TARGETS,
    )

    targets.extend(
        other_targets
    )

    print(
        f"  Other sources: "
        f"{len(other_targets)}"
    )

    return targets


# =========================================================
# NEAREST NEIGHBORS
# =========================================================

def get_neighbors(
    session,
    target_id,
):
    """
    Find nearest articles using pgvector cosine distance.

    Candidate articles may come from ANY source.

    We intentionally retrieve more neighbors than needed
    because later we select candidates according to their
    information value.
    """

    stmt = text(
        """
        SELECT
            candidate.id AS candidate_id,
            candidate.title AS candidate_title,
            candidate.published_at
                AS candidate_published_at,

            candidate_source.name
                AS candidate_source,

            1 - (
                candidate_embedding.embedding
                <=>
                target_embedding.embedding
            ) AS similarity

        FROM article_embeddings
            AS target_embedding

        JOIN article_embeddings
            AS candidate_embedding
            ON candidate_embedding.model
                = target_embedding.model
            AND candidate_embedding.task
                = target_embedding.task

        JOIN articles candidate
            ON candidate.id
                = candidate_embedding.article_id

        JOIN sources candidate_source
            ON candidate_source.id
                = candidate.source_id

        WHERE
            target_embedding.article_id
                = :target_id

            AND target_embedding.model
                = :model

            AND target_embedding.task
                = :task

            AND candidate_embedding.article_id
                != :target_id

        ORDER BY
            candidate_embedding.embedding
            <=>
            target_embedding.embedding

        LIMIT :limit
        """
    )

    rows = session.execute(
        stmt,
        {
            "target_id": target_id,
            "model": MODEL_NAME,
            "task": TASK,
            "limit": NEAREST_NEIGHBORS,
        },
    ).mappings().all()

    return [
        dict(row)
        for row in rows
    ]


# =========================================================
# SIMILARITY BAND
# =========================================================

def get_similarity_band(
    similarity,
):
    """
    Assign a candidate pair to a similarity interval.
    """

    for band, (
        minimum,
        maximum,
    ) in SIMILARITY_BANDS.items():

        if (
            similarity >= minimum
            and similarity < maximum
        ):

            return band

    return None


# =========================================================
# GENERATE ALL ELIGIBLE PAIRS
# =========================================================

def generate_candidate_pool(
    session,
    targets,
    previous_pairs,
):
    """
    Build a large pool of possible labeling pairs.
    """

    pool = []

    new_pairs_seen = set()

    print()
    print("Finding nearest neighbors...")

    for index, target in enumerate(
        targets,
        start=1,
    ):

        target_id = int(
            target["id"]
        )

        neighbors = get_neighbors(
            session,
            target_id,
        )

        valid_for_target = []

        for neighbor in neighbors:

            candidate_id = int(
                neighbor[
                    "candidate_id"
                ]
            )

            similarity = float(
                neighbor[
                    "similarity"
                ]
            )

            if similarity < MIN_SIMILARITY:
                continue

            pair_key = tuple(
                sorted(
                    [
                        target_id,
                        candidate_id,
                    ]
                )
            )

            # Already manually inspected
            if pair_key in previous_pairs:
                continue

            # Avoid duplicate pairs in this batch
            if pair_key in new_pairs_seen:
                continue

            band = get_similarity_band(
                similarity
            )

            if band is None:
                continue

            row = {
                "target_id":
                    target_id,

                "target_source":
                    target["source_name"],

                "target_title":
                    target["title"],

                "target_published_at":
                    target["published_at"],

                "candidate_id":
                    candidate_id,

                "candidate_source":
                    neighbor[
                        "candidate_source"
                    ],

                "candidate_title":
                    neighbor[
                        "candidate_title"
                    ],

                "candidate_published_at":
                    neighbor[
                        "candidate_published_at"
                    ],

                "similarity":
                    round(
                        similarity,
                        4,
                    ),

                "similarity_band":
                    band,

                # Leave this blank for manual labeling.
                "event_label":
                    "",
            }

            valid_for_target.append(
                row
            )

        # -------------------------------------------------
        # Avoid allowing one target to dominate the dataset.
        # -------------------------------------------------

        # Prefer the candidates nearest to the difficult
        # decision region while maintaining some diversity.
        valid_for_target.sort(
            key=lambda x: abs(
                x["similarity"]
                - 0.89
            )
        )

        selected_for_target = (
            valid_for_target[
                :MAX_PAIRS_PER_TARGET
            ]
        )

        for row in selected_for_target:

            pair_key = tuple(
                sorted(
                    [
                        row["target_id"],
                        row["candidate_id"],
                    ]
                )
            )

            new_pairs_seen.add(
                pair_key
            )

            pool.append(
                row
            )

        if index % 10 == 0:

            print(
                f"  Targets processed: "
                f"{index}/{len(targets)}"
            )

    return pool


# =========================================================
# BALANCED BAND SAMPLING
# =========================================================

def select_final_pairs(
    pool,
):
    """
    Select approximately TARGET_PAIR_COUNT examples,
    emphasizing the difficult similarity bands.
    """

    by_band = defaultdict(list)

    for row in pool:

        by_band[
            row["similarity_band"]
        ].append(
            row
        )

    print()
    print("Candidate pool by similarity band:")

    for band in SIMILARITY_BANDS:

        print(
            f"  {band:10s}: "
            f"{len(by_band[band])}"
        )

    selected = []
    selected_keys = set()

    # -----------------------------------------------------
    # First pass: desired quotas
    # -----------------------------------------------------

    for band in SIMILARITY_BANDS:

        rows = by_band[
            band
        ]

        random.shuffle(
            rows
        )

        desired = round(
            TARGET_PAIR_COUNT
            * BAND_WEIGHTS[band]
        )

        for row in rows[:desired]:

            key = (
                row["target_id"],
                row["candidate_id"],
            )

            if key in selected_keys:
                continue

            selected.append(
                row
            )

            selected_keys.add(
                key
            )

    # -----------------------------------------------------
    # Second pass:
    # Fill remaining slots from unused candidates.
    #
    # Prefer examples close to our difficult region.
    # -----------------------------------------------------

    if len(selected) < TARGET_PAIR_COUNT:

        remaining = []

        for row in pool:

            key = (
                row["target_id"],
                row["candidate_id"],
            )

            if key in selected_keys:
                continue

            remaining.append(
                row
            )

        remaining.sort(
            key=lambda x: abs(
                x["similarity"]
                - 0.89
            )
        )

        for row in remaining:

            if (
                len(selected)
                >= TARGET_PAIR_COUNT
            ):
                break

            key = (
                row["target_id"],
                row["candidate_id"],
            )

            selected.append(
                row
            )

            selected_keys.add(
                key
            )

    return selected


# =========================================================
# FINAL DIVERSITY PASS
# =========================================================

def enforce_target_limit(
    rows,
):
    """
    Safety check to ensure no target contributes more than
    MAX_PAIRS_PER_TARGET examples.
    """

    counts = defaultdict(int)

    final = []

    for row in rows:

        target_id = row[
            "target_id"
        ]

        if (
            counts[target_id]
            >= MAX_PAIRS_PER_TARGET
        ):
            continue

        final.append(
            row
        )

        counts[target_id] += 1

    return final


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 72)
    print("ACTIVE-LEARNING EVENT CANDIDATE GENERATOR")
    print("=" * 72)

    print()
    print(
        "Loading previous labeling data..."
    )

    (
        previous_pairs,
        previous_targets,
    ) = load_previous_data()

    print()
    print(
        f"Previous pairs: "
        f"{len(previous_pairs)}"
    )

    print(
        f"Previous target articles: "
        f"{len(previous_targets)}"
    )

    session = SessionLocal()

    try:

        # -------------------------------------------------
        # New target articles
        # -------------------------------------------------

        targets = get_targets(
            session,
            previous_targets,
        )

        print()
        print(
            f"New target articles: "
            f"{len(targets)}"
        )

        if not targets:

            raise RuntimeError(
                "No new target articles were found."
            )

        # -------------------------------------------------
        # Candidate pool
        # -------------------------------------------------

        pool = generate_candidate_pool(
            session,
            targets,
            previous_pairs,
        )

        print()
        print(
            f"Eligible candidate pairs: "
            f"{len(pool)}"
        )

        if not pool:

            raise RuntimeError(
                "No eligible candidate pairs were found."
            )

        # -------------------------------------------------
        # Select informative pairs
        # -------------------------------------------------

        selected = select_final_pairs(
            pool
        )

        selected = enforce_target_limit(
            selected
        )

    finally:

        session.close()

    # -----------------------------------------------------
    # Sort for manual labeling
    #
    # Keep pairs from the same target together.
    # -----------------------------------------------------

    selected.sort(
        key=lambda x: (
            x["target_source"],
            x["target_id"],
            -x["similarity"],
        )
    )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df = pd.DataFrame(
        selected
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    print()
    print("=" * 72)
    print("FINAL LABELING BATCH")
    print("=" * 72)

    print(
        f"Pairs generated: "
        f"{len(df)}"
    )

    print(
        f"Unique target articles: "
        f"{df['target_id'].nunique()}"
    )

    print(
        f"Unique candidate articles: "
        f"{df['candidate_id'].nunique()}"
    )

    print()

    print(
        "Pairs by similarity band:"
    )

    print(
        df[
            "similarity_band"
        ]
        .value_counts()
        .reindex(
            SIMILARITY_BANDS.keys(),
            fill_value=0,
        )
        .to_string()
    )

    print()
    print(
        "Targets by source:"
    )

    print(
        df[
            "target_source"
        ]
        .value_counts()
        .to_string()
    )

    print()
    print(
        "Similarity summary:"
    )

    print(
        df["similarity"]
        .describe()
        .round(4)
        .to_string()
    )

    print()
    print(
        f"Saved to: "
        f"{OUTPUT_FILE}"
    )

    print()
    print(
        "Manual labels:"
    )

    print(
        "  0 = different event"
    )

    print(
        "  1 = related/follow-up, "
        "but different event"
    )

    print(
        "  2 = same event"
    )


if __name__ == "__main__":
    main()
