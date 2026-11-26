from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sqlalchemy import text

from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    average_precision_score
)

from database.db import SessionLocal


RANDOM_STATE = 42

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PATH = MODEL_DIR / "political_classifier.joblib"

NEGATIVE_CATEGORIES = [
    "Deportes",
    "Estilo de Vida",
    "Cultura y Entretenimiento",
    "Tecnología y Ciencia"
]


def load_training_data():

    query = text("""
        SELECT
            a.id AS article_id,
            a.title,
            a.category,
            s.name AS source,
            e.model AS embedding_model,
            e.embedding::text AS embedding,

            CASE
                WHEN a.category = 'Política' THEN 1
                ELSE 0
            END AS label

        FROM articles a

        JOIN article_embeddings e
            ON a.id = e.article_id

        JOIN sources s
            ON a.source_id = s.id

        WHERE (
            a.category = 'Política'
            OR a.category = ANY(:negative_categories)
        )

        AND e.dimensions = 1024
        AND e.task = 'text-matching'

        ORDER BY a.id
    """)

    with SessionLocal() as session:

        result = session.execute(
            query,
            {"negative_categories": NEGATIVE_CATEGORIES}
        )

        df = pd.DataFrame(result.mappings().all())

    return df


def create_model():

    return LogisticRegression(
        max_iter=2000,
        class_weight="balanced",
        random_state=RANDOM_STATE
    )


def evaluate_model(model, X_test, y_test):

    predictions = model.predict(X_test)
    probabilities = model.predict_proba(X_test)[:, 1]

    print("\nClassification report:")

    print(classification_report(
        y_test,
        predictions,
        labels=[0, 1],
        target_names=["No política", "Política"],
        digits=4,
        zero_division=0
    ))

    print("\nConfusion matrix:")

    print(confusion_matrix(
        y_test,
        predictions,
        labels=[0, 1]
    ))

    print(
        "\nROC-AUC:",
        round(roc_auc_score(y_test, probabilities), 4)
    )

    print(
        "Average Precision:",
        round(average_precision_score(
            y_test,
            probabilities
        ), 4)
    )


def main():

    print("Loading training dataset...")

    df = load_training_data()

    print("\nTotal articles:", len(df))

    print("\nClass distribution:")
    print(df["label"].value_counts())

    print("\nSource distribution:")
    print(pd.crosstab(df["source"], df["label"]))

    # Verify embedding consistency
    assert df["embedding_model"].nunique() == 1
    assert df["article_id"].is_unique

    # Convert PostgreSQL vectors into NumPy arrays
    X = np.stack([
        np.fromstring(
            embedding.strip("[]"),
            sep=",",
            dtype=np.float32
        )
        for embedding in df["embedding"]
    ])

    y = df["label"].to_numpy()

    assert X.shape[1] == 1024
    assert np.isfinite(X).all()

    print("\nEmbedding matrix:", X.shape)
    print("Target vector:", y.shape)

    # Random stratified train-test split
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        stratify=y,
        random_state=RANDOM_STATE
    )

    print("\nTraining articles:", len(X_train))
    print("Testing articles:", len(X_test))

    model = create_model()

    print("\nTraining Logistic Regression...")

    model.fit(X_train, y_train)

    print("\n=== RANDOM SPLIT EVALUATION ===")

    evaluate_model(model, X_test, y_test)

    # Cross-source evaluation
    test_sources = [
        "ABC Color",
        "La Nación",
        "La Tribuna",
        "Red Digital San Pedro"
    ]

    for source in test_sources:

        test_mask = df["source"].eq(source).to_numpy()
        train_mask = ~test_mask

        if np.unique(y[test_mask]).size != 2:
            continue

        source_model = create_model()

        source_model.fit(
            X[train_mask],
            y[train_mask]
        )

        print(f"\n=== HOLDOUT SOURCE: {source} ===")
        print("Test articles:", test_mask.sum())

        evaluate_model(
            source_model,
            X[test_mask],
            y[test_mask]
        )

    # Retrain using all available weak labels
    final_model = create_model()

    final_model.fit(X, y)

    joblib.dump(
        {
            "model": final_model,
            "embedding_model": df["embedding_model"].iloc[0],
            "task": "text-matching",
            "dimensions": 1024,
            "training_articles": len(df),
            "positive_label": "Política",
            "negative_categories": NEGATIVE_CATEGORIES
        },
        MODEL_PATH
    )

    print("\nBaseline model saved to:")
    print(MODEL_PATH)


if __name__ == "__main__":
    main()