from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

from database.db import SessionLocal

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
    "events/strict_feature_evaluation_predictions.csv"
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

    "Jina + NER": [
        "similarity",
        "shared_per",
        "shared_org",
        "shared_loc",
        "entity_jaccard",
    ],

    "Jina + NER + time": [
        "similarity",
        "shared_per",
        "shared_org",
        "shared_loc",
        "entity_jaccard",
        "log_time_delta",
    ],
}


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

        if (
            self.rank[root_a]
            < self.rank[root_b]
        ):

            self.parent[root_a] = root_b

        elif (
            self.rank[root_a]
            > self.rank[root_b]
        ):

            self.parent[root_b] = root_a

        else:

            self.parent[root_b] = root_a

            self.rank[root_a] += 1


# =========================================================
# CONNECTED COMPONENTS
# =========================================================

def add_connected_components(df):

    article_ids = set(
        df["target_id"].astype(int)
    )

    article_ids.update(
        df["candidate_id"].astype(int)
    )

    union_find = UnionFind(
        article_ids
    )

    # Every labeled pair creates an edge.
    for row in df.itertuples():

        union_find.union(
            int(row.target_id),
            int(row.candidate_id),
        )

    # Map roots to clean component IDs.
    root_to_component = {}

    next_component = 0

    article_component = {}

    for article_id in article_ids:

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

    # Because each pair is an edge, both articles must
    # belong to the same component.
    df["component_id"] = (
        df["target_id"]
        .astype(int)
        .map(article_component)
    )

    return df


# =========================================================
def add_time_features(df):

    print()
    print("=" * 78)
    print("LOADING PUBLICATION TIMES FROM POSTGRESQL")
    print("=" * 78)

    # -----------------------------------------------------
    # Get every article involved in the labeled pairs
    # -----------------------------------------------------

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

    article_ids = sorted(
        article_ids
    )

    print(
        f"Articles to retrieve: "
        f"{len(article_ids)}"
    )

    # -----------------------------------------------------
    # Retrieve publication timestamps
    # -----------------------------------------------------

    session = SessionLocal()

    try:

        rows = session.execute(
            text(
                """
                SELECT
                    id,
                    published_at
                FROM articles
                WHERE id = ANY(:article_ids)
                """
            ),
            {
                "article_ids":
                    article_ids
            },
        ).mappings().all()

    finally:

        session.close()

    publication_times = {
        int(row["id"]):
            row["published_at"]
        for row in rows
    }

    print(
        f"Articles found in database: "
        f"{len(publication_times)}"
    )

    # -----------------------------------------------------
    # Map timestamps onto pairs
    # -----------------------------------------------------

    df[
        "target_published_at"
    ] = (
        df["target_id"]
        .astype(int)
        .map(
            publication_times
        )
    )

    df[
        "candidate_published_at"
    ] = (
        df["candidate_id"]
        .astype(int)
        .map(
            publication_times
        )
    )

    # -----------------------------------------------------
    # Parse timestamps
    # -----------------------------------------------------

    target_time = pd.to_datetime(
        df[
            "target_published_at"
        ],
        errors="coerce",
        utc=True,
    )

    candidate_time = pd.to_datetime(
        df[
            "candidate_published_at"
        ],
        errors="coerce",
        utc=True,
    )

    # -----------------------------------------------------
    # Calculate absolute difference
    # -----------------------------------------------------

    delta = (
        target_time
        - candidate_time
    ).abs()

    df[
        "time_delta_hours"
    ] = (
        delta.dt.total_seconds()
        / 3600
    )

    # -----------------------------------------------------
    # Missing timestamp diagnostics
    # -----------------------------------------------------

    target_missing = (
        target_time
        .isna()
        .sum()
    )

    candidate_missing = (
        candidate_time
        .isna()
        .sum()
    )

    pair_missing = (
        df[
            "time_delta_hours"
        ]
        .isna()
        .sum()
    )

    print(
        f"Pairs missing target timestamp: "
        f"{target_missing}"
    )

    print(
        f"Pairs missing candidate timestamp: "
        f"{candidate_missing}"
    )

    print(
        f"Pairs missing at least one timestamp: "
        f"{pair_missing}"
    )

    # -----------------------------------------------------
    # Missing-time indicator
    # -----------------------------------------------------

    df[
        "time_missing"
    ] = (
        df[
            "time_delta_hours"
        ]
        .isna()
        .astype(int)
    )

    # -----------------------------------------------------
    # Impute missing values
    # -----------------------------------------------------

    median_delta = (
        df[
            "time_delta_hours"
        ]
        .median()
    )

    if pd.isna(
        median_delta
    ):

        median_delta = 0.0

    print(
        f"Median observed time difference: "
        f"{median_delta:.2f} hours"
    )

    df[
        "time_delta_hours"
    ] = (
        df[
            "time_delta_hours"
        ]
        .fillna(
            median_delta
        )
    )

    # -----------------------------------------------------
    # Log transform
    # -----------------------------------------------------

    df[
        "log_time_delta"
    ] = np.log1p(
        df[
            "time_delta_hours"
        ]
    )

    return df


# =========================================================
# COMPONENT SUMMARY
# =========================================================

def show_component_summary(df):

    component_summary = (
        df
        .groupby(
            "component_id"
        )
        .agg(
            pairs=(
                "same_event",
                "size",
            ),
            positive_pairs=(
                "same_event",
                "sum",
            ),
            articles_target=(
                "target_id",
                "nunique",
            ),
        )
        .sort_values(
            "pairs",
            ascending=False,
        )
    )

    print()
    print("=" * 78)
    print("PAIR-GRAPH CONNECTED COMPONENTS")
    print("=" * 78)

    print(
        f"Components: "
        f"{len(component_summary)}"
    )

    print(
        f"Largest component: "
        f"{component_summary['pairs'].max()} pairs"
    )

    print(
        f"Median component: "
        f"{component_summary['pairs'].median():.1f} pairs"
    )

    print()
    print(
        "10 largest components:"
    )

    print(
        component_summary
        .head(10)
        .to_string()
    )

    return component_summary


# =========================================================
# METRICS
# =========================================================

def calculate_metrics(
    y_true,
    probabilities,
):

    predictions = (
        probabilities >= 0.5
    ).astype(int)

    return {

        "accuracy":
            accuracy_score(
                y_true,
                predictions,
            ),

        "precision":
            precision_score(
                y_true,
                predictions,
                zero_division=0,
            ),

        "recall":
            recall_score(
                y_true,
                predictions,
                zero_division=0,
            ),

        "f1":
            f1_score(
                y_true,
                predictions,
                zero_division=0,
            ),

        "auc":
            roc_auc_score(
                y_true,
                probabilities,
            ),
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
                    max_iter=3000,
                    class_weight="balanced",
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )


# =========================================================
# BUILD FOLDS ONCE
# =========================================================

def build_folds(df):

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

    unique_groups = np.unique(
        groups
    )

    if len(unique_groups) < N_SPLITS:

        raise RuntimeError(
            f"Only {len(unique_groups)} connected components "
            f"exist, so {N_SPLITS}-fold grouped CV is impossible."
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

    # Verify that every fold contains both classes.
    for fold_number, (
        train_idx,
        test_idx,
    ) in enumerate(
        folds,
        start=1,
    ):

        train_classes = np.unique(
            y[train_idx]
        )

        test_classes = np.unique(
            y[test_idx]
        )

        if (
            len(train_classes) < 2
            or len(test_classes) < 2
        ):

            raise RuntimeError(
                f"Fold {fold_number} does not contain both "
                f"classes in train/test. Connected-component "
                f"CV is too fragmented for this split."
            )

    return folds


# =========================================================
# EVALUATE FEATURE SET
# =========================================================

def evaluate_feature_set(
    df,
    feature_name,
    features,
    folds,
):

    X = df[
        features
    ]

    y = df[
        "same_event"
    ]

    probabilities = np.zeros(
        len(df),
        dtype=float,
    )

    fold_assignment = np.zeros(
        len(df),
        dtype=int,
    )

    fold_results = []

    print()
    print("-" * 78)
    print(
        f"FEATURE SET: {feature_name}"
    )
    print(
        "Features:",
        ", ".join(features),
    )
    print("-" * 78)

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

        y_test = y.iloc[
            test_idx
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

        fold_assignment[
            test_idx
        ] = fold_number

        metrics = calculate_metrics(
            y_test,
            fold_probabilities,
        )

        metrics[
            "fold"
        ] = fold_number

        fold_results.append(
            metrics
        )

        test_components = (
            df.iloc[
                test_idx
            ][
                "component_id"
            ]
            .nunique()
        )

        print(
            f"Fold {fold_number}: "
            f"train={len(train_idx)}, "
            f"test={len(test_idx)}, "
            f"components={test_components}, "
            f"positive={int(y_test.sum())}, "
            f"F1={metrics['f1']:.4f}, "
            f"AUC={metrics['auc']:.4f}"
        )

    fold_df = pd.DataFrame(
        fold_results
    )

    overall = calculate_metrics(
        y,
        probabilities,
    )

    summary = {

        "feature_set":
            feature_name,

        "accuracy":
            fold_df[
                "accuracy"
            ].mean(),

        "precision":
            fold_df[
                "precision"
            ].mean(),

        "recall":
            fold_df[
                "recall"
            ].mean(),

        "f1":
            fold_df[
                "f1"
            ].mean(),

        "auc":
            fold_df[
                "auc"
            ].mean(),

        "f1_std":
            fold_df[
                "f1"
            ].std(),

        "auc_std":
            fold_df[
                "auc"
            ].std(),

        "oof_accuracy":
            overall[
                "accuracy"
            ],

        "oof_precision":
            overall[
                "precision"
            ],

        "oof_recall":
            overall[
                "recall"
            ],

        "oof_f1":
            overall[
                "f1"
            ],

        "oof_auc":
            overall[
                "auc"
            ],
    }

    return (
        summary,
        probabilities,
        fold_assignment,
    )


# =========================================================
# TIME SUMMARY
# =========================================================

def show_time_summary(df):

    print()
    print("=" * 78)
    print("TIME DIFFERENCE BY LABEL")
    print("=" * 78)

    summary = (
        df
        .groupby(
            "event_label"
        )[
            "time_delta_hours"
        ]
        .agg(
            [
                "count",
                "mean",
                "median",
                "min",
                "max",
            ]
        )
        .round(2)
    )

    print(
        summary.to_string()
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 78)
    print("STRICT EVENT-MATCHER FEATURE EVALUATION")
    print("=" * 78)

    df = pd.read_csv(
        INPUT_FILE,
        encoding="utf-8-sig",
    )

    print(
        f"\nPairs: {len(df)}"
    )

    print(
        f"Unique articles: "
        f"{len(set(df['target_id']) | set(df['candidate_id']))}"
    )

    # -----------------------------------------------------
    # Add time
    # -----------------------------------------------------

    df = add_time_features(
        df
    )

    show_time_summary(
        df
    )

    # -----------------------------------------------------
    # Connected components
    # -----------------------------------------------------

    df = add_connected_components(
        df
    )

    show_component_summary(
        df
    )

    # -----------------------------------------------------
    # Numeric safety
    # -----------------------------------------------------

    all_features = set()

    for features in FEATURE_SETS.values():

        all_features.update(
            features
        )

    for feature in all_features:

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
    # Build identical folds for every experiment
    # -----------------------------------------------------

    folds = build_folds(
        df
    )

    # -----------------------------------------------------
    # Evaluate
    # -----------------------------------------------------

    summaries = []

    fold_assignment = None

    for (
        feature_name,
        features,
    ) in FEATURE_SETS.items():

        (
            summary,
            probabilities,
            folds_for_rows,
        ) = evaluate_feature_set(
            df,
            feature_name,
            features,
            folds,
        )

        summaries.append(
            summary
        )

        safe_name = (
            feature_name
            .lower()
            .replace(
                " + ",
                "_"
            )
            .replace(
                " ",
                "_"
            )
        )

        df[
            f"prob_{safe_name}"
        ] = probabilities

        if fold_assignment is None:

            fold_assignment = (
                folds_for_rows
            )

    df[
        "strict_cv_fold"
    ] = fold_assignment

    # -----------------------------------------------------
    # Results
    # -----------------------------------------------------

    results = pd.DataFrame(
        summaries
    )

    print()
    print("=" * 78)
    print("STRICT CONNECTED-COMPONENT CV RESULTS")
    print("=" * 78)

    main_columns = [
        "feature_set",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "auc",
        "f1_std",
        "auc_std",
    ]

    print(
        results[
            main_columns
        ]
        .round(4)
        .to_string(
            index=False
        )
    )

    print()
    print("=" * 78)
    print("STRICT OUT-OF-FOLD RESULTS")
    print("=" * 78)

    oof_columns = [
        "feature_set",
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
        f"Saved predictions to: "
        f"{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
