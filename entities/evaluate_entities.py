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
    "embeddings/event_candidates_2.csv"
)

OUTPUT_FILE = Path(
    "entities/event_candidates_with_entities.csv"
)

NER_MODEL = "Davlan/xlm-roberta-base-ner-hrl"


# =========================================================
# MEDIA NAMES
# =========================================================

# These entities may legitimately be detected by NER,
# but they should not provide evidence that two articles
# describe the same event.
#
# We keep them in article_entities and filter them only
# during event-feature generation.

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
# TEXT NORMALIZATION
# =========================================================

def normalize_text(value: str) -> str:
    """
    Normalize entity text while preserving accents.
    """

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
# SAFE CSV LOADING
# =========================================================

def detect_encoding(path: Path) -> str:
    """
    Try common encodings without silently dropping
    characters.
    """

    encodings = [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin1",
    ]

    raw = path.read_bytes()

    for encoding in encodings:
        try:
            raw.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue

    raise RuntimeError(
        f"Could not determine encoding for {path}"
    )


def detect_delimiter(
    path: Path,
    encoding: str,
) -> str:
    """
    Detect common CSV delimiters.
    """

    with open(
        path,
        "r",
        encoding=encoding,
        newline="",
    ) as f:

        sample = f.read(10000)

    try:

        dialect = csv.Sniffer().sniff(
            sample,
            delimiters=",;\t|",
        )

        return dialect.delimiter

    except csv.Error:

        # Fallback: count delimiters in header
        first_line = sample.splitlines()[0]

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


def read_csv_safely(path: Path) -> pd.DataFrame:
    """
    Automatically determine encoding and delimiter.
    """

    if not path.exists():
        raise FileNotFoundError(
            f"Input file not found: {path}"
        )

    encoding = detect_encoding(
        path
    )

    delimiter = detect_delimiter(
        path,
        encoding,
    )

    printable_delimiter = {
        ",": "comma (,)",
        ";": "semicolon (;)",
        "\t": "tab",
        "|": "pipe (|)",
    }.get(
        delimiter,
        repr(delimiter),
    )

    print(
        f"CSV encoding: {encoding}"
    )

    print(
        f"CSV delimiter: {printable_delimiter}"
    )

    try:

        df = pd.read_csv(
            path,
            encoding=encoding,
            sep=delimiter,
            quotechar='"',
            engine="python",
        )

    except pd.errors.ParserError as exc:

        raise RuntimeError(
            "\nCould not parse the CSV correctly.\n"
            f"Encoding detected: {encoding}\n"
            f"Delimiter detected: {repr(delimiter)}\n"
            "\nOriginal error:\n"
            f"{exc}"
        ) from exc

    return df


# =========================================================
# LOAD ENTITIES FROM POSTGRESQL
# =========================================================

def load_entities(
    session,
    article_ids,
):
    """
    Load NER entities for all articles used in the
    labeled candidate pairs.
    """

    article_ids = [
        int(x)
        for x in article_ids
    ]

    if not article_ids:
        return defaultdict(list)

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
            "model": NER_MODEL,
            "article_ids": article_ids,
        },
    ).mappings().all()

    entities = defaultdict(list)

    for row in rows:

        entity = normalize_text(
            row["normalized_text"]
        )

        if not entity:
            continue

        entities[
            int(row["article_id"])
        ].append(
            {
                "text": entity,
                "type": row["entity_type"],
                "confidence": row["confidence"],
            }
        )

    return entities


# =========================================================
# ENTITY SETS
# =========================================================

def get_entity_set(
    article_entities,
    entity_type=None,
    filter_media=False,
):
    """
    Convert entities belonging to an article into a set.

    Optionally:
      - restrict to PER / ORG / LOC
      - remove known media entities
    """

    result = set()

    for entity in article_entities:

        if (
            entity_type is not None
            and entity["type"] != entity_type
        ):
            continue

        entity_text = entity["text"]

        if (
            filter_media
            and entity_text in MEDIA_ALIASES
        ):
            continue

        result.add(
            entity_text
        )

    return result


# =========================================================
# JACCARD SIMILARITY
# =========================================================

def jaccard(a, b):
    """
    |A intersection B| / |A union B|
    """

    if not a and not b:
        return 0.0

    union = a | b

    if not union:
        return 0.0

    return len(a & b) / len(union)


# =========================================================
# DOCUMENT FREQUENCY + IDF
# =========================================================

def calculate_idf(entities):
    """
    Calculate smoothed IDF for each entity.

    Common entities such as Paraguay receive less weight.
    Rare entities receive more weight.
    """

    document_frequency = defaultdict(int)

    article_count = len(entities)

    if article_count == 0:
        return {}

    for article_entities in entities.values():

        unique_entities = {
            entity["text"]
            for entity in article_entities
            if entity["text"] not in MEDIA_ALIASES
        }

        for entity in unique_entities:
            document_frequency[entity] += 1

    idf = {}

    for entity, df in document_frequency.items():

        idf[entity] = (
            math.log(
                (article_count + 1)
                / (df + 1)
            )
            + 1
        )

    return idf


# =========================================================
# IDF-WEIGHTED OVERLAP
# =========================================================

def weighted_overlap(
    entities_a,
    entities_b,
    idf,
):
    """
    Sum the IDF weights of entities shared by both
    articles.
    """

    shared = (
        entities_a
        & entities_b
    )

    if not shared:
        return 0.0

    return sum(
        idf.get(
            entity,
            1.0,
        )
        for entity in shared
    )


def weighted_jaccard(
    entities_a,
    entities_b,
    idf,
):
    """
    IDF-weighted Jaccard similarity.
    """

    union = (
        entities_a
        | entities_b
    )

    if not union:
        return 0.0

    intersection = (
        entities_a
        & entities_b
    )

    numerator = sum(
        idf.get(
            entity,
            1.0,
        )
        for entity in intersection
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
# VALIDATE INPUT COLUMNS
# =========================================================

def validate_columns(df):
    """
    Make sure the candidate file contains the fields
    required by this experiment.
    """

    required_columns = {
        "target_id",
        "candidate_id",
        "similarity",
        "event_label",
    }

    missing = (
        required_columns
        - set(df.columns)
    )

    if missing:

        print(
            "\nColumns found in CSV:"
        )

        for column in df.columns:
            print(
                f"  - {repr(column)}"
            )

        raise RuntimeError(
            "\nMissing required columns: "
            + ", ".join(
                sorted(missing)
            )
        )


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 70)
    print("ENTITY FEATURE EVALUATION")
    print("=" * 70)

    # -----------------------------------------------------
    # Load CSV
    # -----------------------------------------------------

    df = read_csv_safely(
        INPUT_FILE
    )

    # Clean column names
    df.columns = [
        str(column).strip()
        for column in df.columns
    ]

    print(
        f"\nRows in file: {len(df)}"
    )

    print(
        f"Columns: {len(df.columns)}"
    )

    validate_columns(
        df
    )

    # -----------------------------------------------------
    # Keep manually labeled rows
    # -----------------------------------------------------

    df = df[
        df["event_label"].notna()
    ].copy()

    # Convert labels safely
    df["event_label"] = pd.to_numeric(
        df["event_label"],
        errors="coerce",
    )

    df = df[
        df["event_label"].notna()
    ].copy()

    df["event_label"] = (
        df["event_label"]
        .astype(int)
    )

    # Only expected labels
    df = df[
        df["event_label"].isin(
            [0, 1, 2]
        )
    ].copy()

    print(
        f"Labeled rows: {len(df)}"
    )

    if df.empty:
        raise RuntimeError(
            "No labeled rows were found."
        )

    # -----------------------------------------------------
    # Convert IDs to numeric
    # -----------------------------------------------------

    df["target_id"] = pd.to_numeric(
        df["target_id"],
        errors="coerce",
    )

    df["candidate_id"] = pd.to_numeric(
        df["candidate_id"],
        errors="coerce",
    )

    df = df[
        df["target_id"].notna()
        & df["candidate_id"].notna()
    ].copy()

    df["target_id"] = (
        df["target_id"]
        .astype(int)
    )

    df["candidate_id"] = (
        df["candidate_id"]
        .astype(int)
    )

    # Similarity should also be numeric
    df["similarity"] = pd.to_numeric(
        df["similarity"],
        errors="coerce",
    )

    # -----------------------------------------------------
    # Collect article IDs
    # -----------------------------------------------------

    article_ids = set(
        df["target_id"].tolist()
        + df["candidate_id"].tolist()
    )

    print(
        f"Unique articles: "
        f"{len(article_ids)}"
    )

    # -----------------------------------------------------
    # Load entities
    # -----------------------------------------------------

    session = SessionLocal()

    try:

        entities = load_entities(
            session,
            article_ids,
        )

    finally:

        session.close()

    print(
        f"Articles with entities: "
        f"{len(entities)}"
    )

    articles_without_entities = (
        article_ids
        - set(entities.keys())
    )

    print(
        f"Articles without entities: "
        f"{len(articles_without_entities)}"
    )

    # -----------------------------------------------------
    # Calculate IDF
    # -----------------------------------------------------

    idf = calculate_idf(
        entities
    )

    print(
        f"Unique filtered entities: "
        f"{len(idf)}"
    )

    # -----------------------------------------------------
    # Generate pair-level features
    # -----------------------------------------------------

    feature_rows = []

    for _, row in df.iterrows():

        target_id = int(
            row["target_id"]
        )

        candidate_id = int(
            row["candidate_id"]
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

        # -------------------------------------------------
        # Raw entities
        # -------------------------------------------------

        target_all = get_entity_set(
            target_entities
        )

        candidate_all = get_entity_set(
            candidate_entities
        )

        # -------------------------------------------------
        # Media-filtered entities
        # -------------------------------------------------

        target_filtered = get_entity_set(
            target_entities,
            filter_media=True,
        )

        candidate_filtered = get_entity_set(
            candidate_entities,
            filter_media=True,
        )

        # -------------------------------------------------
        # Persons
        # -------------------------------------------------

        target_per = get_entity_set(
            target_entities,
            entity_type="PER",
            filter_media=True,
        )

        candidate_per = get_entity_set(
            candidate_entities,
            entity_type="PER",
            filter_media=True,
        )

        # -------------------------------------------------
        # Organizations
        # -------------------------------------------------

        target_org = get_entity_set(
            target_entities,
            entity_type="ORG",
            filter_media=True,
        )

        candidate_org = get_entity_set(
            candidate_entities,
            entity_type="ORG",
            filter_media=True,
        )

        # -------------------------------------------------
        # Locations
        # -------------------------------------------------

        target_loc = get_entity_set(
            target_entities,
            entity_type="LOC",
            filter_media=True,
        )

        candidate_loc = get_entity_set(
            candidate_entities,
            entity_type="LOC",
            filter_media=True,
        )

        # -------------------------------------------------
        # Shared entities
        # -------------------------------------------------

        shared_all = (
            target_all
            & candidate_all
        )

        shared_filtered = (
            target_filtered
            & candidate_filtered
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

        # -------------------------------------------------
        # Features
        # -------------------------------------------------

        features = {

            # Number of entities in each article
            "target_entity_count":
                len(target_filtered),

            "candidate_entity_count":
                len(candidate_filtered),

            # Raw overlap, before media filtering
            "shared_entities_raw":
                len(shared_all),

            # Media-filtered overlap
            "shared_entities":
                len(shared_filtered),

            # Type-specific overlap
            "shared_per":
                len(shared_per),

            "shared_org":
                len(shared_org),

            "shared_loc":
                len(shared_loc),

            # Standard Jaccard
            "entity_jaccard_raw":
                jaccard(
                    target_all,
                    candidate_all,
                ),

            "entity_jaccard":
                jaccard(
                    target_filtered,
                    candidate_filtered,
                ),

            # IDF-weighted overlap
            "idf_overlap":
                weighted_overlap(
                    target_filtered,
                    candidate_filtered,
                    idf,
                ),

            "idf_jaccard":
                weighted_jaccard(
                    target_filtered,
                    candidate_filtered,
                    idf,
                ),

            # Useful for manual inspection
            "shared_entity_names":
                " | ".join(
                    sorted(
                        shared_filtered
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

        feature_rows.append(
            features
        )

    # -----------------------------------------------------
    # Combine original data + new features
    # -----------------------------------------------------

    features_df = pd.DataFrame(
        feature_rows
    )

    result = pd.concat(
        [
            df.reset_index(
                drop=True
            ),
            features_df,
        ],
        axis=1,
    )

    # -----------------------------------------------------
    # Save result
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
    print("=" * 70)
    print("FEATURE SUMMARY")
    print("=" * 70)

    columns = [
        "similarity",
        "shared_entities",
        "shared_per",
        "shared_org",
        "shared_loc",
        "entity_jaccard",
        "idf_overlap",
        "idf_jaccard",
    ]

    summary = (
        result
        .groupby("event_label")[
            columns
        ]
        .agg(
            [
                "count",
                "mean",
                "median",
            ]
        )
        .round(4)
    )

    print(
        summary.to_string()
    )

    # -----------------------------------------------------
    # Label distribution
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("LABEL DISTRIBUTION")
    print("=" * 70)

    print(
        result[
            "event_label"
        ]
        .value_counts()
        .sort_index()
        .to_string()
    )

    # -----------------------------------------------------
    # Example high-overlap pairs
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("TOP ENTITY-OVERLAP PAIRS")
    print("=" * 70)

    inspection_columns = [
        "target_id",
        "candidate_id",
        "similarity",
        "event_label",
        "shared_entities",
        "entity_jaccard",
        "idf_jaccard",
        "shared_entity_names",
    ]

    top_pairs = (
        result
        .sort_values(
            [
                "idf_jaccard",
                "similarity",
            ],
            ascending=False,
        )
        [inspection_columns]
        .head(10)
    )

    print(
        top_pairs.to_string(
            index=False
        )
    )

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)

    print(
        f"Saved to: "
        f"{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()