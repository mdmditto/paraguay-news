from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

from sqlalchemy import select

from database.db import SessionLocal
from database.models import (
    Event,
    EventContent,
    EventContentContext,
)

from events.build_event_context import (
    load_event_articles,
    select_context_articles,
    build_context,
)


# =========================================================
# CONFIGURATION
# =========================================================

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen3:8b"

MAX_CONTEXT_ARTICLES = 6
MAX_BODY_CHARS = 6000

TEMPERATURE = 0.2
NUM_PREDICT = 500


# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
IDIOMA OBLIGATORIO: ESPAÑOL.

Eres un editor de noticias encargado de sintetizar varios artículos
periodísticos que pertenecen al mismo evento.

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

6. Para el TÍTULO utiliza solamente hechos claramente respaldados
   por los artículos seleccionados.

7. Si existe desacuerdo sobre la causa, mecanismo o circunstancias
   de un hecho, omite esa explicación del título.

8. Prefiere un título más general pero correcto antes que un título
   más específico basado en información incierta.

9. El título debe representar el acontecimiento principal compartido
   por los artículos, no el enfoque particular de un solo medio.

10. El artículo marcado como REPRESENTATIVO no es una fuente de verdad
    privilegiada. Sus afirmaciones también deben contrastarse con los
    demás artículos.

11. Si distintas fuentes presentan versiones contradictorias, el resumen
    puede explicar el desacuerdo de manera explícita y neutral.

12. Cuando una afirmación importante provenga solamente de una fuente,
    atribúyela si decides incluirla. No la presentes como consenso.

13. Evita lenguaje sensacionalista, partidista, promocional o valorativo.

14. No menciones los nombres de los medios salvo que el medio sea parte
    relevante del acontecimiento o sea necesario atribuir una afirmación.

15. No escribas frases como "según los artículos proporcionados".

16. No agregues antecedentes que no estén presentes en los textos.

17. El resumen debe explicar qué ocurrió y priorizar la información
    central respaldada por múltiples artículos.

18. El título debe ser breve, descriptivo y factual.

19. El resumen debe tener entre 2 y 4 oraciones.

20. Ante la duda, OMITE una afirmación antes que presentarla como cierta.

21. Responde exclusivamente en español.
""".strip()


# =========================================================
# PROMPT
# =========================================================

def build_llm_prompt(context: dict) -> str:

    sections = []

    sections.append(
        f"EVENTO {context['event_id']}\n"
        f"Cantidad total de artículos: "
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

Antes de escribir el título, identifica cuál es el hecho central que
puede afirmarse sin depender de hipótesis o versiones disputadas.

El título debe describir ese hecho central.

IDIOMA OBLIGATORIO: ESPAÑOL.

Devuelve únicamente:

{
  "title": "Título en español",
  "summary": "Resumen en español"
}
""".strip()
    )

    return "\n\n".join(
        sections
    )


# =========================================================
# OLLAMA
# =========================================================

def call_ollama(
    prompt: str,
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
                "content": prompt,
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
                response
                .read()
                .decode("utf-8")
            )

    except urllib.error.URLError as exc:

        raise RuntimeError(
            f"Could not connect to Ollama: "
            f"{exc}"
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
            "Ollama returned an empty response."
        )

    try:

        parsed = json.loads(
            content
        )

    except json.JSONDecodeError as exc:

        raise RuntimeError(
            "Invalid JSON returned by Qwen:\n"
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
            "Generated title is empty."
        )

    if not summary:
        raise RuntimeError(
            "Generated summary is empty."
        )

    return {
        "title": title,
        "summary": summary,

        "prompt_tokens":
            result.get(
                "prompt_eval_count"
            ),

        "generated_tokens":
            result.get(
                "eval_count"
            ),

        "elapsed_seconds":
            round(elapsed, 2),
    }


# =========================================================
# EVENTS TO GENERATE
# =========================================================

def get_events_to_generate(
    session,
    limit: int | None,
):

    # Only events with more than one article are
    # summarized for now.
    #
    # LEFT JOIN with EventContent ensures that events
    # already generated are skipped automatically.

    stmt = (
        select(Event)
        .outerjoin(
            EventContent,
            EventContent.event_id
            == Event.id,
        )
        .where(
            Event.article_count > 1,

            Event.representative_article_id
            .is_not(None),

            EventContent.event_id
            .is_(None),
        )
        .order_by(
            Event.last_seen_at.desc(),
            Event.id.desc(),
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


# =========================================================
# SAVE DRAFT
# =========================================================

def save_event_draft(
    session,
    event,
    context,
    result,
):

    # -----------------------------------------------------
    # Save generated title + summary
    # -----------------------------------------------------

    content = EventContent(
        event_id=event.id,

        generated_title=(
            result["title"]
        ),

        generated_summary=(
            result["summary"]
        ),

        status="draft",

        model=OLLAMA_MODEL,
    )

    session.add(
        content
    )

    # -----------------------------------------------------
    # Save the EXACT context used by the LLM.
    #
    # This allows the review interface to later show
    # precisely which articles Qwen saw when generating
    # the title and summary.
    # -----------------------------------------------------

    for position, article in enumerate(
        context["articles"],
        start=1,
    ):

        context_row = EventContentContext(
            event_id=event.id,

            article_id=article[
                "article_id"
            ],

            position=position,

            is_representative=article[
                "is_representative"
            ],
        )

        session.add(
            context_row
        )

    # -----------------------------------------------------
    # One transaction per event.
    #
    # EventContent and EventContentContext are committed
    # together. If anything fails, neither should remain
    # partially saved.
    # -----------------------------------------------------

    session.commit()


# =========================================================
# MAIN
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Generate draft event content "
            "using Qwen3 8B."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help=(
            "Number of drafts to generate. "
            "Default: 10."
        ),
    )

    parser.add_argument(
        "--max-articles",
        type=int,
        default=MAX_CONTEXT_ARTICLES,
        help=(
            "Maximum number of articles "
            "included in the LLM context."
        ),
    )

    args = parser.parse_args()

    session = SessionLocal()

    try:

        events = (
            get_events_to_generate(
                session,
                args.limit,
            )
        )

        print("=" * 80)
        print("EVENT DRAFT GENERATOR")
        print("=" * 80)

        print(
            f"Model: {OLLAMA_MODEL}"
        )

        print(
            f"Events selected: "
            f"{len(events)}"
        )

        print(
            f"Max context articles: "
            f"{args.max_articles}"
        )

        print()

        generated = 0
        failed = 0

        for index, event in enumerate(
            events,
            start=1,
        ):

            print("-" * 80)

            print(
                f"[{index}/{len(events)}] "
                f"Event {event.id}"
            )

            print(
                f"Articles: "
                f"{event.article_count}"
            )

            try:

                # -----------------------------------------
                # Load all articles belonging to event
                # -----------------------------------------

                articles = (
                    load_event_articles(
                        session,
                        event.id,
                    )
                )

                if not articles:

                    raise RuntimeError(
                        f"Event {event.id} "
                        f"contains no usable articles."
                    )

                # -----------------------------------------
                # Select representative + supporting
                # articles.
                # -----------------------------------------

                selected = (
                    select_context_articles(
                        articles,
                        event.representative_article_id,
                        max_articles=(
                            args.max_articles
                        ),
                    )
                )

                if not selected:

                    raise RuntimeError(
                        f"No context articles selected "
                        f"for event {event.id}."
                    )

                # -----------------------------------------
                # Build context
                # -----------------------------------------

                context = build_context(
                    event,
                    articles,
                    selected,
                )

                # -----------------------------------------
                # Build prompt
                # -----------------------------------------

                prompt = build_llm_prompt(
                    context
                )

                # -----------------------------------------
                # Generate
                # -----------------------------------------

                result = call_ollama(
                    prompt
                )

                # -----------------------------------------
                # Persist BOTH generated content and
                # exact LLM context.
                # -----------------------------------------

                save_event_draft(
                    session=session,
                    event=event,
                    context=context,
                    result=result,
                )

                generated += 1

                # -----------------------------------------
                # Diagnostics
                # -----------------------------------------

                print()
                print("TITLE:")
                print(
                    result["title"]
                )

                print()
                print("SUMMARY:")
                print(
                    result["summary"]
                )

                print()

                print(
                    f"Context: "
                    f"{context['context_article_count']} "
                    f"articles / "
                    f"{context['context_source_count']} "
                    f"sources"
                )

                print(
                    f"Tokens: "
                    f"{result['prompt_tokens']} + "
                    f"{result['generated_tokens']}"
                )

                print(
                    f"Time: "
                    f"{result['elapsed_seconds']}s"
                )

                print(
                    "Saved as draft."
                )

            except Exception as exc:

                # Roll back anything associated with this
                # particular event.
                session.rollback()

                failed += 1

                print()
                print(
                    f"ERROR: {exc}"
                )

        print()
        print("=" * 80)
        print("GENERATION COMPLETE")
        print("=" * 80)

        print(
            f"Generated: {generated}"
        )

        print(
            f"Failed: {failed}"
        )

    finally:

        session.close()


if __name__ == "__main__":
    main()