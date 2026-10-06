from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

from database.db import SessionLocal

from events.build_event_context import (
    get_events,
    load_event_articles,
    select_context_articles,
    build_context,
)


# =========================================================
# CONFIGURATION
# =========================================================

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "gpt-oss:20b"

MAX_CONTEXT_ARTICLES = 6

# Limit the amount of text contributed by each article.
# This prevents a few very long articles from consuming
# the entire context window.
MAX_BODY_CHARS = 6000

TEMPERATURE = 0.2


# =========================================================
# PROMPT
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
3. No inventes hechos, nombres, fechas, cifras, causas, motivaciones
   ni declaraciones.
4. Distingue entre hechos reportados, afirmaciones atribuidas, hipótesis,
   versiones contradictorias e información no confirmada.
5. Nunca conviertas una hipótesis o versión disputada en un hecho.
6. Para el título, utiliza únicamente hechos claramente respaldados.
7. Si existe desacuerdo sobre la causa o circunstancias de un hecho,
   omite esa explicación del título.
8. Prefiere un título general y correcto antes que uno específico
   pero incierto.
9. El artículo representativo no es una fuente de verdad privilegiada.
10. Cuando exista información contradictoria, exprésala como incertidumbre
    en el resumen si es relevante.
11. Ante la duda, omite una afirmación antes que presentarla como cierta.
12. El título debe ser breve, descriptivo y factual.
13. El resumen debe tener entre 2 y 4 oraciones.

IMPORTANTE: responde exclusivamente en español.
""".strip()


# =========================================================
# BUILD USER PROMPT
# =========================================================

def build_llm_prompt(context: dict) -> str:

    sections = []

    sections.append(
        f"EVENTO {context['event_id']}\n"
        f"Cantidad total de artículos en el evento: "
        f"{context['article_count']}\n"
        f"Cantidad total de medios: "
        f"{context['source_count']}\n"
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

        section = f"""
--------------------------------------------------
ARTÍCULO {index} — {role}
--------------------------------------------------

Medio: {article["source"]}
Fecha: {article["published_at"]}
Título: {article["title"]}

Texto:
{body}
""".strip()

        sections.append(section)

    sections.append(
        """Genera ahora la representación neutral del evento.
        Antes de escribir el título, identifica mentalmente cuál es el hecho
        central que puede afirmarse sin depender de hipótesis o versiones
        disputadas. El título debe describir ese hecho central. 
        IDIOMA OBLIGATORIO: ESPAÑOL.
        Devuelve únicamente:
        {
        "title": "Título en español",
        "summary": "Resumen en español"
        }""".strip()
    )

    return "\n\n".join(sections)


# =========================================================
# OLLAMA
# =========================================================

def call_ollama(
    user_prompt: str,
) -> dict:

    payload = {
        "model": OLLAMA_MODEL,

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

        # Qwen3 supports thinking. We do not need it
        # for this constrained summarization task.
        "think": False,

        # Ollama can constrain the response to JSON.
        "format": "json",

        "options": {
            "temperature": TEMPERATURE,

            # Plenty for title + short summary.
            "num_predict": 500,
        },
    }

    data = json.dumps(
        payload
    ).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={
            "Content-Type":
                "application/json",
        },
        method="POST",
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=300,
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

    message = result.get(
        "message",
        {},
    )

    content = message.get(
        "content",
        "",
    ).strip()

    if not content:

        raise RuntimeError(
            "Ollama returned an empty response."
        )

    try:

        parsed = json.loads(
            content
        )

    except json.JSONDecodeError as exc:

        raise RuntimeError(
            "Qwen returned invalid JSON:\n"
            f"{content}"
        ) from exc

    return {
        "title": parsed.get(
            "title",
            ""
        ).strip(),

        "summary": parsed.get(
            "summary",
            ""
        ).strip(),

        "_ollama": {
            "model": result.get(
                "model"
            ),

            "total_duration": result.get(
                "total_duration"
            ),

            "load_duration": result.get(
                "load_duration"
            ),

            "prompt_eval_count":
                result.get(
                    "prompt_eval_count"
                ),

            "eval_count":
                result.get(
                    "eval_count"
                ),

            "eval_duration":
                result.get(
                    "eval_duration"
                ),
        },
    }


# =========================================================
# VALIDATION
# =========================================================

def validate_generation(
    generation: dict,
):

    title = generation[
        "title"
    ]

    summary = generation[
        "summary"
    ]

    if not title:
        raise ValueError(
            "Generated title is empty."
        )

    if not summary:
        raise ValueError(
            "Generated summary is empty."
        )

    if len(title) > 250:
        raise ValueError(
            "Generated title is unexpectedly long."
        )

    if len(summary) > 2000:
        raise ValueError(
            "Generated summary is unexpectedly long."
        )


# =========================================================
# DISPLAY
# =========================================================

def print_generation(
    context,
    generation,
):

    print()
    print("=" * 80)

    print(
        f"EVENT {context['event_id']}"
    )

    print(
        f"Articles in event: "
        f"{context['article_count']}"
    )

    print(
        f"Sources in event: "
        f"{context['source_count']}"
    )

    print(
        f"Articles sent to Qwen: "
        f"{context['context_article_count']}"
    )

    print(
        f"Sources sent to Qwen: "
        f"{context['context_source_count']}"
    )

    print()
    print("ORIGINAL EVENT TITLE:")
    print(
        context["current_title"]
    )

    print()
    print("GENERATED TITLE:")
    print(
        generation["title"]
    )

    print()
    print("GENERATED SUMMARY:")
    print(
        generation["summary"]
    )

    stats = generation[
        "_ollama"
    ]

    print()
    print(
        "Prompt tokens:",
        stats[
            "prompt_eval_count"
        ],
    )

    print(
        "Generated tokens:",
        stats[
            "eval_count"
        ],
    )


# =========================================================
# MAIN
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Generate neutral event titles "
            "and summaries using Qwen3 "
            "through Ollama."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help=(
            "Number of events to generate. "
            "Default: 1."
        ),
    )

    parser.add_argument(
        "--event-id",
        type=int,
        default=None,
        help=(
            "Generate content for one "
            "specific event."
        ),
    )

    parser.add_argument(
        "--max-articles",
        type=int,
        default=MAX_CONTEXT_ARTICLES,
        help=(
            "Maximum number of articles "
            "sent to the model."
        ),
    )

    args = parser.parse_args()

    print("=" * 80)
    print("EVENT CONTENT GENERATOR")
    print("=" * 80)

    print(
        f"Model: {OLLAMA_MODEL}"
    )

    print(
        f"Ollama: {OLLAMA_URL}"
    )

    print(
        f"Max context articles: "
        f"{args.max_articles}"
    )

    session = SessionLocal()

    try:

        events = get_events(
            session,
            limit=args.limit,
            event_id=args.event_id,
        )

        print(
            f"Events selected: "
            f"{len(events)}"
        )

        for event in events:

            articles = (
                load_event_articles(
                    session,
                    event.id,
                )
            )

            if not articles:

                print(
                    f"Event {event.id}: "
                    f"no articles found."
                )

                continue

            selected = (
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
                selected,
            )

            prompt = build_llm_prompt(
                context
            )

            print()
            print(
                f"Generating event "
                f"{event.id}..."
            )

            generation = call_ollama(
                prompt
            )

            validate_generation(
                generation
            )

            print_generation(
                context,
                generation,
            )

        print()
        print("=" * 80)
        print("DONE")
        print("=" * 80)

    finally:

        session.close()


if __name__ == "__main__":
    main()
