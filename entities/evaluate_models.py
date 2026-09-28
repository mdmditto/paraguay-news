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
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


# =========================================================
# CONFIGURATION
# =========================================================

INPUT_FILE = Path(
    "entities/event_candidates_with_entities.csv"
)

OUTPUT_FILE = Path(
    "entities/grouped_model_predictions.csv"
)

N_SPLITS = 5
RANDOM_STATE = 42


# =========================================================
# FEATURE SETS
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
        "entity_jaccard",
    ],
}


# =========================================================
# MODEL
# =========================================================

def create_model():

    return Pipeline(
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
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )


# =========================================================
# GROUPED CROSS VALIDATION
# =========================================================

def evaluate_feature_set(
    df,
    features,
):

    X = df[features]
    y = df["same_event"]

    # Important:
    # every pair belonging to the same target article
    # stays in the same fold.
    groups = df["target_id"]

    cv = StratifiedGroupKFold(
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

    probabilities = np.zeros(
        len(df),
        dtype=float,
    )

    predictions = np.zeros(
        len(df),
        dtype=int,
    )

    fold_numbers = np.zeros(
        len(df),
        dtype=int,
    )

    for fold, (
        train_idx,
        test_idx,
    ) in enumerate(
        cv.split(
            X,
            y,
            groups=groups,
        ),
        start=1,
    ):

        X_train = X.iloc[
            train_idx
        ]

        X_test = X.iloc[
            test_idx
        ]

        y_train = y.iloc[
            train_idx
        ]

        y_test = y.iloc[
            test_idx
        ]

        model = create_model()

        model.fit(
            X_train,
            y_train,
        )

        fold_probabilities = (
            model.predict_proba(
                X_test
            )[:, 1]
        )

        fold_predictions = (
            fold_probabilities >= 0.5
        ).astype(int)

        probabilities[
            test_idx
        ] = fold_probabilities

        predictions[
            test_idx
        ] = fold_predictions

        fold_numbers[
            test_idx
        ] = fold

        metrics[
            "accuracy"
        ].append(
            accuracy_score(
                y_test,
                fold_predictions,
            )
        )

        metrics[
            "precision"
        ].append(
            precision_score(
                y_test,
                fold_predictions,
                zero_division=0,
            )
        )

        metrics[
            "recall"
        ].append(
            recall_score(
                y_test,
                fold_predictions,
                zero_division=0,
            )
        )

        metrics[
            "f1"
        ].append(
            f1_score(
                y_test,
                fold_predictions,
                zero_division=0,
            )
        )

        # AUC requires both classes in test fold
        if y_test.nunique() == 2:

            metrics[
                "auc"
            ].append(
                roc_auc_score(
                    y_test,
                    fold_probabilities,
                )
            )

        print(
            f"  Fold {fold}: "
            f"train={len(train_idx)}, "
            f"test={len(test_idx)}, "
            f"targets={df.iloc[test_idx]['target_id'].nunique()}"
        )

    summary = {}

    for metric, values in metrics.items():

        if values:

            summary[metric] = (
                np.mean(values)
            )

            summary[
                f"{metric}_std"
            ] = (
                np.std(values)
            )

        else:

            summary[metric] = np.nan
            summary[
                f"{metric}_std"
            ] = np.nan

    return (
        summary,
        probabilities,
        predictions,
        fold_numbers,
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 76)
    print("GROUPED EVENT-DETECTION EVALUATION")
    print("=" * 76)

    df = pd.read_csv(
        INPUT_FILE,
        encoding="utf-8-sig",
    )

    print(
        f"\nPairs: {len(df)}"
    )

    print(
        "Unique target articles:",
        df["target_id"].nunique(),
    )

    # -----------------------------------------------------
    # Binary target
    #
    # label 2 = same event
    # labels 0/1 = not same event
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
    # Validate features
    # -----------------------------------------------------

    all_features = set()

    for features in FEATURE_SETS.values():
        all_features.update(
            features
        )

    required = (
        all_features
        | {
            "target_id",
            "candidate_id",
            "event_label",
        }
    )

    missing = (
        required
        - set(df.columns)
    )

    if missing:

        raise RuntimeError(
            "Missing columns: "
            + ", ".join(
                sorted(missing)
            )
        )

    for feature in all_features:

        df[feature] = pd.to_numeric(
            df[feature],
            errors="coerce",
        ).fillna(0)

    # -----------------------------------------------------
    # Evaluate models
    # -----------------------------------------------------

    results = []

    best_predictions = None

    for name, features in (
        FEATURE_SETS.items()
    ):

        print()
        print("-" * 76)
        print(
            f"Evaluating: {name}"
        )
        print("-" * 76)

        (
            metrics,
            probabilities,
            predictions,
            folds,
        ) = evaluate_feature_set(
            df,
            features,
        )

        results.append(
            {
                "model": name,
                **metrics,
            }
        )

        safe_name = (
            name.lower()
            .replace(" ", "_")
            .replace("+", "plus")
        )

        df[
            f"prob_{safe_name}"
        ] = probabilities

        if name == "Jina + basic NER":

            best_predictions = (
                probabilities,
                predictions,
                folds,
            )

    # -----------------------------------------------------
    # Results
    # -----------------------------------------------------

    results_df = pd.DataFrame(
        results
    )

    results_df = (
        results_df
        .sort_values(
            "f1",
            ascending=False,
        )
    )

    print()
    print("=" * 76)
    print("GROUPED CROSS-VALIDATED RESULTS")
    print("=" * 76)

    display_columns = [
        "model",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "auc",
    ]

    print(
        results_df[
            display_columns
        ]
        .round(4)
        .to_string(
            index=False
        )
    )

    print()
    print("=" * 76)
    print("STANDARD DEVIATION ACROSS FOLDS")
    print("=" * 76)

    std_columns = [
        "model",
        "accuracy_std",
        "precision_std",
        "recall_std",
        "f1_std",
        "auc_std",
    ]

    print(
        results_df[
            std_columns
        ]
        .round(4)
        .to_string(
            index=False
        )
    )

    # -----------------------------------------------------
    # Save predictions from basic NER model
    # -----------------------------------------------------

    if best_predictions is not None:

        (
            probabilities,
            predictions,
            folds,
        ) = best_predictions

        df[
            "same_event_probability"
        ] = probabilities

        df[
            "same_event_prediction"
        ] = predictions

        df[
            "cv_fold"
        ] = folds

        df[
            "prediction_correct"
        ] = (
            df[
                "same_event_prediction"
            ]
            == df[
                "same_event"
            ]
        )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print(
        f"Predictions saved to: "
        f"{OUTPUT_FILE}"
    )

    # -----------------------------------------------------
    # Show errors
    # -----------------------------------------------------

    if best_predictions is not None:

        errors = df[
            ~df[
                "prediction_correct"
            ]
        ].copy()

        print()
        print("=" * 76)
        print(
            "JINA + BASIC NER ERRORS"
        )
        print("=" * 76)

        print(
            f"Total errors: "
            f"{len(errors)}"
        )

        false_positives = errors[
            (
                errors[
                    "same_event_prediction"
                ] == 1
            )
            & (
                errors[
                    "same_event"
                ] == 0
            )
        ]

        false_negatives = errors[
            (
                errors[
                    "same_event_prediction"
                ] == 0
            )
            & (
                errors[
                    "same_event"
                ] == 1
            )
        ]

        print(
            f"False positives: "
            f"{len(false_positives)}"
        )

        print(
            f"False negatives: "
            f"{len(false_negatives)}"
        )

        # -------------------------------------------------
        # Most confident false positives
        # -------------------------------------------------

        print()
        print(
            "Most confident false positives:"
        )

        fp_columns = [
            "target_id",
            "candidate_id",
            "event_label",
            "similarity",
            "shared_per",
            "shared_org",
            "shared_loc",
            "entity_jaccard",
            "same_event_probability",
        ]

        print(
            false_positives
            .sort_values(
                "same_event_probability",
                ascending=False,
            )[
                fp_columns
            ]
            .head(10)
            .round(4)
            .to_string(
                index=False
            )
        )

        # -------------------------------------------------
        # Most confident false negatives
        # -------------------------------------------------

        print()
        print(
            "Most confident false negatives:"
        )

        print(
            false_negatives
            .sort_values(
                "same_event_probability",
                ascending=True,
            )[
                fp_columns
            ]
            .head(10)
            .round(4)
            .to_string(
                index=False
            )
        )


if __name__ == "__main__":
    main()