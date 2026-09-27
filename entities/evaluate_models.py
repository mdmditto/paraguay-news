from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


# =========================================================
# CONFIGURATION
# =========================================================

INPUT_FILE = Path(
    "entities/event_candidates_with_entities.csv"
)

N_SPLITS = 5
RANDOM_STATE = 42


# =========================================================
# MODELS TO TEST
# =========================================================

FEATURE_SETS = {

    "Jina only": [
        "similarity",
    ],

    "Jina + basic NER": [
        "similarity",
        "shared_per",
        "shared_org",
        "shared_loc",
        "entity_jaccard",
    ],

    "Jina + IDF NER": [
        "similarity",
        "shared_per",
        "shared_org",
        "shared_loc",
        "idf_jaccard",
    ],

    "NER only": [
        "shared_per",
        "shared_org",
        "shared_loc",
        "idf_jaccard",
    ],
}


# =========================================================
# EVALUATION
# =========================================================

def evaluate_feature_set(
    X,
    y,
    feature_names,
):

    cv = StratifiedKFold(
        n_splits=N_SPLITS,
        shuffle=True,
        random_state=RANDOM_STATE,
    )

    metrics = {
        "accuracy": [],
        "precision": [],
        "recall": [],
        "f1": [],
        "auc": [],
    }

    all_probabilities = np.zeros(
        len(y)
    )

    for train_idx, test_idx in cv.split(
        X,
        y,
    ):

        X_train = X.iloc[
            train_idx
        ][feature_names]

        X_test = X.iloc[
            test_idx
        ][feature_names]

        y_train = y.iloc[
            train_idx
        ]

        y_test = y.iloc[
            test_idx
        ]

        model = Pipeline(
            [
                (
                    "scaler",
                    StandardScaler(),
                ),
                (
                    "classifier",
                    LogisticRegression(
                        max_iter=2000,
                        class_weight="balanced",
                    ),
                ),
            ]
        )

        model.fit(
            X_train,
            y_train,
        )

        probabilities = (
            model.predict_proba(
                X_test
            )[:, 1]
        )

        predictions = (
            probabilities >= 0.5
        ).astype(int)

        all_probabilities[
            test_idx
        ] = probabilities

        metrics[
            "accuracy"
        ].append(
            accuracy_score(
                y_test,
                predictions,
            )
        )

        metrics[
            "precision"
        ].append(
            precision_score(
                y_test,
                predictions,
                zero_division=0,
            )
        )

        metrics[
            "recall"
        ].append(
            recall_score(
                y_test,
                predictions,
                zero_division=0,
            )
        )

        metrics[
            "f1"
        ].append(
            f1_score(
                y_test,
                predictions,
                zero_division=0,
            )
        )

        metrics[
            "auc"
        ].append(
            roc_auc_score(
                y_test,
                probabilities,
            )
        )

    return {
        metric: np.mean(values)
        for metric, values
        in metrics.items()
    }, all_probabilities


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 72)
    print("EVENT DETECTION MODEL COMPARISON")
    print("=" * 72)

    df = pd.read_csv(
        INPUT_FILE,
        encoding="utf-8-sig",
    )

    print(
        f"\nPairs: {len(df)}"
    )

    # -----------------------------------------------------
    # Binary target
    #
    # 2 = same event     -> 1
    # 0/1 = not same     -> 0
    # -----------------------------------------------------

    df["same_event"] = (
        df["event_label"] == 2
    ).astype(int)

    print()
    print("Binary distribution:")
    print(
        df["same_event"]
        .value_counts()
        .sort_index()
    )

    # -----------------------------------------------------
    # Make sure features are numeric
    # -----------------------------------------------------

    all_features = set()

    for features in FEATURE_SETS.values():
        all_features.update(
            features
        )

    for column in all_features:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        ).fillna(0)

    # -----------------------------------------------------
    # Evaluate
    # -----------------------------------------------------

    results = []

    probability_columns = {}

    for name, features in (
        FEATURE_SETS.items()
    ):

        print()
        print(
            f"Evaluating: {name}"
        )

        metrics, probabilities = (
            evaluate_feature_set(
                df,
                df["same_event"],
                features,
            )
        )

        probability_columns[
            name
        ] = probabilities

        results.append(
            {
                "model": name,
                **metrics,
            }
        )

    results_df = pd.DataFrame(
        results
    )

    # -----------------------------------------------------
    # Results
    # -----------------------------------------------------

    print()
    print("=" * 72)
    print("CROSS-VALIDATED RESULTS")
    print("=" * 72)

    print(
        results_df
        .sort_values(
            "f1",
            ascending=False,
        )
        .round(4)
        .to_string(
            index=False
        )
    )

    # -----------------------------------------------------
    # Add out-of-fold predictions
    # -----------------------------------------------------

    for name, probabilities in (
        probability_columns.items()
    ):

        safe_name = (
            name
            .lower()
            .replace(" ", "_")
            .replace("+", "plus")
        )

        df[
            f"prob_{safe_name}"
        ] = probabilities

    output_file = Path(
        "entities/model_predictions.csv"
    )

    df.to_csv(
        output_file,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print(
        f"Predictions saved to: "
        f"{output_file}"
    )


if __name__ == "__main__":
    main()
