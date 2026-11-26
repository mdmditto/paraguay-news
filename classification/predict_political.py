from pathlib import Path

import joblib
import numpy as np

from sqlalchemy import text
from database.db import SessionLocal


MODEL_PATH = (
    Path(__file__).resolve().parent
    / "models"
    / "political_classifier.joblib"
)

BATCH_SIZE = 2000


def main():

    print("Loading political classifier...")

    artifact = joblib.load(MODEL_PATH)

    model = artifact["model"]

    embedding_model = artifact["embedding_model"]
    task = artifact["task"]
    dimensions = artifact["dimensions"]

    positive_index = list(model.classes_).index(1)

    print("Embedding model:", embedding_model)
    print("Task:", task)
    print("Dimensions:", dimensions)

    select_query = text("""
        SELECT
            a.id AS article_id,
            e.embedding::text AS embedding
        FROM articles a
        JOIN article_embeddings e
            ON a.id = e.article_id
        WHERE a.political_probability IS NULL
          AND e.model = :model
          AND e.task = :task
          AND e.dimensions = :dimensions
        ORDER BY a.id
        LIMIT :batch_size
    """)

    update_query = text("""
        UPDATE articles
        SET political_probability = :probability
        WHERE id = :article_id
          AND political_probability IS NULL
    """)

    total_processed = 0

    with SessionLocal() as session:

        while True:

            rows = session.execute(
                select_query,
                {
                    "model": embedding_model,
                    "task": task,
                    "dimensions": dimensions,
                    "batch_size": BATCH_SIZE
                }
            ).mappings().all()

            if not rows:
                break

            article_ids = [
                row["article_id"]
                for row in rows
            ]

            X = np.stack([
                np.fromstring(
                    row["embedding"].strip("[]"),
                    sep=",",
                    dtype=np.float32
                )
                for row in rows
            ])

            assert X.shape[1] == dimensions
            assert np.isfinite(X).all()

            probabilities = model.predict_proba(X)[
                :, positive_index
            ]

            updates = [
                {
                    "article_id": article_id,
                    "probability": float(probability)
                }
                for article_id, probability
                in zip(article_ids, probabilities)
            ]

            session.execute(
                update_query,
                updates
            )

            session.commit()

            total_processed += len(updates)

            print(
                f"Processed articles: {total_processed:,}",
                flush=True
            )

    print("\nPrediction completed.")
    print(f"Total processed: {total_processed:,}")


if __name__ == "__main__":
    main()