from __future__ import annotations

import argparse
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
from sqlalchemy import func, select

from database.db import SessionLocal
from database.models import (
    Article,
    ArticleEmbedding,
    ArticleEntity,
    Event,
    EventArticle,
)


# =========================================================
# CONFIG
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MODEL_FILE = (
    PROJECT_ROOT
    / "events"
    / "models"
    / "event_matcher_v1.joblib"
)

EMBEDDING_MODEL = "jinaai/jina-embeddings-v5-text-small"
EMBEDDING_TASK = "text-matching"

NER_MODEL = "Davlan/xlm-roberta-base-ner-hrl"


# =========================================================
# HISTORICAL BACKFILL START
# =========================================================

# The corpus before August 2026 is extremely sparse.
#
# We therefore begin historical event reconstruction with
# the dense portion of the corpus.
#
# NOTE:
# PostgreSQL stores timezone-aware timestamps, so this is
# an aware datetime and can safely be compared against
# published_at / scraped_at.

EVENT_BACKFILL_START = datetime(
    2026,
    8,
    1,
    tzinfo=timezone.utc,
)


# =========================================================
# CANDIDATE RETRIEVAL
# =========================================================

CANDIDATE_WINDOW_HOURS = 48

TOP_K_NEIGHBORS = 20

MIN_RETRIEVAL_SIMILARITY = 0.75


# =========================================================
# EVENT MATCHING
# =========================================================

STRONG_PAIR_THRESHOLD = 0.75

SUPPORT_PAIR_THRESHOLD = 0.50

VERY_STRONG_PAIR_THRESHOLD = 0.90

MIN_STRONG_MATCHES = 2

MIN_SUPPORT_MATCHES = 2

MAX_EVENT_EVIDENCE = 5


# =========================================================
# FEATURE ORDER
# =========================================================

# IMPORTANT:
# This must remain identical to Event Matcher v1 training.

FEATURES = [
    "similarity",
    "shared_per",
    "shared_org",
    "shared_loc",
    "entity_jaccard",
]


# =========================================================
# MEDIA ENTITY FILTER
# =========================================================

MEDIA_ALIASES = {
    "5dias",
    "5 días",
    "abc",
    "abc color",
    "adn",
    "agencia ip",
    "ahora cde",
    "amambay ahora",
    "amambay digital",
    "amambay news",
    "caazapa ahora",
    "caazapá ahora",
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
    "ñanduti",
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
    "the asunción times",
    "tn press",
    "ultima hora",
    "última hora",
}


# =========================================================
# NORMALIZATION
# =========================================================

def normalize_text(value: str) -> str:

    value = unicodedata.normalize(
        "NFKC",
        value or "",
    )

    value = value.lower().strip()

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value


NORMALIZED_MEDIA_ALIASES = {
    normalize_text(alias)
    for alias in MEDIA_ALIASES
}


def is_media_entity(value: str) -> bool:

    return (
        normalize_text(value)
        in NORMALIZED_MEDIA_ALIASES
    )


# =========================================================
# LOAD MODEL
# =========================================================

def load_matcher():

    if not MODEL_FILE.exists():

        raise FileNotFoundError(
            f"Event matcher not found: {MODEL_FILE}"
        )

    print(
        f"Loading Event Matcher: {MODEL_FILE}"
    )

    model = joblib.load(
        MODEL_FILE
    )

    print(
        "Event Matcher loaded."
    )

    return model


# =========================================================
# EMBEDDING UTILITIES
# =========================================================

def embedding_to_numpy(value) -> np.ndarray:

    if isinstance(value, str):

        vector = np.fromstring(
            value.strip("[]"),
            sep=",",
            dtype=np.float32,
        )

    else:

        vector = np.asarray(
            value,
            dtype=np.float32,
        )

    norm = np.linalg.norm(
        vector
    )

    if norm > 0:

        vector = (
            vector
            / norm
        )

    return vector


def cosine_similarity(
    vector_a: np.ndarray,
    vector_b: np.ndarray,
) -> float:

    return float(
        np.dot(
            vector_a,
            vector_b,
        )
    )


# =========================================================
# ENTITY UTILITIES
# =========================================================

def load_entities(
    session,
    article_ids: list[int],
):

    if not article_ids:

        return {}

    stmt = (
        select(
            ArticleEntity.article_id,
            ArticleEntity.entity_type,
            ArticleEntity.normalized_text,
        )
        .where(
            ArticleEntity.article_id.in_(
                article_ids
            ),
            ArticleEntity.model
            == NER_MODEL,
            ArticleEntity.entity_type.in_(
                [
                    "PER",
                    "ORG",
                    "LOC",
                ]
            ),
        )
    )

    rows = session.execute(
        stmt
    ).all()

    result = defaultdict(
        lambda: {
            "PER": set(),
            "ORG": set(),
            "LOC": set(),
        }
    )

    for (
        article_id,
        entity_type,
        normalized_text,
    ) in rows:

        if is_media_entity(
            normalized_text
        ):
            continue

        result[
            int(article_id)
        ][
            entity_type
        ].add(
            normalized_text
        )

    return result


def empty_entities():

    return {
        "PER": set(),
        "ORG": set(),
        "LOC": set(),
    }


def calculate_entity_features(
    target_entities,
    candidate_entities,
):

    shared_per = len(
        target_entities["PER"]
        & candidate_entities["PER"]
    )

    shared_org = len(
        target_entities["ORG"]
        & candidate_entities["ORG"]
    )

    shared_loc = len(
        target_entities["LOC"]
        & candidate_entities["LOC"]
    )

    target_all = (
        target_entities["PER"]
        | target_entities["ORG"]
        | target_entities["LOC"]
    )

    candidate_all = (
        candidate_entities["PER"]
        | candidate_entities["ORG"]
        | candidate_entities["LOC"]
    )

    union = (
        target_all
        | candidate_all
    )

    intersection = (
        target_all
        & candidate_all
    )

    if union:

        entity_jaccard = (
            len(intersection)
            / len(union)
        )

    else:

        entity_jaccard = 0.0

    return {
        "shared_per": shared_per,
        "shared_org": shared_org,
        "shared_loc": shared_loc,
        "entity_jaccard": entity_jaccard,
    }


# =========================================================
# ARTICLE SELECTION
# =========================================================

def get_unassigned_articles(
    session,
    limit: int | None = None,
):

    embedded = (
        select(
            ArticleEmbedding.article_id
        )
        .where(
            ArticleEmbedding.model
            == EMBEDDING_MODEL,

            ArticleEmbedding.task
            == EMBEDDING_TASK,
        )
    )

    assigned = (
        select(
            EventArticle.article_id
        )
    )

    effective_time = func.coalesce(
        Article.published_at,
        Article.scraped_at,
    )

    stmt = (
        select(
            Article
        )
        .where(
            Article.id.in_(
                embedded
            ),

            ~Article.id.in_(
                assigned
            ),

            # =============================================
            # NEW:
            # Ignore sparse historical articles before
            # August 1, 2026.
            # =============================================

            effective_time
            >= EVENT_BACKFILL_START,
        )
        .order_by(
            effective_time.asc(),
            Article.id.asc(),
        )
    )

    if limit is not None:

        stmt = stmt.limit(
            limit
        )

    return list(
        session.scalars(
            stmt
        ).all()
    )


def get_effective_time(
    article: Article,
):

    return (
        article.published_at
        or article.scraped_at
    )


# =========================================================
# TARGET EMBEDDING
# =========================================================

def get_embedding(
    session,
    article_id: int,
):

    stmt = (
        select(
            ArticleEmbedding.embedding
        )
        .where(
            ArticleEmbedding.article_id
            == article_id,

            ArticleEmbedding.model
            == EMBEDDING_MODEL,

            ArticleEmbedding.task
            == EMBEDDING_TASK,
        )
    )

    value = session.scalar(
        stmt
    )

    if value is None:

        return None

    return embedding_to_numpy(
        value
    )


# =========================================================
# CANDIDATE RETRIEVAL
# =========================================================

def get_candidate_articles(
    session,
    target_article: Article,
    target_embedding: np.ndarray,
):

    target_time = get_effective_time(
        target_article
    )

    if target_time is None:

        return []

    start_time = (
        target_time
        - timedelta(
            hours=CANDIDATE_WINDOW_HOURS
        )
    )

    effective_time = func.coalesce(
        Article.published_at,
        Article.scraped_at,
    )

    stmt = (
        select(
            Article.id,
            ArticleEmbedding.embedding,
        )
        .join(
            ArticleEmbedding,
            ArticleEmbedding.article_id
            == Article.id,
        )
        .join(
            EventArticle,
            EventArticle.article_id
            == Article.id,
        )
        .where(
            ArticleEmbedding.model
            == EMBEDDING_MODEL,

            ArticleEmbedding.task
            == EMBEDDING_TASK,

            effective_time
            >= start_time,

            effective_time
            <= target_time,

            Article.id
            != target_article.id,
        )
    )

    rows = session.execute(
        stmt
    ).all()

    scored = []

    for (
        article_id,
        embedding,
    ) in rows:

        candidate_vector = (
            embedding_to_numpy(
                embedding
            )
        )

        similarity = cosine_similarity(
            target_embedding,
            candidate_vector,
        )

        if (
            similarity
            < MIN_RETRIEVAL_SIMILARITY
        ):

            continue

        scored.append(
            (
                int(article_id),
                similarity,
            )
        )

    scored.sort(
        key=lambda item:
            item[1],
        reverse=True,
    )

    return scored[
        :TOP_K_NEIGHBORS
    ]


# =========================================================
# EVENT LOOKUP
# =========================================================

def get_event_ids_for_articles(
    session,
    article_ids: list[int],
):

    if not article_ids:

        return {}

    stmt = (
        select(
            EventArticle.article_id,
            EventArticle.event_id,
        )
        .where(
            EventArticle.article_id.in_(
                article_ids
            )
        )
    )

    rows = session.execute(
        stmt
    ).all()

    return {
        int(article_id):
            int(event_id)

        for (
            article_id,
            event_id,
        ) in rows
    }


def get_event_sizes(
    session,
    event_ids: list[int],
):

    if not event_ids:

        return {}

    stmt = (
        select(
            Event.id,
            Event.article_count,
        )
        .where(
            Event.id.in_(
                event_ids
            )
        )
    )

    rows = session.execute(
        stmt
    ).all()

    return {
        int(event_id):
            int(article_count)

        for (
            event_id,
            article_count,
        ) in rows
    }


# =========================================================
# EVENT MATCHER
# =========================================================

def score_pair(
    matcher,
    similarity: float,
    target_entities,
    candidate_entities,
):

    entity_features = (
        calculate_entity_features(
            target_entities,
            candidate_entities,
        )
    )

    feature_values = np.asarray(
        [[
            similarity,
            entity_features[
                "shared_per"
            ],
            entity_features[
                "shared_org"
            ],
            entity_features[
                "shared_loc"
            ],
            entity_features[
                "entity_jaccard"
            ],
        ]],
        dtype=float,
    )

    probability = float(
        matcher.predict_proba(
            feature_values
        )[0, 1]
    )

    return {
        "probability":
            probability,

        "similarity":
            similarity,

        **entity_features,
    }


# =========================================================
# GROUP CANDIDATES BY EVENT
# =========================================================

def build_event_evidence(
    scored_pairs,
    article_to_event,
):

    grouped = defaultdict(
        list
    )

    for pair in scored_pairs:

        candidate_id = pair[
            "candidate_article_id"
        ]

        event_id = (
            article_to_event.get(
                candidate_id
            )
        )

        if event_id is None:

            continue

        grouped[
            event_id
        ].append(
            pair
        )

    return grouped


# =========================================================
# SUMMARIZE EVENT EVIDENCE
# =========================================================

def summarize_event_evidence(
    pairs,
):

    ordered = sorted(
        pairs,
        key=lambda row:
            row["probability"],
        reverse=True,
    )

    evidence = ordered[
        :MAX_EVENT_EVIDENCE
    ]

    probabilities = [
        row["probability"]
        for row in evidence
    ]

    similarities = [
        row["similarity"]
        for row in evidence
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

    max_probability = max(
        probabilities
    )

    mean_probability = float(
        np.mean(
            probabilities
        )
    )

    if len(
        probabilities
    ) >= 2:

        top_two_mean = float(
            np.mean(
                probabilities[:2]
            )
        )

    else:

        top_two_mean = (
            probabilities[0]
        )

    best_pair = evidence[0]

    return {
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

        "best_similarity":
            max(
                similarities
            ),

        "best_pair":
            best_pair,
    }


# =========================================================
# EVENT ACCEPTANCE
# =========================================================

def event_is_acceptable(
    evidence,
    event_size: int,
):

    # Singleton bootstrap
    if event_size == 1:

        return (
            evidence[
                "max_probability"
            ]
            >= VERY_STRONG_PAIR_THRESHOLD
        )

    # Established event:
    # at least two strong matches
    if (
        evidence[
            "strong_matches"
        ]
        >= MIN_STRONG_MATCHES
    ):

        return True

    # One very strong pair + supporting evidence
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
# CHOOSE EVENT
# =========================================================

def choose_event(
    grouped_evidence,
    event_sizes,
):

    accepted = []

    for (
        event_id,
        pairs,
    ) in grouped_evidence.items():

        evidence = (
            summarize_event_evidence(
                pairs
            )
        )

        event_size = (
            event_sizes.get(
                event_id,
                1,
            )
        )

        if not event_is_acceptable(
            evidence,
            event_size,
        ):

            continue

        accepted.append(
            (
                event_id,
                evidence,
            )
        )

    if not accepted:

        return (
            None,
            None,
        )

    accepted.sort(
        key=lambda item: (
            item[1][
                "strong_matches"
            ],
            item[1][
                "top_two_mean"
            ],
            item[1][
                "max_probability"
            ],
            item[1][
                "mean_probability"
            ],
        ),
        reverse=True,
    )

    return accepted[0]


# =========================================================
# DATABASE WRITES
# =========================================================

def create_new_event(
    session,
    article: Article,
):

    article_time = (
        get_effective_time(
            article
        )
    )

    now = datetime.now(
        timezone.utc
    )

    event = Event(
        title=article.title,
        first_seen_at=article_time,
        last_seen_at=article_time,
        article_count=1,
        created_at=now,
        updated_at=now,
    )

    session.add(
        event
    )

    # Generate event.id immediately.
    session.flush()

    assignment = EventArticle(
        event_id=event.id,
        article_id=article.id,
        match_probability=None,
        similarity=None,
        is_seed=True,
        created_at=now,
    )

    session.add(
        assignment
    )

    return event


def assign_to_existing_event(
    session,
    article: Article,
    event_id: int,
    evidence,
):

    event = session.get(
        Event,
        event_id,
    )

    if event is None:

        raise RuntimeError(
            f"Event {event_id} does not exist."
        )

    article_time = (
        get_effective_time(
            article
        )
    )

    now = datetime.now(
        timezone.utc
    )

    assignment = EventArticle(
        event_id=event.id,
        article_id=article.id,

        match_probability=evidence[
            "max_probability"
        ],

        similarity=evidence[
            "best_similarity"
        ],

        is_seed=False,
        created_at=now,
    )

    session.add(
        assignment
    )

    event.article_count += 1

    if (
        event.first_seen_at is None
        or article_time
        < event.first_seen_at
    ):

        event.first_seen_at = (
            article_time
        )

    if (
        event.last_seen_at is None
        or article_time
        > event.last_seen_at
    ):

        event.last_seen_at = (
            article_time
        )

    event.updated_at = now

    return event


# =========================================================
# PROCESS ARTICLE
# =========================================================

def process_article(
    session,
    matcher,
    article,
    dry_run: bool,
):

    target_embedding = (
        get_embedding(
            session,
            article.id,
        )
    )

    if target_embedding is None:

        return {
            "decision":
                "skip_no_embedding",
        }

    # -----------------------------------------------------
    # Candidate retrieval
    # -----------------------------------------------------

    candidates = (
        get_candidate_articles(
            session,
            article,
            target_embedding,
        )
    )

    # -----------------------------------------------------
    # No candidates -> new event
    # -----------------------------------------------------

    if not candidates:

        if not dry_run:

            event = (
                create_new_event(
                    session,
                    article,
                )
            )

            return {
                "decision":
                    "new_event",

                "event_id":
                    event.id,

                "candidate_count":
                    0,
            }

        return {
            "decision":
                "new_event",

            "event_id":
                None,

            "candidate_count":
                0,
        }

    candidate_ids = [
        article_id

        for (
            article_id,
            _
        ) in candidates
    ]

    # -----------------------------------------------------
    # NER
    # -----------------------------------------------------

    entities = load_entities(
        session,
        [
            article.id,
            *candidate_ids,
        ],
    )

    target_entities = (
        entities.get(
            article.id,
            empty_entities(),
        )
    )

    # -----------------------------------------------------
    # Score candidate pairs
    # -----------------------------------------------------

    scored_pairs = []

    for (
        candidate_id,
        similarity,
    ) in candidates:

        candidate_entities = (
            entities.get(
                candidate_id,
                empty_entities(),
            )
        )

        pair = score_pair(
            matcher,
            similarity,
            target_entities,
            candidate_entities,
        )

        pair[
            "candidate_article_id"
        ] = candidate_id

        scored_pairs.append(
            pair
        )

    # -----------------------------------------------------
    # Candidate articles -> events
    # -----------------------------------------------------

    article_to_event = (
        get_event_ids_for_articles(
            session,
            candidate_ids,
        )
    )

    grouped_evidence = (
        build_event_evidence(
            scored_pairs,
            article_to_event,
        )
    )

    # -----------------------------------------------------
    # No event evidence
    # -----------------------------------------------------

    if not grouped_evidence:

        if not dry_run:

            event = (
                create_new_event(
                    session,
                    article,
                )
            )

            return {
                "decision":
                    "new_event",

                "event_id":
                    event.id,

                "candidate_count":
                    len(
                        candidates
                    ),
            }

        return {
            "decision":
                "new_event",

            "event_id":
                None,

            "candidate_count":
                len(
                    candidates
                ),
        }

    # -----------------------------------------------------
    # Event sizes
    # -----------------------------------------------------

    event_ids = list(
        grouped_evidence.keys()
    )

    event_sizes = (
        get_event_sizes(
            session,
            event_ids,
        )
    )

    # -----------------------------------------------------
    # Choose event
    # -----------------------------------------------------

    (
        selected_event_id,
        evidence,
    ) = choose_event(
        grouped_evidence,
        event_sizes,
    )

    # -----------------------------------------------------
    # No acceptable existing event
    # -----------------------------------------------------

    if selected_event_id is None:

        if not dry_run:

            event = (
                create_new_event(
                    session,
                    article,
                )
            )

            return {
                "decision":
                    "new_event",

                "event_id":
                    event.id,

                "candidate_count":
                    len(
                        candidates
                    ),
            }

        return {
            "decision":
                "new_event",

            "event_id":
                None,

            "candidate_count":
                len(
                    candidates
                ),
        }

    # -----------------------------------------------------
    # Existing event
    # -----------------------------------------------------

    if not dry_run:

        assign_to_existing_event(
            session,
            article,
            selected_event_id,
            evidence,
        )

    return {
        "decision":
            "existing_event",

        "event_id":
            selected_event_id,

        "candidate_count":
            len(
                candidates
            ),

        "max_probability":
            evidence[
                "max_probability"
            ],

        "strong_matches":
            evidence[
                "strong_matches"
            ],

        "support_matches":
            evidence[
                "support_matches"
            ],
    }


# =========================================================
# DATABASE STATUS
# =========================================================

def database_has_events(
    session,
):

    event_count = session.scalar(
        select(
            func.count(
                Event.id
            )
        )
    )

    assignment_count = (
        session.scalar(
            select(
                func.count()
            )
            .select_from(
                EventArticle
            )
        )
    )

    return (
        int(
            event_count
            or 0
        ),

        int(
            assignment_count
            or 0
        ),
    )


# =========================================================
# MAIN
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Incrementally assign embedded news "
            "articles to events."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum number of currently "
            "unassigned articles to process."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Evaluate articles without writing "
            "events or assignments."
        ),
    )

    parser.add_argument(
        "--commit-every",
        type=int,
        default=50,
        help=(
            "Commit every N processed articles "
            "(default: 50)."
        ),
    )

    args = parser.parse_args()

    print(
        "=" * 70
    )

    print(
        "PRODUCTION EVENT ASSIGNMENT"
    )

    print(
        "=" * 70
    )

    print(
        "Historical backfill starts: "
        f"{EVENT_BACKFILL_START}"
    )

    print(
        "Candidate window: "
        f"{CANDIDATE_WINDOW_HOURS} hours"
    )

    print(
        "Top K neighbors: "
        f"{TOP_K_NEIGHBORS}"
    )

    print(
        "Minimum retrieval similarity: "
        f"{MIN_RETRIEVAL_SIMILARITY}"
    )

    print(
        f"Dry run: {args.dry_run}"
    )

    matcher = (
        load_matcher()
    )

    session = (
        SessionLocal()
    )

    try:

        (
            event_count,
            assignment_count,
        ) = database_has_events(
            session
        )

        print()

        print(
            "Existing events: "
            f"{event_count}"
        )

        print(
            "Existing event assignments: "
            f"{assignment_count}"
        )

        articles = (
            get_unassigned_articles(
                session,
                args.limit,
            )
        )

        print(
            "Articles to process: "
            f"{len(articles)}"
        )

        if articles:

            print(
                "First article: "
                f"{get_effective_time(articles[0])}"
            )

            print(
                "Last article: "
                f"{get_effective_time(articles[-1])}"
            )

        if not articles:

            print(
                "No articles need event assignment."
            )

            return

        # -------------------------------------------------
        # Dry-run limitation
        # -------------------------------------------------

        if (
            args.dry_run
            and event_count == 0
        ):

            print()

            print(
                "WARNING: dry-run on an empty event "
                "database cannot reconstruct evolving "
                "events because assignments are not "
                "persisted."
            )

            print(
                "Use build_events.py for full "
                "in-memory simulation."
            )

            return

        new_events = 0

        existing_assignments = 0

        skipped = 0

        articles_with_candidates = 0

        total_candidates = 0

        # -------------------------------------------------
        # Process chronologically
        # -------------------------------------------------

        for (
            index,
            article,
        ) in enumerate(
            articles,
            start=1,
        ):

            result = process_article(
                session,
                matcher,
                article,
                dry_run=args.dry_run,
            )

            decision = result[
                "decision"
            ]

            candidate_count = (
                result.get(
                    "candidate_count",
                    0,
                )
            )

            total_candidates += (
                candidate_count
            )

            if candidate_count > 0:

                articles_with_candidates += 1

            if (
                decision
                == "new_event"
            ):

                new_events += 1

            elif (
                decision
                == "existing_event"
            ):

                existing_assignments += 1

            else:

                skipped += 1

            # ---------------------------------------------
            # Commit checkpoint
            # ---------------------------------------------

            if (
                not args.dry_run
                and
                index
                % args.commit_every
                == 0
            ):

                session.commit()

                print(
                    f"[{index}/"
                    f"{len(articles)}] "
                    f"new={new_events} "
                    f"existing="
                    f"{existing_assignments} "
                    f"candidates="
                    f"{articles_with_candidates} "
                    f"skipped={skipped}"
                )

            elif (
                args.dry_run
                and
                index % 50 == 0
            ):

                print(
                    f"[{index}/"
                    f"{len(articles)}] "
                    f"new={new_events} "
                    f"existing="
                    f"{existing_assignments} "
                    f"candidates="
                    f"{articles_with_candidates} "
                    f"skipped={skipped}"
                )

        # -------------------------------------------------
        # Final commit
        # -------------------------------------------------

        if not args.dry_run:

            session.commit()

        else:

            session.rollback()

        # -------------------------------------------------
        # Summary
        # -------------------------------------------------

        print()

        print(
            "=" * 70
        )

        print(
            "EVENT ASSIGNMENT COMPLETE"
        )

        print(
            "=" * 70
        )

        print(
            f"Processed: "
            f"{len(articles)}"
        )

        print(
            f"New events: "
            f"{new_events}"
        )

        print(
            "Assigned to existing events: "
            f"{existing_assignments}"
        )

        print(
            "Articles with >=1 candidate: "
            f"{articles_with_candidates}"
        )

        print(
            "Total candidates retrieved: "
            f"{total_candidates}"
        )

        print(
            f"Skipped: "
            f"{skipped}"
        )

    except KeyboardInterrupt:

        session.rollback()

        print()

        print(
            "=" * 70
        )

        print(
            "INTERRUPTED"
        )

        print(
            "=" * 70
        )

        print(
            "Current uncommitted group "
            "was rolled back."
        )

        print(
            "Previously committed assignments "
            "remain in the database."
        )

        print(
            "Run the command again to resume."
        )

    except Exception:

        session.rollback()

        raise

    finally:

        session.close()


if __name__ == "__main__":

    main()