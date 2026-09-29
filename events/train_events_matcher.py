from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
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

MODEL_DIR = Path(
    "events/models"
)

MODEL_FILE = MODEL_DIR / "event_matcher_v1.joblib"

METADATA_FILE = MODEL_DIR / "event_matcher_v1_metadata.json"

OOF_FILE = Path(
    "events/event_matcher_v1_oof_predictions.csv"
)

THRESHOLD_FILE = Path(
    "events/event_matcher_v1_thresholds.csv"
)

N_SPLITS = 5
RANDOM_STATE = 42


# =========================================================
# MODEL VERSION
# =========================================================

MODEL_VERSION = "event_matcher_v1"

EMBEDDING_MODEL = (
    "jinaai/jina-embeddings-v5-text-small"
)

EMBEDDING_TASK = "text-matching"

NER_MODEL = (
    "Davlan/xlm-roberta-base-ner-hrl"
)


# =========================================================
# FEATURES
# =========================================================

FEATURES = [
    "similarity",
    "shared_per",
    "shared_org",
    "shared_loc",
    "entity_jaccard",
]


# =========================================================
# THRESHOLDS TO TEST
# =========================================================

THRESHOLDS = [
    0.50,
    0.55,
    0.60,
    0.65,
    0.70,
    0.75,
    0.80,
    0.85,
    0.90,
    0.95,
]


# =========================================================
# UNION-FIND
# =========================================================

class UnionFind:

    def __init__(self, nodes):

        self.parent = {
            node: node
            for node in nodes
        }

        self.rank = {
            node: 0
            for node in nodes
        }

    def find(self, node):

        if self.parent[node] != node:

            self.parent[node] = self.find(
                self.parent[node]
            )

        return self.parent[node]

    def union(self, a, b):

        root_a = self.find(a)
        root_b = self.find(b)

        if root_a == root_b:
            return

        if self.rank[root_a] < self.rank[root_b]:

            self.parent[root_a] = root_b

        elif self.rank[root_a] > self.rank[root_b]:

            self.parent[root_b] = root_a

        else:

            self.parent[root_b] = root_a
            self.rank[root_a] += 1


# =========================================================
# CONNECTED COMPONENTS
# =========================================================

def add_connected_components(df):

    article_ids = set(
        df["target_id"]
        .astype(int)
        .tolist()
    )

    article_ids.update(
        df["candidate_id"]
        .astype(int)
        .tolist()
    )

    union_find = UnionFind(
        article_ids
    )

    # Every manually labeled pair is an edge.
    for row in df.itertuples():

        union_find.union(
            int(row.target_id),
            int(row.candidate_id),
        )

    # Convert arbitrary union-find roots into simple
    # component IDs: 0, 1, 2, ...
    root_to_component = {}

    article_component = {}

    next_component = 0

    for article_id in sorted(article_ids):

        root = union_find.find(
            article_id
        )

        if root not in root_to_component:

            root_to_component[
                root
            ] = next_component

            next_component += 1

        article_component[
            article_id
        ] = root_to_component[
            root
        ]

    df[
        "component_id"
    ] = (
        df["target_id"]
        .astype(int)
        .map(
            article_component
        )
    )

    return df


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
                    max_iter=3000,
                    class_weight="balanced",
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )


# =========================================================
# DATA LOADING
# =========================================================

def load_data():

    print("=" * 78)
    print("LOADING TRAINING DATA")
    print("=" * 78)

    df = pd.read_csv(
        INPUT_FILE,
        encoding="utf-8-sig",
    )

    required_columns = (
        [
            "target_id",
            "candidate_id",
            "event_label",
            "same_event",
        ]
        + FEATURES
    )

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:

        raise RuntimeError(
            "Missing columns: "
            + ", ".join(
                missing_columns
            )
        )

    # -----------------------------------------------------
    # Numeric safety
    # -----------------------------------------------------

    numeric_columns = (
        FEATURES
        + [
            "target_id",
            "candidate_id",
            "event_label",
            "same_event",
        ]
    )

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # -----------------------------------------------------
    # Remove invalid rows
    # -----------------------------------------------------

    before = len(df)

    df = (
        df
        .dropna(
            subset=required_columns
        )
        .copy()
    )

    removed = before - len(df)

    if removed > 0:

        print(
            f"Removed invalid rows: "
            f"{removed}"
        )

    df[
        "target_id"
    ] = df[
        "target_id"
    ].astype(int)

    df[
        "candidate_id"
    ] = df[
        "candidate_id"
    ].astype(int)

    df[
        "event_label"
    ] = df[
        "event_label"
    ].astype(int)

    df[
        "same_event"
    ] = df[
        "same_event"
    ].astype(int)

    # -----------------------------------------------------
    # Sanity checks
    # -----------------------------------------------------

    valid_binary_labels = set(
        df[
            "same_event"
        ].unique()
    )

    if not valid_binary_labels.issubset(
        {0, 1}
    ):

        raise RuntimeError(
            "same_event must contain only 0 and 1."
        )

    print(
        f"Pairs: "
        f"{len(df)}"
    )

    unique_articles = (
        set(
            df["target_id"]
        )
        |
        set(
            df["candidate_id"]
        )
    )

    print(
        f"Unique articles: "
        f"{len(unique_articles)}"
    )

    print()
    print(
        "Original label distribution:"
    )

    print(
        df[
            "event_label"
        ]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print()
    print(
        "Binary label distribution:"
    )

    print(
        df[
            "same_event"
        ]
        .value_counts()
        .sort_index()
        .rename(
            index={
                0: "not_same_event",
                1: "same_event",
            }
        )
        .to_string()
    )

    return df


# =========================================================
# BUILD STRICT CV FOLDS
# =========================================================

def build_strict_folds(df):

    print()
    print("=" * 78)
    print("BUILDING STRICT CONNECTED-COMPONENT FOLDS")
    print("=" * 78)

    df = add_connected_components(
        df
    )

    component_sizes = (
        df[
            "component_id"
        ]
        .value_counts()
    )

    print(
        f"Connected components: "
        f"{df['component_id'].nunique()}"
    )

    print(
        f"Largest component: "
        f"{component_sizes.max()} pairs"
    )

    print(
        f"Median component: "
        f"{component_sizes.median():.1f} pairs"
    )

    X_dummy = np.zeros(
        (
            len(df),
            1,
        )
    )

    y = df[
        "same_event"
    ].to_numpy()

    groups = df[
        "component_id"
    ].to_numpy()

    if (
        df[
            "component_id"
        ]
        .nunique()
        < N_SPLITS
    ):

        raise RuntimeError(
            "Not enough connected components "
            "for strict cross-validation."
        )

    cv = StratifiedGroupKFold(
        n_splits=N_SPLITS,
        shuffle=True,
        random_state=RANDOM_STATE,
    )

    folds = list(
        cv.split(
            X_dummy,
            y,
            groups,
        )
    )

    # -----------------------------------------------------
    # Validate folds
    # -----------------------------------------------------

    for fold_number, (
        train_idx,
        test_idx,
    ) in enumerate(
        folds,
        start=1,
    ):

        train_classes = set(
            y[
                train_idx
            ]
        )

        test_classes = set(
            y[
                test_idx
            ]
        )

        if (
            len(train_classes) < 2
            or len(test_classes) < 2
        ):

            raise RuntimeError(
                f"Fold {fold_number} does not contain "
                f"both classes."
            )

        train_components = set(
            groups[
                train_idx
            ]
        )

        test_components = set(
            groups[
                test_idx
            ]
        )

        overlap = (
            train_components
            &
            test_components
        )

        if overlap:

            raise RuntimeError(
                f"Component leakage detected "
                f"in fold {fold_number}."
            )

        print(
            f"Fold {fold_number}: "
            f"train={len(train_idx)}, "
            f"test={len(test_idx)}, "
            f"test_components="
            f"{len(test_components)}, "
            f"positive_test="
            f"{int(y[test_idx].sum())}"
        )

    return df, folds


# =========================================================
# GENERATE STRICT OOF PREDICTIONS
# =========================================================

def generate_oof_predictions(
    df,
    folds,
):

    print()
    print("=" * 78)
    print("GENERATING STRICT OUT-OF-FOLD PREDICTIONS")
    print("=" * 78)

    X = df[
        FEATURES
    ]

    y = df[
        "same_event"
    ]

    probabilities = np.zeros(
        len(df),
        dtype=float,
    )

    fold_assignments = np.zeros(
        len(df),
        dtype=int,
    )

    for fold_number, (
        train_idx,
        test_idx,
    ) in enumerate(
        folds,
        start=1,
    ):

        model = create_model()

        X_train = X.iloc[
            train_idx
        ]

        X_test = X.iloc[
            test_idx
        ]

        y_train = y.iloc[
            train_idx
        ]

        model.fit(
            X_train,
            y_train,
        )

        fold_probabilities = (
            model
            .predict_proba(
                X_test
            )[:, 1]
        )

        probabilities[
            test_idx
        ] = fold_probabilities

        fold_assignments[
            test_idx
        ] = fold_number

    df[
        "oof_probability"
    ] = probabilities

    df[
        "cv_fold"
    ] = fold_assignments

    auc = roc_auc_score(
        y,
        probabilities,
    )

    print(
        f"Strict OOF ROC-AUC: "
        f"{auc:.4f}"
    )

    return df


# =========================================================
# THRESHOLD EVALUATION
# =========================================================

def evaluate_thresholds(df):

    print()
    print("=" * 78)
    print("OOF THRESHOLD ANALYSIS")
    print("=" * 78)

    y_true = df[
        "same_event"
    ].to_numpy()

    probabilities = df[
        "oof_probability"
    ].to_numpy()

    rows = []

    for threshold in THRESHOLDS:

        predictions = (
            probabilities >= threshold
        ).astype(int)

        tn, fp, fn, tp = (
            confusion_matrix(
                y_true,
                predictions,
                labels=[
                    0,
                    1,
                ],
            )
            .ravel()
        )

        accuracy = accuracy_score(
            y_true,
            predictions,
        )

        precision = precision_score(
            y_true,
            predictions,
            zero_division=0,
        )

        recall = recall_score(
            y_true,
            predictions,
            zero_division=0,
        )

        f1 = f1_score(
            y_true,
            predictions,
            zero_division=0,
        )

        # -------------------------------------------------
        # Separate the two kinds of negative examples
        #
        # label 0 = genuinely different event
        # label 1 = related/follow-up event
        # -------------------------------------------------

        label_0_mask = (
            df[
                "event_label"
            ].to_numpy()
            == 0
        )

        label_1_mask = (
            df[
                "event_label"
            ].to_numpy()
            == 1
        )

        label_0_fp = int(
            np.sum(
                predictions[
                    label_0_mask
                ] == 1
            )
        )

        label_1_fp = int(
            np.sum(
                predictions[
                    label_1_mask
                ] == 1
            )
        )

        label_0_total = int(
            label_0_mask.sum()
        )

        label_1_total = int(
            label_1_mask.sum()
        )

        label_0_fp_rate = (
            label_0_fp
            / label_0_total
            if label_0_total
            else 0
        )

        label_1_fp_rate = (
            label_1_fp
            / label_1_total
            if label_1_total
            else 0
        )

        rows.append(
            {
                "threshold":
                    threshold,

                "accuracy":
                    accuracy,

                "precision":
                    precision,

                "recall":
                    recall,

                "f1":
                    f1,

                "tp":
                    int(tp),

                "fp":
                    int(fp),

                "fn":
                    int(fn),

                "tn":
                    int(tn),

                "label_0_fp":
                    label_0_fp,

                "label_0_fp_rate":
                    label_0_fp_rate,

                "label_1_fp":
                    label_1_fp,

                "label_1_fp_rate":
                    label_1_fp_rate,
            }
        )

    results = pd.DataFrame(
        rows
    )

    display_columns = [
        "threshold",
        "precision",
        "recall",
        "f1",
        "tp",
        "fp",
        "fn",
        "label_0_fp",
        "label_1_fp",
    ]

    print(
        results[
            display_columns
        ]
        .round(4)
        .to_string(
            index=False
        )
    )

    print()
    print(
        "False-positive rates by original negative label:"
    )

    rate_columns = [
        "threshold",
        "label_0_fp_rate",
        "label_1_fp_rate",
    ]

    print(
        results[
            rate_columns
        ]
        .round(4)
        .to_string(
            index=False
        )
    )

    return results


# =========================================================
# ERROR ANALYSIS AT EACH USEFUL THRESHOLD
# =========================================================

def show_high_confidence_errors(
    df,
    threshold=0.80,
):

    probabilities = df[
        "oof_probability"
    ].to_numpy()

    predictions = (
        probabilities >= threshold
    ).astype(int)

    false_positive_mask = (
        (predictions == 1)
        &
        (
            df[
                "same_event"
            ].to_numpy()
            == 0
        )
    )

    false_negative_mask = (
        (predictions == 0)
        &
        (
            df[
                "same_event"
            ].to_numpy()
            == 1
        )
    )

    false_positives = df[
        false_positive_mask
    ].copy()

    false_negatives = df[
        false_negative_mask
    ].copy()

    columns = [
        "target_id",
        "candidate_id",
        "event_label",
        "similarity",
        "shared_per",
        "shared_org",
        "shared_loc",
        "entity_jaccard",
        "oof_probability",
    ]

    print()
    print("=" * 78)
    print(
        f"ERRORS AT THRESHOLD {threshold:.2f}"
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

    if len(false_positives):

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

        print()
        print(
            "Highest-confidence false positives:"
        )

        print(
            false_positives
            .sort_values(
                "oof_probability",
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

    if len(false_negatives):

        print()
        print(
            "Highest-confidence false negatives:"
        )

        print(
            false_negatives
            .sort_values(
                "oof_probability",
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
# TRAIN FINAL MODEL
# =========================================================

def train_final_model(df):

    print()
    print("=" * 78)
    print("TRAINING FINAL EVENT MATCHER")
    print("=" * 78)

    X = df[
        FEATURES
    ]

    y = df[
        "same_event"
    ]

    model = create_model()

    model.fit(
        X,
        y,
    )

    print(
        f"Training pairs: "
        f"{len(df)}"
    )

    print(
        "Final model trained on all labeled pairs."
    )

    return model


# =========================================================
# COEFFICIENTS
# =========================================================

def show_coefficients(model):

    scaler = model.named_steps[
        "scaler"
    ]

    classifier = model.named_steps[
        "classifier"
    ]

    coefficients = (
        classifier.coef_[0]
    )

    coefficient_df = pd.DataFrame(
        {
            "feature":
                FEATURES,

            "coefficient_standardized":
                coefficients,

            "abs_coefficient":
                np.abs(
                    coefficients
                ),

            "feature_mean":
                scaler.mean_,

            "feature_scale":
                scaler.scale_,
        }
    )

    coefficient_df = (
        coefficient_df
        .sort_values(
            "abs_coefficient",
            ascending=False,
        )
        .reset_index(
            drop=True
        )
    )

    print()
    print("=" * 78)
    print("FINAL MODEL COEFFICIENTS")
    print("=" * 78)

    print(
        coefficient_df
        .round(4)
        .to_string(
            index=False
        )
    )

    print()
    print(
        "Intercept:"
    )

    print(
        round(
            float(
                classifier.intercept_[
                    0
                ]
            ),
            4,
        )
    )

    return coefficient_df


# =========================================================
# SAVE MODEL
# =========================================================

def save_model(
    model,
    df,
    threshold_results,
    coefficient_df,
):

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # -----------------------------------------------------
    # Save sklearn pipeline
    # -----------------------------------------------------

    joblib.dump(
        model,
        MODEL_FILE,
    )

    # -----------------------------------------------------
    # Metadata
    # -----------------------------------------------------

    best_f1_row = (
        threshold_results
        .sort_values(
            "f1",
            ascending=False,
        )
        .iloc[0]
    )

    metadata = {

        "version":
            MODEL_VERSION,

        "classifier":
            "LogisticRegression",

        "training_pairs":
            int(
                len(df)
            ),

        "unique_articles":
            int(
                len(
                    set(
                        df[
                            "target_id"
                        ]
                    )
                    |
                    set(
                        df[
                            "candidate_id"
                        ]
                    )
                )
            ),

        "features":
            FEATURES,

        "embedding_model":
            EMBEDDING_MODEL,

        "embedding_task":
            EMBEDDING_TASK,

        "ner_model":
            NER_MODEL,

        "cross_validation":
            {
                "method":
                    "StratifiedGroupKFold",

                "group":
                    "connected_component",

                "n_splits":
                    N_SPLITS,

                "random_state":
                    RANDOM_STATE,
            },

        # This is descriptive only.
        # We are NOT automatically declaring it the
        # production threshold.
        "best_oof_f1_threshold":
            float(
                best_f1_row[
                    "threshold"
                ]
            ),

        "best_oof_f1":
            float(
                best_f1_row[
                    "f1"
                ]
            ),

        "coefficients":
            {
                row["feature"]:
                    float(
                        row[
                            "coefficient_standardized"
                        ]
                    )

                for _, row
                in coefficient_df.iterrows()
            },
    }

    with open(
        METADATA_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            metadata,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("=" * 78)
    print("SAVED MODEL")
    print("=" * 78)

    print(
        f"Model:    "
        f"{MODEL_FILE}"
    )

    print(
        f"Metadata: "
        f"{METADATA_FILE}"
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 78)
    print("TRAIN EVENT MATCHER V1")
    print("=" * 78)

    # -----------------------------------------------------
    # Load
    # -----------------------------------------------------

    df = load_data()

    # -----------------------------------------------------
    # Strict connected-component CV
    # -----------------------------------------------------

    df, folds = build_strict_folds(
        df
    )

    # -----------------------------------------------------
    # Generate OOF probabilities
    # -----------------------------------------------------

    df = generate_oof_predictions(
        df,
        folds,
    )

    # -----------------------------------------------------
    # Threshold analysis
    # -----------------------------------------------------

    threshold_results = (
        evaluate_thresholds(
            df
        )
    )

    # -----------------------------------------------------
    # Error inspection
    # -----------------------------------------------------

    show_high_confidence_errors(
        df,
        threshold=0.80,
    )

    show_high_confidence_errors(
        df,
        threshold=0.90,
    )

    # -----------------------------------------------------
    # Save OOF predictions
    # -----------------------------------------------------

    OOF_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        OOF_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    threshold_results.to_csv(
        THRESHOLD_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print(
        f"OOF predictions saved to: "
        f"{OOF_FILE}"
    )

    print(
        f"Threshold results saved to: "
        f"{THRESHOLD_FILE}"
    )

    # -----------------------------------------------------
    # Train production model on ALL labeled data
    # -----------------------------------------------------

    final_model = train_final_model(
        df
    )

    # -----------------------------------------------------
    # Inspect coefficients
    # -----------------------------------------------------

    coefficient_df = (
        show_coefficients(
            final_model
        )
    )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    save_model(
        final_model,
        df,
        threshold_results,
        coefficient_df,
    )


if __name__ == "__main__":
    main()
