import csv
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from database.db import SessionLocal


# =========================================================
# CONFIGURATION
# =========================================================

INPUT_FILE = Path(
    "embeddings/event_candidates.csv"
)

OUTPUT_FILE = Path(
    "entities/event_training_dataset.csv"
)

NER_MODEL = "Davlan/xlm-roberta-base-ner-hrl"


# =========================================================
# MANUAL LABEL CORRECTIONS
# =========================================================

# Pair order does NOT matter.
#
# (15110, 15288) = same event
# (15113, 15465) = different event

LABEL_CORRECTIONS = {
    (15110, 15288): 2,
    (15113, 15465): 0,
}


# =========================================================
# MEDIA ALIASES
# =========================================================

MEDIA_ALIASES = {
    "5dias",
    "5días",
    "abc",
    "abc color",
    "adn",
    "agencia ip",
    "ahora cde",
    "amambay ahora",
    "amambay digital",
    "amambay news",
    "caazapa ahora",
    "cde hot",
    "concepcion al dia",
    "concepción al día",
    "cronica",
    "crónica",
    "diario paraguayo",
    "diario paraguayo noticias",
    "digital misiones",
    "el independiente",
    "el observador",
    "el poder",
    "extra",
    "hoy",
    "itapua en noticias",
    "itapúa en noticias",
    "la clave",
    "la jornada",
    "la nacion",
    "la nación",
    "la tribuna",
    "luque noticias",
    "mas encarnacion",
    "más encarnación",
    "megacadena",
    "monumental",
    "monumental 1080 am",
    "nanduti",
    "ñanduti",
    "noticias cde",
    "npy",
    "oviedo press",
    "pedro juan digital",
    "popular",
    "primera plana",
    "qap chaco news",
    "red digital san pedro",
    "resumen de noticias",
    "san lorenzo hoy",
    "san lorenzo py",
    "telefuturo",
    "the asuncion times",
    "tn press",
    "ultima hora",
    "última hora",
}


# =========================================================
# NORMALIZATION
# =========================================================

def normalize_text(value):
    if value is None:
        return ""

    value = str(value)

    value = unicodedata.normalize(
        "NFKC",
        value,
    )

    value = value.lower().strip()

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value


MEDIA_ALIASES = {
    normalize_text(x)
    for x in MEDIA_ALIASES
}


# =========================================================
# PAIR KEY
# =========================================================

def canonical_pair(
    article_a,
    article_b,
):
    """
    Event matching is symmetric.

    (A, B) and (B, A) therefore produce exactly
    the same key.
    """

    a = int(article_a)
    b = int(article_b)

    return tuple(
        sorted(
            (a, b)
        )
    )


# =========================================================
# SAFE CSV LOADING
# =========================================================

def detect_encoding(path):
    encodings = [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin1",
    ]

    raw = path.read_bytes()

    for encoding in encodings:
        try:
            raw.decode(
                encoding
            )

            return encoding

        except UnicodeDecodeError:
            continue

    raise RuntimeError(
        f"Could not determine encoding: {path}"
    )


def detect_delimiter(
    path,
    encoding,
):
    with open(
        path,
        "r",
        encoding=encoding,
        newline="",
    ) as f:

        sample = f.read(
            20000
        )

    try:

        dialect = csv.Sniffer().sniff(
            sample,
            delimiters=",;\t|",
        )

        return dialect.delimiter

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

        if candidates[delimiter] == 0:
            raise RuntimeError(
                "Could not detect CSV delimiter."
            )

        return delimiter


def read_csv_safely(path):
    if not path.exists():
        raise FileNotFoundError(
            f"File not found: {path}"
        )

    encoding = detect_encoding(
        path
    )

    delimiter = detect_delimiter(
        path,
        encoding,
    )

    print(
        f"CSV encoding: {encoding}"
    )

    print(
        f"CSV delimiter: {repr(delimiter)}"
    )

    return pd.read_csv(
        path,
        encoding=encoding,
        sep=delimiter,
        engine="python",
    )


# =========================================================
# CLEAN ORIGINAL DATA
# =========================================================

def clean_pairs(df):

    print()
    print("=" * 72)
    print("CLEANING PAIRS")
    print("=" * 72)

    original_count = len(
        df
    )

    print(
        f"Original rows: {original_count}"
    )

    # -----------------------------------------------------
    # Validate required columns
    # -----------------------------------------------------

    required = {
        "target_id",
        "candidate_id",
        "similarity",
        "event_label",
    }

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

    # -----------------------------------------------------
    # Numeric conversion
    # -----------------------------------------------------

    df["target_id"] = pd.to_numeric(
        df["target_id"],
        errors="coerce",
    )

    df["candidate_id"] = pd.to_numeric(
        df["candidate_id"],
        errors="coerce",
    )

    df["similarity"] = pd.to_numeric(
        df["similarity"],
        errors="coerce",
    )

    df["event_label"] = pd.to_numeric(
        df["event_label"],
        errors="coerce",
    )

    # -----------------------------------------------------
    # Remove invalid/unlabeled rows
    # -----------------------------------------------------

    before = len(
        df
    )

    df = df[
        df["target_id"].notna()
        & df["candidate_id"].notna()
        & df["similarity"].notna()
        & df["event_label"].notna()
    ].copy()

    print(
        "Removed unlabeled/invalid rows:",
        before - len(df),
    )

    df["target_id"] = (
        df["target_id"]
        .astype(int)
    )

    df["candidate_id"] = (
        df["candidate_id"]
        .astype(int)
    )

    df["event_label"] = (
        df["event_label"]
        .astype(int)
    )

    # Only valid labels
    df = df[
        df["event_label"].isin(
            [0, 1, 2]
        )
    ].copy()

    # -----------------------------------------------------
    # Create canonical unordered pair
    # -----------------------------------------------------

    canonical = df.apply(
        lambda row: canonical_pair(
            row["target_id"],
            row["candidate_id"],
        ),
        axis=1,
    )

    df[
        "pair_article_1"
    ] = [
        pair[0]
        for pair in canonical
    ]

    df[
        "pair_article_2"
    ] = [
        pair[1]
        for pair in canonical
    ]

    # -----------------------------------------------------
    # Apply manual corrections
    # -----------------------------------------------------

    corrections_applied = 0

    for (
        article_1,
        article_2,
    ), label in LABEL_CORRECTIONS.items():

        pair = canonical_pair(
            article_1,
            article_2,
        )

        mask = (
            (
                df[
                    "pair_article_1"
                ] == pair[0]
            )
            &
            (
                df[
                    "pair_article_2"
                ] == pair[1]
            )
        )

        count = int(
            mask.sum()
        )

        if count > 0:

            df.loc[
                mask,
                "event_label",
            ] = label

            corrections_applied += count

            print(
                f"Corrected pair "
                f"{pair[0]} ↔ {pair[1]} "
                f"to label {label} "
                f"({count} rows)"
            )

    print(
        "Rows affected by manual corrections:",
        corrections_applied,
    )

    # -----------------------------------------------------
    # Check for remaining conflicts
    # -----------------------------------------------------

    conflicts = (
        df
        .groupby(
            [
                "pair_article_1",
                "pair_article_2",
            ]
        )[
            "event_label"
        ]
        .nunique()
    )

    conflicts = conflicts[
        conflicts > 1
    ]

    if len(conflicts) > 0:

        print()
        print(
            "WARNING: Remaining conflicting pairs:"
        )

        print(
            conflicts.to_string()
        )

        raise RuntimeError(
            "Conflicting labels remain after corrections."
        )

    # -----------------------------------------------------
    # Count reversed/duplicate observations
    # -----------------------------------------------------

    before_dedup = len(
        df
    )

    # Sort so result is deterministic.
    #
    # We retain the first textual representation of the
    # pair, but the canonical IDs are also preserved.
    df = (
        df
        .sort_values(
            [
                "pair_article_1",
                "pair_article_2",
            ]
        )
        .drop_duplicates(
            subset=[
                "pair_article_1",
                "pair_article_2",
            ],
            keep="first",
        )
        .reset_index(
            drop=True
        )
    )

    removed_duplicates = (
        before_dedup
        - len(df)
    )

    print(
        "Removed duplicate/reversed pairs:",
        removed_duplicates,
    )

    print(
        f"Final unique labeled pairs: {len(df)}"
    )

    print()
    print(
        "Label distribution:"
    )

    print(
        df[
            "event_label"
        ]
        .value_counts()
        .sort_index()
        .to_string()
    )

    return df


# =========================================================
# LOAD ENTITIES
# =========================================================

def load_entities(
    session,
    article_ids,
):
    article_ids = [
        int(x)
        for x in article_ids
    ]

    rows = session.execute(
        text(
            """
            SELECT
                article_id,
                normalized_text,
                entity_type,
                confidence

            FROM article_entities

            WHERE model = :model
              AND article_id = ANY(:article_ids)
            """
        ),
        {
            "model":
                NER_MODEL,

            "article_ids":
                article_ids,
        },
    ).mappings().all()

    entities = defaultdict(
        list
    )

    for row in rows:

        entity_text = normalize_text(
            row[
                "normalized_text"
            ]
        )

        if not entity_text:
            continue

        entities[
            int(
                row[
                    "article_id"
                ]
            )
        ].append(
            {
                "text":
                    entity_text,

                "type":
                    row[
                        "entity_type"
                    ],

                "confidence":
                    row[
                        "confidence"
                    ],
            }
        )

    return entities


# =========================================================
# ENTITY SET
# =========================================================

def get_entity_set(
    article_entities,
    entity_type=None,
    filter_media=True,
):
    result = set()

    for entity in article_entities:

        if (
            entity_type is not None
            and entity["type"] != entity_type
        ):
            continue

        value = entity[
            "text"
        ]

        if (
            filter_media
            and value in MEDIA_ALIASES
        ):
            continue

        result.add(
            value
        )

    return result


# =========================================================
# JACCARD
# =========================================================

def jaccard(
    set_a,
    set_b,
):
    union = (
        set_a
        | set_b
    )

    if not union:
        return 0.0

    return (
        len(
            set_a
            & set_b
        )
        / len(union)
    )


# =========================================================
# IDF
# =========================================================

def calculate_idf(
    entities,
    article_ids,
):
    """
    Exploratory IDF calculated across all articles in the
    training dataset.

    Basic NER remains our primary feature set, but keeping
    these features lets us test IDF again if desired.
    """

    document_frequency = defaultdict(
        int
    )

    article_ids = set(
        article_ids
    )

    article_count = len(
        article_ids
    )

    for article_id in article_ids:

        article_entities = (
            entities.get(
                article_id,
                [],
            )
        )

        unique_entities = get_entity_set(
            article_entities,
            filter_media=True,
        )

        for entity in unique_entities:

            document_frequency[
                entity
            ] += 1

    idf = {}

    for entity, frequency in (
        document_frequency.items()
    ):

        idf[entity] = (
            math.log(
                (article_count + 1)
                / (frequency + 1)
            )
            + 1
        )

    return idf


def weighted_overlap(
    set_a,
    set_b,
    idf,
):
    shared = (
        set_a
        & set_b
    )

    return sum(
        idf.get(
            entity,
            1.0,
        )
        for entity in shared
    )


def weighted_jaccard(
    set_a,
    set_b,
    idf,
):
    union = (
        set_a
        | set_b
    )

    if not union:
        return 0.0

    shared = (
        set_a
        & set_b
    )

    numerator = sum(
        idf.get(
            entity,
            1.0,
        )
        for entity in shared
    )

    denominator = sum(
        idf.get(
            entity,
            1.0,
        )
        for entity in union
    )

    if denominator == 0:
        return 0.0

    return (
        numerator
        / denominator
    )


# =========================================================
# BUILD FEATURES
# =========================================================

def build_entity_features(
    df,
    entities,
    idf,
):
    feature_rows = []

    for _, row in df.iterrows():

        target_id = int(
            row[
                "target_id"
            ]
        )

        candidate_id = int(
            row[
                "candidate_id"
            ]
        )

        target_entities = (
            entities.get(
                target_id,
                [],
            )
        )

        candidate_entities = (
            entities.get(
                candidate_id,
                [],
            )
        )

        # ---------------------------------------------
        # All filtered entities
        # ---------------------------------------------

        target_all = get_entity_set(
            target_entities,
        )

        candidate_all = get_entity_set(
            candidate_entities,
        )

        # ---------------------------------------------
        # Persons
        # ---------------------------------------------

        target_per = get_entity_set(
            target_entities,
            entity_type="PER",
        )

        candidate_per = get_entity_set(
            candidate_entities,
            entity_type="PER",
        )

        # ---------------------------------------------
        # Organizations
        # ---------------------------------------------

        target_org = get_entity_set(
            target_entities,
            entity_type="ORG",
        )

        candidate_org = get_entity_set(
            candidate_entities,
            entity_type="ORG",
        )

        # ---------------------------------------------
        # Locations
        # ---------------------------------------------

        target_loc = get_entity_set(
            target_entities,
            entity_type="LOC",
        )

        candidate_loc = get_entity_set(
            candidate_entities,
            entity_type="LOC",
        )

        # ---------------------------------------------
        # Shared sets
        # ---------------------------------------------

        shared_all = (
            target_all
            & candidate_all
        )

        shared_per = (
            target_per
            & candidate_per
        )

        shared_org = (
            target_org
            & candidate_org
        )

        shared_loc = (
            target_loc
            & candidate_loc
        )

        feature_rows.append(
            {
                "target_entity_count":
                    len(
                        target_all
                    ),

                "candidate_entity_count":
                    len(
                        candidate_all
                    ),

                "shared_entities":
                    len(
                        shared_all
                    ),

                "shared_per":
                    len(
                        shared_per
                    ),

                "shared_org":
                    len(
                        shared_org
                    ),

                "shared_loc":
                    len(
                        shared_loc
                    ),

                "entity_jaccard":
                    jaccard(
                        target_all,
                        candidate_all,
                    ),

                "idf_overlap":
                    weighted_overlap(
                        target_all,
                        candidate_all,
                        idf,
                    ),

                "idf_jaccard":
                    weighted_jaccard(
                        target_all,
                        candidate_all,
                        idf,
                    ),

                "shared_entity_names":
                    " | ".join(
                        sorted(
                            shared_all
                        )
                    ),

                "shared_person_names":
                    " | ".join(
                        sorted(
                            shared_per
                        )
                    ),

                "shared_org_names":
                    " | ".join(
                        sorted(
                            shared_org
                        )
                    ),

                "shared_location_names":
                    " | ".join(
                        sorted(
                            shared_loc
                        )
                    ),
            }
        )

    features = pd.DataFrame(
        feature_rows
    )

    return pd.concat(
        [
            df.reset_index(
                drop=True
            ),
            features,
        ],
        axis=1,
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 72)
    print("BUILD EVENT TRAINING DATASET")
    print("=" * 72)

    # -----------------------------------------------------
    # Load
    # -----------------------------------------------------

    df = read_csv_safely(
        INPUT_FILE
    )

    df.columns = [
        str(column).strip()
        for column in df.columns
    ]

    # -----------------------------------------------------
    # Clean labels and pairs
    # -----------------------------------------------------

    df = clean_pairs(
        df
    )

    # -----------------------------------------------------
    # Collect every article involved
    # -----------------------------------------------------

    article_ids = set(
        df[
            "target_id"
        ].tolist()
    )

    article_ids.update(
        df[
            "candidate_id"
        ].tolist()
    )

    print()
    print("=" * 72)
    print("ENTITY EXTRACTION COVERAGE")
    print("=" * 72)

    print(
        f"Unique articles: "
        f"{len(article_ids)}"
    )

    # -----------------------------------------------------
    # Load NER
    # -----------------------------------------------------

    session = SessionLocal()

    try:

        entities = load_entities(
            session,
            article_ids,
        )

    finally:

        session.close()

    articles_with_entities = (
        set(
            entities.keys()
        )
        & article_ids
    )

    articles_without_entities = (
        article_ids
        - articles_with_entities
    )

    print(
        f"Articles with entities: "
        f"{len(articles_with_entities)}"
    )

    print(
        f"Articles without entities: "
        f"{len(articles_without_entities)}"
    )

    if articles_without_entities:

        print(
            "IDs without entities:"
        )

        print(
            sorted(
                articles_without_entities
            )
        )

    # -----------------------------------------------------
    # IDF
    # -----------------------------------------------------

    idf = calculate_idf(
        entities,
        article_ids,
    )

    print(
        f"Unique filtered entities: "
        f"{len(idf)}"
    )

    # -----------------------------------------------------
    # Features
    # -----------------------------------------------------

    result = build_entity_features(
        df,
        entities,
        idf,
    )

    # -----------------------------------------------------
    # Binary production target
    # -----------------------------------------------------

    result[
        "same_event"
    ] = (
        result[
            "event_label"
        ] == 2
    ).astype(
        int
    )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    print()
    print("=" * 72)
    print("FINAL TRAINING DATASET")
    print("=" * 72)

    print(
        f"Pairs: "
        f"{len(result)}"
    )

    print(
        f"Unique target articles: "
        f"{result['target_id'].nunique()}"
    )

    print(
        f"Unique articles overall: "
        f"{len(article_ids)}"
    )

    print()
    print(
        "Three-class labels:"
    )

    print(
        result[
            "event_label"
        ]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print()
    print(
        "Binary production target:"
    )

    print(
        result[
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
    # Feature summary
    # -----------------------------------------------------

    feature_columns = [
        "similarity",
        "shared_entities",
        "shared_per",
        "shared_org",
        "shared_loc",
        "entity_jaccard",
        "idf_overlap",
        "idf_jaccard",
    ]

    print()
    print("=" * 72)
    print("FEATURE SUMMARY BY ORIGINAL LABEL")
    print("=" * 72)

    summary = (
        result
        .groupby(
            "event_label"
        )[
            feature_columns
        ]
        .agg(
            [
                "mean",
                "median",
            ]
        )
        .round(
            4
        )
    )

    print(
        summary.to_string()
    )

    print()
    print(
        f"Saved to: "
        f"{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
