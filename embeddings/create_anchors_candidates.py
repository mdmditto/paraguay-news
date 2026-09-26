import csv
from pathlib import Path

from sqlalchemy import text

from database.db import SessionLocal


MODEL_NAME = "jinaai/jina-embeddings-v5-text-small"
TASK = "text-matching"

# --------------------------------------------------
# Evaluation sampling
# --------------------------------------------------

ANCHOR_SOURCES = [
    "ABC Color",
    "Última Hora",
    "La Nación",
    "Ñanduti",
    "HOY",
]

# 16 × 5 = 80 anchor targets
TARGETS_PER_ANCHOR = 16

# Additional targets sampled from all other sources
OTHER_TARGETS = 20

# Nearest neighbors for each target
NEIGHBORS = 5

OUTPUT_FILE = Path(
    "embeddings/event_candidates.csv"
)


def get_anchor_targets(session):
    """
    Select the same number of target articles from each
    anchor source.

    Random sampling prevents us from simply taking the
    newest articles from every outlet.
    """

    targets = []

    for source_name in ANCHOR_SOURCES:

        rows = session.execute(
            text(
                """
                SELECT
                    a.id,
                    a.title,
                    a.published_at,
                    s.name AS source
                FROM article_embeddings ae

                JOIN articles a
                    ON a.id = ae.article_id

                JOIN sources s
                    ON s.id = a.source_id

                WHERE ae.model = :model
                  AND ae.task = :task
                  AND s.name = :source_name

                ORDER BY RANDOM()

                LIMIT :limit
                """
            ),
            {
                "model": MODEL_NAME,
                "task": TASK,
                "source_name": source_name,
                "limit": TARGETS_PER_ANCHOR,
            },
        ).mappings().all()

        print(
            f"{source_name}: "
            f"{len(rows)} target articles"
        )

        targets.extend(rows)

    return targets


def get_other_targets(session):
    """
    Sample articles from sources that are not part
    of the anchor group.
    """

    rows = session.execute(
        text(
            """
            SELECT
                a.id,
                a.title,
                a.published_at,
                s.name AS source
            FROM article_embeddings ae

            JOIN articles a
                ON a.id = ae.article_id

            JOIN sources s
                ON s.id = a.source_id

            WHERE ae.model = :model
              AND ae.task = :task

              AND s.name NOT IN (
                  'ABC Color',
                  'Última Hora',
                  'La Nación',
                  'Ñanduti',
                  'HOY'
              )

            ORDER BY RANDOM()

            LIMIT :limit
            """
        ),
        {
            "model": MODEL_NAME,
            "task": TASK,
            "limit": OTHER_TARGETS,
        },
    ).mappings().all()

    print(
        f"Other sources: "
        f"{len(rows)} target articles"
    )

    return rows


def get_neighbors(
    session,
    target_id,
):
    """
    Find the nearest articles to a target.

    IMPORTANT:
    Candidates can come from ANY source,
    including smaller/regional outlets.
    """

    rows = session.execute(
        text(
            """
            SELECT
                candidate.id,
                candidate.title,
                candidate.published_at,
                candidate_source.name AS source,

                1 - (
                    candidate_embedding.embedding
                    <=>
                    target_embedding.embedding
                ) AS similarity

            FROM article_embeddings candidate_embedding

            JOIN articles candidate
                ON candidate.id =
                   candidate_embedding.article_id

            JOIN sources candidate_source
                ON candidate_source.id =
                   candidate.source_id

            CROSS JOIN (
                SELECT embedding
                FROM article_embeddings
                WHERE article_id = :target_id
                  AND model = :model
                  AND task = :task
            ) target_embedding

            WHERE
                candidate_embedding.article_id
                    != :target_id

                AND candidate_embedding.model
                    = :model

                AND candidate_embedding.task
                    = :task

            ORDER BY
                candidate_embedding.embedding
                <=>
                target_embedding.embedding

            LIMIT :neighbors
            """
        ),
        {
            "target_id": target_id,
            "model": MODEL_NAME,
            "task": TASK,
            "neighbors": NEIGHBORS,
        },
    ).mappings().all()

    return rows


def main():

    print("=" * 60)
    print("EVENT CANDIDATE GENERATION")
    print("=" * 60)

    session = SessionLocal()

    try:

        # --------------------------------------------------
        # 1. Select evaluation targets
        # --------------------------------------------------

        print("\nSelecting anchor targets...\n")

        anchor_targets = get_anchor_targets(
            session
        )

        print("\nSelecting other targets...\n")

        other_targets = get_other_targets(
            session
        )

        targets = (
            anchor_targets
            + list(other_targets)
        )

        print()
        print(
            f"Total targets: {len(targets)}"
        )

        # --------------------------------------------------
        # 2. Find nearest neighbors
        # --------------------------------------------------

        rows = []

        print(
            "\nFinding nearest neighbors...\n"
        )

        for i, target in enumerate(
            targets,
            start=1,
        ):

            neighbors = get_neighbors(
                session,
                target["id"],
            )

            for neighbor in neighbors:

                rows.append(
                    {
                        "target_id":
                            target["id"],

                        "target_source":
                            target["source"],

                        "target_title":
                            target["title"],

                        "target_date":
                            target["published_at"],

                        "candidate_id":
                            neighbor["id"],

                        "candidate_source":
                            neighbor["source"],

                        "candidate_title":
                            neighbor["title"],

                        "candidate_date":
                            neighbor["published_at"],

                        "similarity":
                            round(
                                float(
                                    neighbor[
                                        "similarity"
                                    ]
                                ),
                                4,
                            ),

                        # Manual label:
                        #
                        # 2 = same event
                        # 1 = related/follow-up
                        # 0 = different event
                        #
                        "event_label": "",
                    }
                )

            print(
                f"[{i}/{len(targets)}] "
                f"{target['source']} | "
                f"{target['title'][:55]}"
            )

        # --------------------------------------------------
        # 3. Save CSV
        # --------------------------------------------------

        OUTPUT_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with OUTPUT_FILE.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as f:

            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "target_id",
                    "target_source",
                    "target_title",
                    "target_date",
                    "candidate_id",
                    "candidate_source",
                    "candidate_title",
                    "candidate_date",
                    "similarity",
                    "event_label",
                ],
            )

            writer.writeheader()
            writer.writerows(rows)

        print()
        print("=" * 60)
        print("DONE")
        print("=" * 60)

        print(
            f"Targets: {len(targets)}"
        )

        print(
            f"Candidate pairs: {len(rows)}"
        )

        print(
            f"Saved to: {OUTPUT_FILE}"
        )

    finally:

        session.close()


if __name__ == "__main__":
    main()
