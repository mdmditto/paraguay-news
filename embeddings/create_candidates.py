import csv
from pathlib import Path

from sqlalchemy import text

from database.db import SessionLocal


MODEL_NAME = "jinaai/jina-embeddings-v5-text-small"
TASK = "text-matching"

# How many target articles to evaluate
TARGET_LIMIT = 100

# Nearest neighbors per target
NEIGHBORS = 5

OUTPUT_FILE = Path("embeddings/event_candidates.csv")


def main():

    session = SessionLocal()

    try:

        # --------------------------------------------------
        # Select target articles
        # --------------------------------------------------

        targets = session.execute(
            text(
                """
                SELECT
                    a.id,
                    a.title,
                    a.published_at
                FROM article_embeddings ae
                JOIN articles a
                    ON a.id = ae.article_id
                WHERE ae.model = :model
                  AND ae.task = :task
                ORDER BY a.published_at DESC NULLS LAST
                LIMIT :limit
                """
            ),
            {
                "model": MODEL_NAME,
                "task": TASK,
                "limit": TARGET_LIMIT,
            },
        ).mappings().all()

        print(f"Target articles: {len(targets)}")

        rows = []

        # --------------------------------------------------
        # Find nearest neighbors for every target
        # --------------------------------------------------

        for i, target in enumerate(targets, start=1):

            neighbors = session.execute(
                text(
                    """
                    SELECT
                        candidate.id,
                        candidate.title,
                        candidate.published_at,

                        1 - (
                            candidate_embedding.embedding
                            <=>
                            target_embedding.embedding
                        ) AS similarity

                    FROM article_embeddings candidate_embedding

                    JOIN articles candidate
                        ON candidate.id =
                           candidate_embedding.article_id

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
                    "target_id": target["id"],
                    "model": MODEL_NAME,
                    "task": TASK,
                    "neighbors": NEIGHBORS,
                },
            ).mappings().all()

            for neighbor in neighbors:

                rows.append(
                    {
                        "target_id": target["id"],
                        "target_title": target["title"],
                        "target_date": target["published_at"],

                        "candidate_id": neighbor["id"],
                        "candidate_title": neighbor["title"],
                        "candidate_date": neighbor["published_at"],

                        "similarity": round(
                            float(neighbor["similarity"]),
                            4,
                        ),

                        # You will fill this manually
                        "event_label": "",
                    }
                )

            print(
                f"[{i}/{len(targets)}] "
                f"{target['title'][:60]}"
            )

        # --------------------------------------------------
        # Save CSV
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
                    "target_title",
                    "target_date",
                    "candidate_id",
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

        print(f"Candidate pairs: {len(rows)}")
        print(f"Saved to: {OUTPUT_FILE}")

    finally:

        session.close()


if __name__ == "__main__":
    main()
