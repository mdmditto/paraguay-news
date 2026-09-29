from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
import unicodedata

import joblib
import numpy as np
import pandas as pd

from sqlalchemy import text

from database.db import SessionLocal


# =========================================================
# CONFIGURATION
# =========================================================

MODEL_FILE = Path(
    "events/models/event_matcher_v1.joblib"
)

OUTPUT_DIR = Path(
    "events/output"
)

EVENTS_OUTPUT = (
    OUTPUT_DIR
    / "simulated_events.csv"
)

ASSIGNMENTS_OUTPUT = (
    OUTPUT_DIR
    / "simulated_event_articles.csv"
)

DECISIONS_OUTPUT = (
    OUTPUT_DIR
    / "simulated_event_decisions.csv"
)


# =========================================================
# MODELS
# =========================================================

EMBEDDING_MODEL = (
    "jinaai/jina-embeddings-v5-text-small"
)

EMBEDDING_TASK = "text-matching"

NER_MODEL = (
    "Davlan/xlm-roberta-base-ner-hrl"
)


# =========================================================
# FEATURE ORDER
# =========================================================

# IMPORTANT:
# This must match the exact feature order used when
# event_matcher_v1.joblib was trained.
FEATURES = [
    "similarity",
    "shared_per",
    "shared_org",
    "shared_loc",
    "entity_jaccard",
]


# =========================================================
# RETRIEVAL PARAMETERS
# =========================================================

# Retrieve the 20 most semantically similar PREVIOUS
# articles.
TOP_K_NEIGHBORS = 20


# Do not send very weak semantic candidates through the
# pair classifier.
MIN_RETRIEVAL_SIMILARITY = 0.75


# =========================================================
# PAIR PROBABILITY THRESHOLDS
# =========================================================

# Strong evidence that two articles belong to the same
# event.
STRONG_PAIR_THRESHOLD = 0.75


# Weaker supporting evidence.
SUPPORT_PAIR_THRESHOLD = 0.50


# Used for:
#
# 1. bootstrapping singleton events
# 2. very strong evidence for established events
VERY_STRONG_PAIR_THRESHOLD = 0.90


# =========================================================
# EVENT ASSIGNMENT PARAMETERS
# =========================================================

# For an established event, two strong matches are enough.
MIN_STRONG_MATCHES = 2


# Or:
#
# one very strong match
# +
# at least two supporting matches
MIN_SUPPORT_MATCHES = 2


# Only the strongest N retrieved articles from one event
# are used when summarizing evidence.
MAX_EVENT_EVIDENCE = 5


# =========================================================
# MEDIA ENTITY FILTER
# =========================================================

MEDIA_ALIASES = {
    "5dias",
    "5 dias",
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
    "cronica",
    "diario paraguayo",
    "diario paraguayo noticias",
    "digital misiones",
    "el independiente",
    "el observador",
    "el poder",
    "extra",
    "hoy",
    "itapua en noticias",
    "la clave",
    "la jornada",
    "la nacion",
    "la tribuna",
    "luque noticias",
    "mas encarnacion",
    "megacadena",
    "monumental",
    "monumental 1080 am",
    "nanduti",
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
}


# =========================================================
# DATA STRUCTURE
# =========================================================

@dataclass
class SimulatedEvent:

    event_id: int

    article_ids: list[int] = field(
        default_factory=list
    )

    title: str = ""

    first_seen_at: datetime | None = None

    last_seen_at: datetime | None = None


# =========================================================
# NORMALIZATION
# =========================================================

def normalize_text(value):

    if value is None:
        return ""

    value = str(
        value
    ).strip().lower()

    value = unicodedata.normalize(
        "NFKD",
        value,
    )

    value = "".join(
        character
        for character in value
        if not unicodedata.combining(
            character
        )
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


# =========================================================
# MEDIA ENTITY FILTER
# =========================================================

def is_media_entity(entity):

    normalized = normalize_text(
        entity
    )

    return (
        normalized
        in MEDIA_ALIASES
    )


# =========================================================
# LOAD MODEL
# =========================================================

def load_model():

    print("=" * 78)
    print("LOADING EVENT MATCHER")
    print("=" * 78)

    if not MODEL_FILE.exists():

        raise FileNotFoundError(
            f"Model not found: "
            f"{MODEL_FILE}"
        )

    model = joblib.load(
        MODEL_FILE
    )

    print(
        f"Loaded: "
        f"{MODEL_FILE}"
    )

    return model


# =========================================================
# LOAD ARTICLES
# =========================================================

def load_articles(session):

    print()
    print("=" * 78)
    print("LOADING ARTICLES")
    print("=" * 78)

    query = text(
        """
        SELECT
            a.id,
            a.title,
            a.published_at,
            a.scraped_at,
            s.name AS source_name

        FROM articles a

        JOIN sources s
            ON s.id = a.source_id

        JOIN article_embeddings ae
            ON ae.article_id = a.id

        WHERE ae.model = :embedding_model
          AND ae.task = :embedding_task

        ORDER BY
            COALESCE(
                a.published_at,
                a.scraped_at
            ),
            a.id
        """
    )

    rows = (
        session.execute(
            query,
            {
                "embedding_model":
                    EMBEDDING_MODEL,

                "embedding_task":
                    EMBEDDING_TASK,
            },
        )
        .mappings()
        .all()
    )

    articles = [
        dict(row)
        for row in rows
    ]

    print(
        f"Articles available: "
        f"{len(articles)}"
    )

    if articles:

        first_time = (
            articles[0]["published_at"]
            or articles[0]["scraped_at"]
        )

        last_time = (
            articles[-1]["published_at"]
            or articles[-1]["scraped_at"]
        )

        print(
            f"First article time: "
            f"{first_time}"
        )

        print(
            f"Last article time: "
            f"{last_time}"
        )

    return articles


# =========================================================
# LOAD ENTITIES
# =========================================================

def load_entities(
    session,
    article_ids,
):

    print()
    print("=" * 78)
    print("LOADING ARTICLE ENTITIES")
    print("=" * 78)

    rows = (
        session.execute(
            text(
                """
                SELECT
                    article_id,
                    normalized_text,
                    entity_type,
                    confidence

                FROM article_entities

                WHERE model = :ner_model
                  AND article_id = ANY(:article_ids)
                """
            ),
            {
                "ner_model":
                    NER_MODEL,

                "article_ids":
                    article_ids,
            },
        )
        .mappings()
        .all()
    )

    entities = defaultdict(
        lambda: {
            "PER": set(),
            "ORG": set(),
            "LOC": set(),
        }
    )

    for row in rows:

        article_id = int(
            row[
                "article_id"
            ]
        )

        entity_type = row[
            "entity_type"
        ]

        entity_text = normalize_text(
            row[
                "normalized_text"
            ]
        )

        if entity_type not in {
            "PER",
            "ORG",
            "LOC",
        }:

            continue

        if not entity_text:
            continue

        if is_media_entity(
            entity_text
        ):

            continue

        entities[
            article_id
        ][
            entity_type
        ].add(
            entity_text
        )

    print(
        f"Entity rows loaded: "
        f"{len(rows)}"
    )

    print(
        f"Articles with entities: "
        f"{len(entities)}"
    )

    print(
        f"Articles without entities: "
        f"{len(article_ids) - len(entities)}"
    )

    return entities


# =========================================================
# CALCULATE ENTITY FEATURES
# =========================================================

def calculate_entity_features(
    article_a,
    article_b,
    entities,
):

    a = entities[
        article_a
    ]

    b = entities[
        article_b
    ]

    shared_per = len(
        a["PER"]
        &
        b["PER"]
    )

    shared_org = len(
        a["ORG"]
        &
        b["ORG"]
    )

    shared_loc = len(
        a["LOC"]
        &
        b["LOC"]
    )

    all_a = (
        a["PER"]
        |
        a["ORG"]
        |
        a["LOC"]
    )

    all_b = (
        b["PER"]
        |
        b["ORG"]
        |
        b["LOC"]
    )

    union = (
        all_a
        |
        all_b
    )

    intersection = (
        all_a
        &
        all_b
    )

    if union:

        entity_jaccard = (
            len(intersection)
            /
            len(union)
        )

    else:

        entity_jaccard = 0.0

    return {
        "shared_per":
            shared_per,

        "shared_org":
            shared_org,

        "shared_loc":
            shared_loc,

        "entity_jaccard":
            entity_jaccard,
    }


# =========================================================
# RETRIEVE PREVIOUS NEIGHBORS
# =========================================================

def get_nearest_previous_articles(
    session,
    article_id,
    processed_article_ids,
):

    if not processed_article_ids:

        return []

    query = text(
        """
        SELECT
            candidate.article_id
                AS candidate_id,

            1 - (
                candidate.embedding
                <=>
                target.embedding
            ) AS similarity

        FROM article_embeddings target

        JOIN article_embeddings candidate
            ON candidate.model = target.model
           AND candidate.task = target.task

        WHERE target.article_id = :article_id

          AND target.model = :embedding_model

          AND target.task = :embedding_task

          AND candidate.article_id = ANY(
              :processed_article_ids
          )

          AND candidate.article_id != :article_id

        ORDER BY
            candidate.embedding
            <=>
            target.embedding

        LIMIT :top_k
        """
    )

    rows = (
        session.execute(
            query,
            {
                "article_id":
                    article_id,

                "embedding_model":
                    EMBEDDING_MODEL,

                "embedding_task":
                    EMBEDDING_TASK,

                "processed_article_ids":
                    list(
                        processed_article_ids
                    ),

                "top_k":
                    TOP_K_NEIGHBORS,
            },
        )
        .mappings()
        .all()
    )

    neighbors = []

    for row in rows:

        similarity = float(
            row[
                "similarity"
            ]
        )

        if (
            similarity
            <
            MIN_RETRIEVAL_SIMILARITY
        ):

            continue

        neighbors.append(
            {
                "candidate_id":
                    int(
                        row[
                            "candidate_id"
                        ]
                    ),

                "similarity":
                    similarity,
            }
        )

    return neighbors


# =========================================================
# SCORE ARTICLE PAIR
# =========================================================

def score_pair(
    model,
    target_id,
    candidate_id,
    similarity,
    entities,
):

    entity_features = (
        calculate_entity_features(
            target_id,
            candidate_id,
            entities,
        )
    )

    feature_row = {
        "similarity":
            similarity,

        **entity_features,
    }

    X = pd.DataFrame(
        [
            feature_row
        ],
        columns=FEATURES,
    )

    probability = float(
        model.predict_proba(
            X
        )[0, 1]
    )

    return {
        **feature_row,

        "probability":
            probability,
    }


# =========================================================
# GROUP ARTICLE CANDIDATES BY EVENT
# =========================================================

def group_candidates_by_event(
    scored_neighbors,
    article_to_event,
):

    event_candidates = defaultdict(
        list
    )

    for candidate in scored_neighbors:

        candidate_id = candidate[
            "candidate_id"
        ]

        event_id = (
            article_to_event.get(
                candidate_id
            )
        )

        if event_id is None:
            continue

        event_candidates[
            event_id
        ].append(
            candidate
        )

    return event_candidates


# =========================================================
# SUMMARIZE EVENT EVIDENCE
# =========================================================

def summarize_event_evidence(
    event_id,
    candidates,
):

    # Highest probabilities first.
    candidates = sorted(
        candidates,
        key=lambda item:
            item[
                "probability"
            ],
        reverse=True,
    )

    # Avoid allowing a huge event to dominate simply
    # because it has many articles.
    candidates = candidates[
        :MAX_EVENT_EVIDENCE
    ]

    probabilities = [
        item[
            "probability"
        ]
        for item in candidates
    ]

    strong_matches = sum(
        probability
        >= STRONG_PAIR_THRESHOLD

        for probability
        in probabilities
    )

    support_matches = sum(
        probability
        >= SUPPORT_PAIR_THRESHOLD

        for probability
        in probabilities
    )

    max_probability = (
        max(
            probabilities
        )
        if probabilities
        else 0.0
    )

    mean_probability = (
        float(
            np.mean(
                probabilities
            )
        )
        if probabilities
        else 0.0
    )

    top_two = (
        probabilities[
            :2
        ]
    )

    top_two_mean = (
        float(
            np.mean(
                top_two
            )
        )
        if top_two
        else 0.0
    )

    return {
        "event_id":
            event_id,

        "retrieved_event_articles":
            len(candidates),

        "strong_matches":
            strong_matches,

        "support_matches":
            support_matches,

        "max_probability":
            max_probability,

        "mean_probability":
            mean_probability,

        "top_two_mean":
            top_two_mean,

        "evidence":
            candidates,
    }


# =========================================================
# EVENT ACCEPTANCE RULE
# =========================================================

def event_is_acceptable(
    evidence,
    actual_event_size,
):

    # =====================================================
    # RULE 1 — SINGLETON BOOTSTRAP
    #
    # A one-article event cannot provide two independent
    # supporting article matches.
    #
    # Therefore, allow the second article to join only
    # when the pairwise model is very confident.
    # =====================================================

    if actual_event_size == 1:

        return (
            evidence[
                "max_probability"
            ]
            >= VERY_STRONG_PAIR_THRESHOLD
        )

    # =====================================================
    # RULE 2 — ESTABLISHED EVENT
    #
    # At least two strong independent article matches.
    # =====================================================

    if (
        evidence[
            "strong_matches"
        ]
        >= MIN_STRONG_MATCHES
    ):

        return True

    # =====================================================
    # RULE 3 — VERY STRONG + SUPPORT
    #
    # One extremely strong pair plus at least one
    # additional supporting article.
    # =====================================================

    if (
        evidence[
            "max_probability"
        ]
        >= VERY_STRONG_PAIR_THRESHOLD

        and

        evidence[
            "support_matches"
        ]
        >= MIN_SUPPORT_MATCHES
    ):

        return True

    return False


# =========================================================
# CHOOSE BEST EVENT
# =========================================================

def choose_event(
    event_candidates,
    events,
):

    accepted_summaries = []

    all_summaries = []

    for (
        event_id,
        candidates,
    ) in event_candidates.items():

        summary = (
            summarize_event_evidence(
                event_id,
                candidates,
            )
        )

        actual_event_size = len(
            events[
                event_id
            ].article_ids
        )

        summary[
            "actual_event_size"
        ] = actual_event_size

        summary[
            "accepted"
        ] = event_is_acceptable(
            summary,
            actual_event_size,
        )

        all_summaries.append(
            summary
        )

        if summary[
            "accepted"
        ]:

            accepted_summaries.append(
                summary
            )

    if not accepted_summaries:

        return (
            None,
            [],
            all_summaries,
        )

    # -----------------------------------------------------
    # Rank accepted candidate events.
    #
    # Priority:
    #
    # 1. number of strong matches
    # 2. mean probability of top two matches
    # 3. maximum probability
    # 4. mean probability
    # -----------------------------------------------------

    accepted_summaries.sort(
        key=lambda item: (
            item[
                "strong_matches"
            ],
            item[
                "top_two_mean"
            ],
            item[
                "max_probability"
            ],
            item[
                "mean_probability"
            ],
        ),
        reverse=True,
    )

    return (
        accepted_summaries[
            0
        ],
        accepted_summaries,
        all_summaries,
    )


# =========================================================
# CREATE NEW EVENT
# =========================================================

def create_event(
    events,
    article,
):

    event_id = (
        len(events)
        + 1
    )

    timestamp = (
        article[
            "published_at"
        ]
        or article[
            "scraped_at"
        ]
    )

    event = SimulatedEvent(
        event_id=event_id,

        article_ids=[
            int(
                article[
                    "id"
                ]
            )
        ],

        title=article[
            "title"
        ],

        first_seen_at=timestamp,

        last_seen_at=timestamp,
    )

    events[
        event_id
    ] = event

    return event


# =========================================================
# ADD ARTICLE TO EXISTING EVENT
# =========================================================

def add_article_to_event(
    event,
    article,
):

    article_id = int(
        article[
            "id"
        ]
    )

    if (
        article_id
        not in event.article_ids
    ):

        event.article_ids.append(
            article_id
        )

    timestamp = (
        article[
            "published_at"
        ]
        or article[
            "scraped_at"
        ]
    )

    if timestamp is None:
        return

    if (
        event.first_seen_at is None
        or timestamp
        < event.first_seen_at
    ):

        event.first_seen_at = (
            timestamp
        )

    if (
        event.last_seen_at is None
        or timestamp
        > event.last_seen_at
    ):

        event.last_seen_at = (
            timestamp
        )


# =========================================================
# SIMULATION
# =========================================================

def simulate(
    session,
    model,
    articles,
    entities,
):

    print()
    print("=" * 78)
    print("BUILDING EVENTS — DRY RUN")
    print("=" * 78)

    events = {}

    article_to_event = {}

    processed_article_ids = []

    assignments = []

    decisions = []

    # =====================================================
    # DIAGNOSTICS
    # =====================================================

    total_neighbors_retrieved = 0

    total_scored_pairs = 0

    articles_with_neighbors = 0

    articles_with_pair_above_50 = 0

    articles_with_pair_above_75 = 0

    articles_with_pair_above_90 = 0

    singleton_bootstrap_matches = 0

    established_event_matches = 0

    multiple_accepted_event_cases = 0

    total_articles = len(
        articles
    )

    # =====================================================
    # PROCESS ARTICLES CHRONOLOGICALLY
    # =====================================================

    for index, article in enumerate(
        articles,
        start=1,
    ):

        article_id = int(
            article[
                "id"
            ]
        )

        # -------------------------------------------------
        # STEP 1
        # Retrieve semantically similar previous articles
        # -------------------------------------------------

        neighbors = (
            get_nearest_previous_articles(
                session=session,
                article_id=article_id,
                processed_article_ids=
                    processed_article_ids,
            )
        )

        total_neighbors_retrieved += len(
            neighbors
        )

        if neighbors:

            articles_with_neighbors += 1

        # -------------------------------------------------
        # STEP 2
        # Score every retrieved pair using Event Matcher v1
        # -------------------------------------------------

        scored_neighbors = []

        for neighbor in neighbors:

            pair_result = score_pair(
                model=model,

                target_id=article_id,

                candidate_id=neighbor[
                    "candidate_id"
                ],

                similarity=neighbor[
                    "similarity"
                ],

                entities=entities,
            )

            scored_neighbors.append(
                {
                    "candidate_id":
                        neighbor[
                            "candidate_id"
                        ],

                    **pair_result,
                }
            )

        total_scored_pairs += len(
            scored_neighbors
        )

        # -------------------------------------------------
        # Pair probability diagnostics
        # -------------------------------------------------

        max_pair_probability = None

        if scored_neighbors:

            max_pair_probability = max(
                item[
                    "probability"
                ]
                for item
                in scored_neighbors
            )

            if (
                max_pair_probability
                >= 0.50
            ):

                articles_with_pair_above_50 += 1

            if (
                max_pair_probability
                >= 0.75
            ):

                articles_with_pair_above_75 += 1

            if (
                max_pair_probability
                >= 0.90
            ):

                articles_with_pair_above_90 += 1

        # -------------------------------------------------
        # STEP 3
        # Convert candidate ARTICLES into candidate EVENTS
        # -------------------------------------------------

        event_candidates = (
            group_candidates_by_event(
                scored_neighbors,
                article_to_event,
            )
        )

        # -------------------------------------------------
        # STEP 4
        # Evaluate event-level evidence
        # -------------------------------------------------

        (
            selected_event,
            accepted_events,
            all_event_summaries,
        ) = choose_event(
            event_candidates,
            events,
        )

        if (
            len(
                accepted_events
            )
            > 1
        ):

            multiple_accepted_event_cases += 1

        # -------------------------------------------------
        # STEP 5A
        # No convincing existing event
        # -------------------------------------------------

        if selected_event is None:

            event = create_event(
                events,
                article,
            )

            article_to_event[
                article_id
            ] = event.event_id

            decision = (
                "new_event"
            )

            selected_probability = None

            strong_matches = 0

            support_matches = 0

            selected_event_previous_size = 0

        # -------------------------------------------------
        # STEP 5B
        # Assign to existing event
        # -------------------------------------------------

        else:

            event_id = selected_event[
                "event_id"
            ]

            event = events[
                event_id
            ]

            selected_event_previous_size = len(
                event.article_ids
            )

            if (
                selected_event_previous_size
                == 1
            ):

                singleton_bootstrap_matches += 1

            else:

                established_event_matches += 1

            add_article_to_event(
                event,
                article,
            )

            article_to_event[
                article_id
            ] = event_id

            decision = (
                "existing_event"
            )

            selected_probability = (
                selected_event[
                    "max_probability"
                ]
            )

            strong_matches = (
                selected_event[
                    "strong_matches"
                ]
            )

            support_matches = (
                selected_event[
                    "support_matches"
                ]
            )

        # -------------------------------------------------
        # SAVE ARTICLE ASSIGNMENT
        # -------------------------------------------------

        assignments.append(
            {
                "article_id":
                    article_id,

                "event_id":
                    event.event_id,

                "source":
                    article[
                        "source_name"
                    ],

                "title":
                    article[
                        "title"
                    ],

                "decision":
                    decision,

                "max_retrieved_pair_probability":
                    max_pair_probability,

                "selected_event_probability":
                    selected_probability,

                "strong_matches":
                    strong_matches,

                "support_matches":
                    support_matches,

                "selected_event_previous_size":
                    selected_event_previous_size,
            }
        )

        # -------------------------------------------------
        # SAVE DETAILED DECISION INFORMATION
        # -------------------------------------------------

        best_candidate_event_probability = None

        best_candidate_event_id = None

        if all_event_summaries:

            best_summary = max(
                all_event_summaries,
                key=lambda item:
                    item[
                        "max_probability"
                    ],
            )

            best_candidate_event_probability = (
                best_summary[
                    "max_probability"
                ]
            )

            best_candidate_event_id = (
                best_summary[
                    "event_id"
                ]
            )

        decisions.append(
            {
                "article_id":
                    article_id,

                "assigned_event_id":
                    event.event_id,

                "decision":
                    decision,

                "retrieved_neighbors":
                    len(
                        neighbors
                    ),

                "scored_pairs":
                    len(
                        scored_neighbors
                    ),

                "candidate_events":
                    len(
                        event_candidates
                    ),

                "accepted_candidate_events":
                    len(
                        accepted_events
                    ),

                "max_pair_probability":
                    max_pair_probability,

                "best_candidate_event_id":
                    best_candidate_event_id,

                "best_candidate_event_probability":
                    best_candidate_event_probability,

                "selected_event_probability":
                    selected_probability,

                "strong_matches":
                    strong_matches,

                "support_matches":
                    support_matches,

                "selected_event_previous_size":
                    selected_event_previous_size,
            }
        )

        # -------------------------------------------------
        # STEP 6
        # Article becomes available as a candidate for
        # future articles.
        # -------------------------------------------------

        processed_article_ids.append(
            article_id
        )

        # -------------------------------------------------
        # PROGRESS
        # -------------------------------------------------

        if (
            index % 100 == 0
            or index == total_articles
        ):

            print(
                f"Processed "
                f"{index}/{total_articles} "
                f"articles | "
                f"events={len(events)}"
            )

    # =====================================================
    # DIAGNOSTIC SUMMARY
    # =====================================================

    print()
    print("=" * 78)
    print("RETRIEVAL / MATCHING DIAGNOSTICS")
    print("=" * 78)

    print(
        f"Total retrieved neighbors: "
        f"{total_neighbors_retrieved}"
    )

    print(
        f"Total scored pairs: "
        f"{total_scored_pairs}"
    )

    print(
        f"Articles with >=1 retrieved neighbor: "
        f"{articles_with_neighbors}"
    )

    print(
        f"Articles with max probability >= 0.50: "
        f"{articles_with_pair_above_50}"
    )

    print(
        f"Articles with max probability >= 0.75: "
        f"{articles_with_pair_above_75}"
    )

    print(
        f"Articles with max probability >= 0.90: "
        f"{articles_with_pair_above_90}"
    )

    print(
        f"Singleton bootstrap assignments: "
        f"{singleton_bootstrap_matches}"
    )

    print(
        f"Established-event assignments: "
        f"{established_event_matches}"
    )

    print(
        f"Articles with multiple acceptable events: "
        f"{multiple_accepted_event_cases}"
    )

    return (
        events,
        assignments,
        decisions,
    )


# =========================================================
# SAVE RESULTS
# =========================================================

def save_results(
    events,
    assignments,
    decisions,
):

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # =====================================================
    # EVENT TABLE
    # =====================================================

    event_rows = []

    for event in events.values():

        event_rows.append(
            {
                "event_id":
                    event.event_id,

                "title":
                    event.title,

                "article_count":
                    len(
                        event.article_ids
                    ),

                "first_seen_at":
                    event.first_seen_at,

                "last_seen_at":
                    event.last_seen_at,

                "article_ids":
                    ",".join(
                        str(
                            article_id
                        )
                        for article_id
                        in event.article_ids
                    ),
            }
        )

    event_df = pd.DataFrame(
        event_rows
    )

    if not event_df.empty:

        event_df = (
            event_df
            .sort_values(
                [
                    "article_count",
                    "event_id",
                ],
                ascending=[
                    False,
                    True,
                ],
            )
            .reset_index(
                drop=True
            )
        )

    event_df.to_csv(
        EVENTS_OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    # =====================================================
    # ARTICLE ASSIGNMENTS
    # =====================================================

    assignment_df = pd.DataFrame(
        assignments
    )

    assignment_df.to_csv(
        ASSIGNMENTS_OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    # =====================================================
    # DECISION LOG
    # =====================================================

    decision_df = pd.DataFrame(
        decisions
    )

    decision_df.to_csv(
        DECISIONS_OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    return (
        event_df,
        assignment_df,
        decision_df,
    )


# =========================================================
# DISPLAY SUMMARY
# =========================================================

def show_summary(
    event_df,
    assignment_df,
):

    print()
    print("=" * 78)
    print("SIMULATION SUMMARY")
    print("=" * 78)

    total_articles = len(
        assignment_df
    )

    total_events = len(
        event_df
    )

    multi_article_events = int(
        (
            event_df[
                "article_count"
            ]
            > 1
        ).sum()
    )

    singleton_events = int(
        (
            event_df[
                "article_count"
            ]
            == 1
        ).sum()
    )

    articles_in_multi_events = int(
        event_df.loc[
            event_df[
                "article_count"
            ]
            > 1,
            "article_count",
        ].sum()
    )

    largest_event = int(
        event_df[
            "article_count"
        ].max()
    )

    mean_event_size = float(
        event_df[
            "article_count"
        ].mean()
    )

    median_event_size = float(
        event_df[
            "article_count"
        ].median()
    )

    print(
        f"Articles processed: "
        f"{total_articles}"
    )

    print(
        f"Events created: "
        f"{total_events}"
    )

    print(
        f"Multi-article events: "
        f"{multi_article_events}"
    )

    print(
        f"Singleton events: "
        f"{singleton_events}"
    )

    print(
        f"Articles in multi-article events: "
        f"{articles_in_multi_events}"
    )

    if total_articles:

        percentage = (
            articles_in_multi_events
            /
            total_articles
            *
            100
        )

        print(
            f"Articles grouped with others: "
            f"{percentage:.1f}%"
        )

    print(
        f"Largest event: "
        f"{largest_event} articles"
    )

    print(
        f"Mean event size: "
        f"{mean_event_size:.2f}"
    )

    print(
        f"Median event size: "
        f"{median_event_size:.1f}"
    )

    # =====================================================
    # EVENT SIZE DISTRIBUTION
    # =====================================================

    print()
    print("=" * 78)
    print("EVENT SIZE DISTRIBUTION")
    print("=" * 78)

    print(
        event_df[
            "article_count"
        ]
        .value_counts()
        .sort_index()
        .to_string()
    )

    # =====================================================
    # LARGEST EVENTS
    # =====================================================

    print()
    print("=" * 78)
    print("20 LARGEST EVENTS")
    print("=" * 78)

    columns = [
        "event_id",
        "article_count",
        "title",
    ]

    print(
        event_df[
            columns
        ]
        .head(20)
        .to_string(
            index=False
        )
    )

    # =====================================================
    # DECISIONS
    # =====================================================

    print()
    print("=" * 78)
    print("DECISION DISTRIBUTION")
    print("=" * 78)

    print(
        assignment_df[
            "decision"
        ]
        .value_counts()
        .to_string()
    )

    # =====================================================
    # MATCH PROBABILITY DISTRIBUTION
    # =====================================================

    matched = assignment_df[
        assignment_df[
            "decision"
        ]
        == "existing_event"
    ]

    if not matched.empty:

        print()
        print("=" * 78)
        print("EXISTING-EVENT MATCH PROBABILITIES")
        print("=" * 78)

        print(
            matched[
                "selected_event_probability"
            ]
            .describe(
                percentiles=[
                    0.10,
                    0.25,
                    0.50,
                    0.75,
                    0.90,
                ]
            )
            .round(4)
            .to_string()
        )


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 78)
    print("EVENT BUILDER V1 — DRY RUN")
    print("=" * 78)

    # -----------------------------------------------------
    # Load trained Event Matcher v1
    # -----------------------------------------------------

    model = load_model()

    session = SessionLocal()

    try:

        # -------------------------------------------------
        # Articles that already have Jina embeddings
        # -------------------------------------------------

        articles = load_articles(
            session
        )

        if not articles:

            print(
                "No embedded articles found."
            )

            return

        article_ids = [
            int(
                article[
                    "id"
                ]
            )
            for article
            in articles
        ]

        # -------------------------------------------------
        # Load NER features once
        # -------------------------------------------------

        entities = load_entities(
            session=session,
            article_ids=article_ids,
        )

        # -------------------------------------------------
        # Simulate chronological event construction
        # -------------------------------------------------

        (
            events,
            assignments,
            decisions,
        ) = simulate(
            session=session,
            model=model,
            articles=articles,
            entities=entities,
        )

    finally:

        session.close()

    # -----------------------------------------------------
    # Save dry-run results
    # -----------------------------------------------------

    (
        event_df,
        assignment_df,
        decision_df,
    ) = save_results(
        events=events,
        assignments=assignments,
        decisions=decisions,
    )

    # -----------------------------------------------------
    # Console summary
    # -----------------------------------------------------

    show_summary(
        event_df=event_df,
        assignment_df=assignment_df,
    )

    # -----------------------------------------------------
    # Files
    # -----------------------------------------------------

    print()
    print("=" * 78)
    print("OUTPUT FILES")
    print("=" * 78)

    print(
        EVENTS_OUTPUT
    )

    print(
        ASSIGNMENTS_OUTPUT
    )

    print(
        DECISIONS_OUTPUT
    )

    print()

    print(
        "DRY RUN ONLY: "
        "the PostgreSQL events and event_articles "
        "tables were not modified."
    )


if __name__ == "__main__":
    main()