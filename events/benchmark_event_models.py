from __future__ import annotations

import argparse
import csv
import json
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

from sqlalchemy import select

from database.db import SessionLocal
from database.models import Event

from events.build_event_context import (
    load_event_articles,
    select_context_articles,
    build_context,
)


# =========================================================
# CONFIGURATION
# =========================================================

OLLAMA_URL = "http://localhost:11434/api/chat"

MODELS = [
    "qwen3:8b",
    "gpt-oss:20b",
]

MAX_CONTEXT_ARTICLES = 6
MAX_BODY_CHARS = 6000

TEMPERATURE = 0.2
NUM_PREDICT = 500

RANDOM_SEED = 42

OUTPUT_DIR = Path("events/benchmark_results")

SELECTION_FILE = OUTPUT_DIR / "benchmark_events.json"

RESULTS_FILE = OUTPUT_DIR / "benchmark_generations.csv"

BLIND_REVIEW_FILE = OUTPUT_DIR / "benchmark_blind_review.csv"

ANSWER_KEY_FILE = OUTPUT_DIR / "benchmark_answer_key.csv"


# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
IDIOMA OBLIGATORIO: ESPAÑOL.

Eres un editor de noticias paraguayo encargado de sintetizar varios
artículos periodísticos que pertenecen al mismo evento.

Tu tarea es producir una representación neutral, factual y conservadora
del evento.

REGLAS FUNDAMENTALES:

1. TODO el contenido generado debe estar escrito en español.

2. Utiliza únicamente información contenida en los artículos proporcionados.
   No utilices conocimiento externo.

3. No inventes hechos, nombres, fechas, cifras, causas, motivaciones
   ni declaraciones.

4. Distingue cuidadosamente entre:
   - hechos reportados de forma consistente;
   - afirmaciones atribuidas a una persona o institución;
   - hipótesis;
   - versiones contradictorias;
   - información todavía no confirmada.

5. NO conviertas una hipótesis, versión o explicación disputada en un hecho.

6. Para el TÍTULO utiliza solamente hechos que estén claramente respaldados
   por los artículos seleccionados.

7. Si existe desacuerdo sobre la causa, mecanismo o circunstancias de un
   hecho, omite esa explicación del título.

8. Prefiere un título más general pero correcto antes que un título más
   específico basado en información incierta.

9. El título debe representar el acontecimiento principal compartido por
   los artículos, no el enfoque particular de un solo medio.

10. El artículo marcado como REPRESENTATIVO es una referencia importante,
    pero no es una fuente de verdad privilegiada. Sus afirmaciones también
    deben contrastarse con los demás artículos.

11. Si distintas fuentes presentan versiones contradictorias, el resumen
    puede explicar el desacuerdo de manera explícita y neutral.

12. Cuando una afirmación importante provenga solamente de una fuente,
    atribúyela si decides incluirla. No la presentes como consenso.

13. Evita lenguaje sensacionalista, partidista, promocional o valorativo.

14. No menciones los nombres de los medios salvo que el medio sea parte
    relevante del acontecimiento o sea necesario atribuir una afirmación.

15. No escribas frases como "según los artículos proporcionados".

16. No agregues antecedentes que no estén presentes en los textos.

17. El resumen debe explicar qué ocurrió y priorizar la información central
    respaldada por múltiples artículos.

18. El título debe ser breve, descriptivo y factual.

19. El resumen debe tener entre 2 y 4 oraciones.

20. Ante la duda, OMITE una afirmación antes que presentarla como cierta.

21. Responde exclusivamente en español.
""".strip()


# =========================================================
# BUILD PROMPT
# =========================================================

def build_llm_prompt(context: dict) -> str:

    sections = []

    sections.append(
        f"EVENTO {context['event_id']}\n"
        f"Cantidad total de artículos en el evento: "
        f"{context['article_count']}\n"
        f"Cantidad total de medios: "
        f"{context['source_count']}"
    )

    for index, article in enumerate(
        context["articles"],
        start=1,
    ):

        role = (
            "ARTÍCULO REPRESENTATIVO"
            if article["is_representative"]
            else "ARTÍCULO DE APOYO"
        )

        body = (
            article["body"][:MAX_BODY_CHARS]
            .strip()
        )

        sections.append(
            f"""
--------------------------------------------------
ARTÍCULO {index} — {role}
--------------------------------------------------

Medio: {article["source"]}
Fecha: {article["published_at"]}
Título: {article["title"]}

Texto:
{body}
""".strip()
        )

    sections.append(
        """
Genera ahora la representación neutral del evento.

Antes de escribir el título, identifica cuál es el hecho central que puede
afirmarse sin depender de hipótesis o versiones disputadas.

El título debe describir ese hecho central.

IDIOMA OBLIGATORIO: ESPAÑOL.

Devuelve únicamente:

{
  "title": "Título en español",
  "summary": "Resumen en español"
}
""".strip()
    )

    return "\n\n".join(sections)


# =========================================================
# OLLAMA
# =========================================================

def call_ollama(
    model: str,
    user_prompt: str,
) -> dict:

    payload = {
        "model": model,

        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],

        "stream": False,

        "think": False,

        "format": "json",

        "options": {
            "temperature": TEMPERATURE,
            "num_predict": NUM_PREDICT,
        },
    }

    data = json.dumps(
        payload
    ).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    start = time.perf_counter()

    try:

        with urllib.request.urlopen(
            request,
            timeout=600,
        ) as response:

            result = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except urllib.error.URLError as exc:

        raise RuntimeError(
            f"Could not connect to Ollama "
            f"at {OLLAMA_URL}: {exc}"
        ) from exc

    elapsed = (
        time.perf_counter()
        - start
    )

    content = (
        result
        .get("message", {})
        .get("content", "")
        .strip()
    )

    if not content:
        raise RuntimeError(
            f"{model} returned an empty response."
        )

    try:

        parsed = json.loads(
            content
        )

    except json.JSONDecodeError as exc:

        raise RuntimeError(
            f"{model} returned invalid JSON:\n"
            f"{content}"
        ) from exc

    title = str(
        parsed.get(
            "title",
            "",
        )
    ).strip()

    summary = str(
        parsed.get(
            "summary",
            "",
        )
    ).strip()

    if not title:
        raise RuntimeError(
            f"{model} returned an empty title."
        )

    if not summary:
        raise RuntimeError(
            f"{model} returned an empty summary."
        )

    return {
        "title": title,
        "summary": summary,

        "elapsed_seconds": round(
            elapsed,
            2,
        ),

        "prompt_tokens": result.get(
            "prompt_eval_count"
        ),

        "generated_tokens": result.get(
            "eval_count"
        ),

        "total_duration_ns": result.get(
            "total_duration"
        ),

        "load_duration_ns": result.get(
            "load_duration"
        ),

        "prompt_eval_duration_ns":
            result.get(
                "prompt_eval_duration"
            ),

        "eval_duration_ns":
            result.get(
                "eval_duration"
            ),
    }


# =========================================================
# BENCHMARK EVENT SELECTION
# =========================================================

def get_candidate_event_ids(
    session,
    minimum: int,
    maximum: int | None,
):

    stmt = (
        select(
            Event.id,
            Event.article_count,
        )
        .where(
            Event.representative_article_id.is_not(
                None
            ),
            Event.article_count >= minimum,
        )
    )

    if maximum is not None:

        stmt = stmt.where(
            Event.article_count <= maximum
        )

    return [
        {
            "event_id": int(row.id),
            "article_count": int(
                row.article_count
            ),
        }
        for row in session.execute(
            stmt
        ).all()
    ]


def sample_group(
    candidates,
    n: int,
    rng,
):

    if len(candidates) < n:
        raise RuntimeError(
            f"Need {n} events but only "
            f"{len(candidates)} are available."
        )

    return rng.sample(
        candidates,
        n,
    )


def create_benchmark_selection(
    session,
):

    rng = random.Random(
        RANDOM_SEED
    )

    small = get_candidate_event_ids(
        session,
        minimum=2,
        maximum=3,
    )

    medium = get_candidate_event_ids(
        session,
        minimum=4,
        maximum=10,
    )

    large = get_candidate_event_ids(
        session,
        minimum=11,
        maximum=None,
    )

    selection = []

    for item in sample_group(
        small,
        10,
        rng,
    ):
        item["size_group"] = "small"
        selection.append(item)

    for item in sample_group(
        medium,
        10,
        rng,
    ):
        item["size_group"] = "medium"
        selection.append(item)

    for item in sample_group(
        large,
        10,
        rng,
    ):
        item["size_group"] = "large"
        selection.append(item)

    # Randomize processing order so we don't run all
    # large events together.
    rng.shuffle(
        selection
    )

    return selection


def load_or_create_selection(
    session,
):

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if SELECTION_FILE.exists():

        with SELECTION_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:

            return json.load(
                file
            )

    selection = (
        create_benchmark_selection(
            session
        )
    )

    with SELECTION_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            selection,
            file,
            ensure_ascii=False,
            indent=2,
        )

    return selection


# =========================================================
# EXISTING RESULTS / RESUME
# =========================================================

RESULT_FIELDS = [
    "event_id",
    "size_group",
    "article_count",
    "source_count",
    "context_article_count",
    "context_source_count",
    "model",
    "title",
    "summary",
    "prompt_tokens",
    "generated_tokens",
    "elapsed_seconds",
    "total_duration_ns",
    "load_duration_ns",
    "prompt_eval_duration_ns",
    "eval_duration_ns",
]


def load_completed_generations():

    completed = set()

    if not RESULTS_FILE.exists():
        return completed

    with RESULTS_FILE.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:

        reader = csv.DictReader(
            file
        )

        for row in reader:

            completed.add(
                (
                    int(row["event_id"]),
                    row["model"],
                )
            )

    return completed


def append_result(
    row,
):

    file_exists = (
        RESULTS_FILE.exists()
    )

    with RESULTS_FILE.open(
        "a",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=RESULT_FIELDS,
        )

        if not file_exists:

            writer.writeheader()

        writer.writerow(
            row
        )


# =========================================================
# LOAD ALL RESULTS
# =========================================================

def load_results():

    if not RESULTS_FILE.exists():
        return []

    with RESULTS_FILE.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:

        return list(
            csv.DictReader(
                file
            )
        )


# =========================================================
# BLIND REVIEW FILE
# =========================================================

def create_blind_review_files():

    results = load_results()

    grouped = {}

    for row in results:

        event_id = int(
            row["event_id"]
        )

        grouped.setdefault(
            event_id,
            {},
        )

        grouped[event_id][
            row["model"]
        ] = row

    rng = random.Random(
        RANDOM_SEED + 1000
    )

    review_rows = []
    key_rows = []

    for event_id in sorted(
        grouped
    ):

        generations = grouped[
            event_id
        ]

        if not all(
            model in generations
            for model in MODELS
        ):
            continue

        model_a, model_b = MODELS

        if rng.random() < 0.5:
            model_a, model_b = (
                model_b,
                model_a,
            )

        a = generations[
            model_a
        ]

        b = generations[
            model_b
        ]

        review_rows.append(
            {
                "event_id":
                    event_id,

                "size_group":
                    a["size_group"],

                "article_count":
                    a["article_count"],

                "title_A":
                    a["title"],

                "summary_A":
                    a["summary"],

                "title_B":
                    b["title"],

                "summary_B":
                    b["summary"],

                # -------------------------------------
                # Fill these manually.
                # Suggested scale: 1–5.
                # -------------------------------------

                "A_factual_accuracy":
                    "",

                "A_representativeness":
                    "",

                "A_neutrality":
                    "",

                "A_language_quality":
                    "",

                "A_unsupported_claims":
                    "",

                "B_factual_accuracy":
                    "",

                "B_representativeness":
                    "",

                "B_neutrality":
                    "",

                "B_language_quality":
                    "",

                "B_unsupported_claims":
                    "",

                "preferred":
                    "",

                "notes":
                    "",
            }
        )

        key_rows.append(
            {
                "event_id":
                    event_id,

                "model_A":
                    model_a,

                "model_B":
                    model_b,
            }
        )

    review_fields = [
        "event_id",
        "size_group",
        "article_count",

        "title_A",
        "summary_A",

        "title_B",
        "summary_B",

        "A_factual_accuracy",
        "A_representativeness",
        "A_neutrality",
        "A_language_quality",
        "A_unsupported_claims",

        "B_factual_accuracy",
        "B_representativeness",
        "B_neutrality",
        "B_language_quality",
        "B_unsupported_claims",

        "preferred",
        "notes",
    ]

    with BLIND_REVIEW_FILE.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=review_fields,
        )

        writer.writeheader()

        writer.writerows(
            review_rows
        )

    with ANSWER_KEY_FILE.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=[
                "event_id",
                "model_A",
                "model_B",
            ],
        )

        writer.writeheader()

        writer.writerows(
            key_rows
        )


# =========================================================
# MAIN
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Benchmark Qwen3 8B and GPT-OSS 20B "
            "on 30 real news events."
        )
    )

    parser.add_argument(
        "--max-articles",
        type=int,
        default=MAX_CONTEXT_ARTICLES,
    )

    args = parser.parse_args()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    session = SessionLocal()

    try:

        selection = (
            load_or_create_selection(
                session
            )
        )

        print("=" * 80)
        print("EVENT MODEL BENCHMARK")
        print("=" * 80)

        print(
            f"Events: {len(selection)}"
        )

        print(
            f"Models: {', '.join(MODELS)}"
        )

        print(
            f"Expected generations: "
            f"{len(selection) * len(MODELS)}"
        )

        print(
            f"Max context articles: "
            f"{args.max_articles}"
        )

        completed = (
            load_completed_generations()
        )

        print(
            f"Already completed: "
            f"{len(completed)}"
        )

        generation_number = len(
            completed
        )

        total_generations = (
            len(selection)
            * len(MODELS)
        )

        for event_info in selection:

            event_id = (
                event_info[
                    "event_id"
                ]
            )

            event = session.get(
                Event,
                event_id,
            )

            if event is None:

                print(
                    f"Event {event_id} "
                    f"does not exist. Skipping."
                )

                continue

            articles = (
                load_event_articles(
                    session,
                    event.id,
                )
            )

            if not articles:

                print(
                    f"Event {event.id}: "
                    f"no articles."
                )

                continue

            selected_articles = (
                select_context_articles(
                    articles,
                    event.representative_article_id,
                    max_articles=(
                        args.max_articles
                    ),
                )
            )

            context = build_context(
                event,
                articles,
                selected_articles,
            )

            prompt = build_llm_prompt(
                context
            )

            for model in MODELS:

                key = (
                    event.id,
                    model,
                )

                if key in completed:

                    continue

                generation_number += 1

                print()
                print("-" * 80)

                print(
                    f"[{generation_number}/"
                    f"{total_generations}] "
                    f"Event {event.id} "
                    f"({event_info['size_group']}, "
                    f"{context['article_count']} articles)"
                )

                print(
                    f"Model: {model}"
                )

                print(
                    "Generating..."
                )

                try:

                    result = call_ollama(
                        model,
                        prompt,
                    )

                except Exception as exc:

                    print(
                        f"ERROR: {exc}"
                    )

                    # Don't kill the entire benchmark.
                    # Rerunning the script will retry it.
                    continue

                row = {
                    "event_id":
                        event.id,

                    "size_group":
                        event_info[
                            "size_group"
                        ],

                    "article_count":
                        context[
                            "article_count"
                        ],

                    "source_count":
                        context[
                            "source_count"
                        ],

                    "context_article_count":
                        context[
                            "context_article_count"
                        ],

                    "context_source_count":
                        context[
                            "context_source_count"
                        ],

                    "model":
                        model,

                    "title":
                        result["title"],

                    "summary":
                        result["summary"],

                    "prompt_tokens":
                        result[
                            "prompt_tokens"
                        ],

                    "generated_tokens":
                        result[
                            "generated_tokens"
                        ],

                    "elapsed_seconds":
                        result[
                            "elapsed_seconds"
                        ],

                    "total_duration_ns":
                        result[
                            "total_duration_ns"
                        ],

                    "load_duration_ns":
                        result[
                            "load_duration_ns"
                        ],

                    "prompt_eval_duration_ns":
                        result[
                            "prompt_eval_duration_ns"
                        ],

                    "eval_duration_ns":
                        result[
                            "eval_duration_ns"
                        ],
                }

                append_result(
                    row
                )

                completed.add(
                    key
                )

                print()
                print(
                    "TITLE:"
                )

                print(
                    result["title"]
                )

                print()
                print(
                    "SUMMARY:"
                )

                print(
                    result["summary"]
                )

                print()
                print(
                    f"Prompt tokens: "
                    f"{result['prompt_tokens']}"
                )

                print(
                    f"Generated tokens: "
                    f"{result['generated_tokens']}"
                )

                print(
                    f"Time: "
                    f"{result['elapsed_seconds']} s"
                )

        # -------------------------------------------------
        # Create blinded comparison once generations exist.
        # -------------------------------------------------

        create_blind_review_files()

        final_completed = (
            load_completed_generations()
        )

        print()
        print("=" * 80)
        print("BENCHMARK COMPLETE")
        print("=" * 80)

        print(
            f"Generations completed: "
            f"{len(final_completed)}/"
            f"{total_generations}"
        )

        print()
        print(
            f"Raw results:\n"
            f"  {RESULTS_FILE}"
        )

        print(
            f"Blind review:\n"
            f"  {BLIND_REVIEW_FILE}"
        )

        print(
            f"Answer key:\n"
            f"  {ANSWER_KEY_FILE}"
        )

        print(
            f"Event selection:\n"
            f"  {SELECTION_FILE}"
        )

    finally:

        session.close()


if __name__ == "__main__":
    main()
