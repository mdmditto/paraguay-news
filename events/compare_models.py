from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.ensemble import (
    ExtraTreesClassifier,
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
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
    "entities/event_training_dataset.csv"
)

OUTPUT_FILE = Path(
    "events/model_comparison_predictions.csv"
)

N_SPLITS = 5
RANDOM_STATE = 42


# =========================================================
# FEATURES
# =========================================================

# Keep exactly the feature set that performed best in our
# previous experiment.
#
# We are changing the CLASSIFIER, not the features.

FEATURES = [
    "similarity",
    "shared_per",
    "shared_org",
    "shared_loc",
    "entity_jaccard",
]


# =========================================================
# MODELS
# =========================================================

def get_models():

    models = {

        # -------------------------------------------------
        # Linear baseline
        # -------------------------------------------------

        "Logistic Regression": Pipeline(
            [
                (
                    "scaler",
                    StandardScaler(),
                ),
                (
                    "classifier",
                    LogisticRegression(
                        max_iter=3000,
                        class_weight="balanced",
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        ),

        # -------------------------------------------------
        # Bagging ensemble
        # -------------------------------------------------

        "Random Forest": RandomForestClassifier(
            n_estimators=500,
            max_depth=None,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=RANDOM_STATE,
            n_jobs=-1,
        ),

        # -------------------------------------------------
        # Highly randomized trees
        # -------------------------------------------------

        "Extra Trees": ExtraTreesClassifier(
            n_estimators=500,
            max_depth=None,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=RANDOM_STATE,
            n_jobs=-1,
        ),

        # -------------------------------------------------
        # Classical gradient boosting
        # -------------------------------------------------

        "Gradient Boosting": GradientBoostingClassifier(
            n_estimators=200,
            learning_rate=0.05,
            max_depth=2,
            min_samples_leaf=3,
            random_state=RANDOM_STATE,
        ),

        # -------------------------------------------------
        # Histogram gradient boosting
        # -------------------------------------------------

        "HistGradientBoosting": HistGradientBoostingClassifier(
            learning_rate=0.05,
            max_iter=200,
            max_leaf_nodes=15,
            min_samples_leaf=10,
            l2_regularization=1.0,
            random_state=RANDOM_STATE,
        ),
    }

    return models


# =========================================================
# METRICS
# =========================================================

def calculate_metrics(
    y_true,
    probabilities,
    threshold=0.5,
):

    predictions = (
        probabilities >= threshold
    ).astype(int)

    return {
        "accuracy": accuracy_score(
            y_true,
            predictions,
        ),

        "precision": precision_score(
            y_true,
            predictions,
            zero_division=0,
        ),

        "recall": recall_score(
            y_true,
            predictions,
            zero_division=0,
        ),

        "f1": f1_score(
            y_true,
            predictions,
            zero_division=0,
        ),

        "auc": roc_auc_score(
            y_true,
            probabilities,
        ),
    }


# =========================================================
# CROSS VALIDATION
# =========================================================

def evaluate_model(
    model_name,
    model,
    df,
):

    X = df[
        FEATURES
    ]

    y = df[
        "same_event"
    ]

    groups = df[
        "target_id"
    ]

    cv = StratifiedGroupKFold(
        n_splits=N_SPLITS,
        shuffle=True,
        random_state=RANDOM_STATE,
    )

    fold_metrics = []

    out_of_fold_probabilities = np.zeros(
        len(df),
        dtype=float,
    )

    fold_assignments = np.zeros(
        len(df),
        dtype=int,
    )

    print()
    print("-" * 78)
    print(
        f"MODEL: {model_name}"
    )
    print("-" * 78)

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

        # ---------------------------------------------
        # Train
        # ---------------------------------------------

        model.fit(
            X_train,
            y_train,
        )

        # ---------------------------------------------
        # Probabilities
        # ---------------------------------------------

        probabilities = (
            model.predict_proba(
                X_test
            )[:, 1]
        )

        out_of_fold_probabilities[
            test_idx
        ] = probabilities

        fold_assignments[
            test_idx
        ] = fold

        # ---------------------------------------------
        # Fold metrics
        # ---------------------------------------------

        metrics = calculate_metrics(
            y_test,
            probabilities,
        )

        metrics[
            "fold"
        ] = fold

        metrics[
            "train_size"
        ] = len(
            train_idx
        )

        metrics[
            "test_size"
        ] = len(
            test_idx
        )

        metrics[
            "test_targets"
        ] = df.iloc[
            test_idx
        ][
            "target_id"
        ].nunique()

        fold_metrics.append(
            metrics
        )

        print(
            f"Fold {fold}: "
            f"train={len(train_idx)}, "
            f"test={len(test_idx)}, "
            f"targets={metrics['test_targets']}, "
            f"F1={metrics['f1']:.4f}, "
            f"AUC={metrics['auc']:.4f}"
        )

    # =====================================================
    # Calculate mean/std across folds
    # =====================================================

    fold_df = pd.DataFrame(
        fold_metrics
    )

    summary = {
        "model":
            model_name,

        "accuracy":
            fold_df[
                "accuracy"
            ].mean(),

        "accuracy_std":
            fold_df[
                "accuracy"
            ].std(),

        "precision":
            fold_df[
                "precision"
            ].mean(),

        "precision_std":
            fold_df[
                "precision"
            ].std(),

        "recall":
            fold_df[
                "recall"
            ].mean(),

        "recall_std":
            fold_df[
                "recall"
            ].std(),

        "f1":
            fold_df[
                "f1"
            ].mean(),

        "f1_std":
            fold_df[
                "f1"
            ].std(),

        "auc":
            fold_df[
                "auc"
            ].mean(),

        "auc_std":
            fold_df[
                "auc"
            ].std(),
    }

    # =====================================================
    # Global OOF metrics
    #
    # Useful in addition to mean fold metrics.
    # =====================================================

    global_metrics = calculate_metrics(
        y,
        out_of_fold_probabilities,
    )

    summary[
        "oof_accuracy"
    ] = global_metrics[
        "accuracy"
    ]

    summary[
        "oof_precision"
    ] = global_metrics[
        "precision"
    ]

    summary[
        "oof_recall"
    ] = global_metrics[
        "recall"
    ]

    summary[
        "oof_f1"
    ] = global_metrics[
        "f1"
    ]

    summary[
        "oof_auc"
    ] = global_metrics[
        "auc"
    ]

    return (
        summary,
        out_of_fold_probabilities,
        fold_assignments,
    )


# =========================================================
# ERROR ANALYSIS
# =========================================================

def show_errors(
    df,
    model_name,
    probability_column,
):

    predictions = (
        df[
            probability_column
        ] >= 0.5
    ).astype(int)

    false_positive_mask = (
        (predictions == 1)
        & (df["same_event"] == 0)
    )

    false_negative_mask = (
        (predictions == 0)
        & (df["same_event"] == 1)
    )

    false_positives = df[
        false_positive_mask
    ].copy()

    false_negatives = df[
        false_negative_mask
    ].copy()

    print()
    print("=" * 78)
    print(
        f"ERROR ANALYSIS: {model_name}"
    )
    print("=" * 78)

    print(
        f"False positives: "
        f"{len(false_positives)}"
    )

    print(
        f"False negatives: "
        f"{len(false_negatives)}"
    )

    # -----------------------------------------------------
    # What kinds of false positives?
    # -----------------------------------------------------

    if len(false_positives) > 0:

        print()
        print(
            "False positives by original label:"
        )

        print(
            false_positives[
                "event_label"
            ]
            .value_counts()
            .sort_index()
            .to_string()
        )

    # -----------------------------------------------------
    # Most confident FP
    # -----------------------------------------------------

    columns = [
        "target_id",
        "candidate_id",
        "event_label",
        "similarity",
        "shared_per",
        "shared_org",
        "shared_loc",
        "entity_jaccard",
        probability_column,
    ]

    print()
    print(
        "Most confident false positives:"
    )

    if len(false_positives) > 0:

        print(
            false_posititives_safe(
                false_positives,
                columns,
                probability_column,
            )
        )

    else:

        print(
            "None"
        )

    print()
    print(
        "Most confident false negatives:"
    )

    if len(false_negatives) > 0:

        print(
            false_negatives
            .sort_values(
                probability_column,
                ascending=True,
            )[
                columns
            ]
            .head(10)
            .round(4)
            .to_string(
                index=False
            )
        )

    else:

        print(
            "None"
        )


def false_posititives_safe(
    false_positives,
    columns,
    probability_column,
):

    return (
        false_positives
        .sort_values(
            probability_column,
            ascending=False,
        )[
            columns
        ]
        .head(10)
        .round(4)
        .to_string(
            index=False
        )
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 78)
    print("EVENT MATCHER MODEL COMPARISON")
    print("=" * 78)

    # -----------------------------------------------------
    # Load
    # -----------------------------------------------------

    df = pd.read_csv(
        INPUT_FILE,
        encoding="utf-8-sig",
    )

    print(
        f"\nPairs: "
        f"{len(df)}"
    )

    print(
        f"Unique target articles: "
        f"{df['target_id'].nunique()}"
    )

    print()
    print(
        "Binary distribution:"
    )

    print(
        df[
            "same_event"
        ]
        .value_counts()
        .sort_index()
        .rename(
            index={
                0:
                    "not_same_event",
                1:
                    "same_event",
            }
        )
        .to_string()
    )

    # -----------------------------------------------------
    # Numeric safety
    # -----------------------------------------------------

    for feature in FEATURES:

        df[
            feature
        ] = pd.to_numeric(
            df[
                feature
            ],
            errors="coerce",
        ).fillna(
            0
        )

    # -----------------------------------------------------
    # Models
    # -----------------------------------------------------

    models = get_models()

    summaries = []

    probability_columns = {}

    common_folds = None

    for (
        model_name,
        model,
    ) in models.items():

        (
            summary,
            probabilities,
            folds,
        ) = evaluate_model(
            model_name,
            model,
            df,
        )

        summaries.append(
            summary
        )

        safe_name = (
            model_name
            .lower()
            .replace(
                " ",
                "_",
            )
        )

        probability_column = (
            f"prob_{safe_name}"
        )

        df[
            probability_column
        ] = probabilities

        probability_columns[
            model_name
        ] = probability_column

        if common_folds is None:

            common_folds = folds

    # -----------------------------------------------------
    # Save fold assignment
    # -----------------------------------------------------

    df[
        "cv_fold"
    ] = common_folds

    # -----------------------------------------------------
    # Summary table
    # -----------------------------------------------------

    results = pd.DataFrame(
        summaries
    )

    results = (
        results
        .sort_values(
            "f1",
            ascending=False,
        )
        .reset_index(
            drop=True
        )
    )

    print()
    print("=" * 78)
    print("GROUPED CROSS-VALIDATION RESULTS")
    print("=" * 78)

    columns = [
        "model",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "auc",
    ]

    print(
        results[
            columns
        ]
        .round(4)
        .to_string(
            index=False
        )
    )

    print()
    print("=" * 78)
    print("STANDARD DEVIATION ACROSS FOLDS")
    print("=" * 78)

    std_columns = [
        "model",
        "accuracy_std",
        "precision_std",
        "recall_std",
        "f1_std",
        "auc_std",
    ]

    print(
        results[
            std_columns
        ]
        .round(4)
        .to_string(
            index=False
        )
    )

    print()
    print("=" * 78)
    print("OUT-OF-FOLD RESULTS")
    print("=" * 78)

    oof_columns = [
        "model",
        "oof_accuracy",
        "oof_precision",
        "oof_recall",
        "oof_f1",
        "oof_auc",
    ]

    print(
        results[
            oof_columns
        ]
        .round(4)
        .to_string(
            index=False
        )
    )

    # -----------------------------------------------------
    # Identify winner by F1
    # -----------------------------------------------------

    best_model_name = (
        results.iloc[
            0
        ][
            "model"
        ]
    )

    best_probability_column = (
        probability_columns[
            best_model_name
        ]
    )

    print()
    print("=" * 78)
    print("TOP MODEL BY MEAN F1")
    print("=" * 78)

    print(
        best_model_name
    )

    # -----------------------------------------------------
    # Error analysis for top model
    # -----------------------------------------------------

    show_errors(
        df,
        best_model_name,
        best_probability_column,
    )

    # -----------------------------------------------------
    # Save predictions
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


if __name__ == "__main__":
    main()
