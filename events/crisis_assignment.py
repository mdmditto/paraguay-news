"""Conservative, headline-first classification of five editorial Ueno crisis anchors.

This is an experimental *candidate classifier*, not independent verification that
an event occurred. Review the resulting articles before publishing or promotion.

An article only enters a fixed anchor when its own headline directly reports the
specified completed action. Mentions, demands, speculation and other developments
fall back to ordinary event clustering. Anchors never grow by member similarity.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

ANCHOR_START = datetime(2026, 11, 3, tzinfo=timezone.utc)
# Article publication can be later than the event itself; default experiment
# ends Nov 17, but this module does not impose an article end date.


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.casefold()).strip()


def has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


@dataclass(frozen=True)
class Anchor:
    key: str
    title: str
    # All required regexes must match the normalized *headline*.
    required: tuple[str, ...]
    # Any excluded regex prevents a match.
    excluded: tuple[str, ...] = ()


# Intentionally conservative: headline must explicitly describe the event,
# not just mention the crisis. Edit these patterns after manual review of
# representative Spanish headlines in your own dataset.
ANCHORS = (
    Anchor("UENO_01", "Resolución de Ueno Bank por el BCP", (
        r"\b(ueno|banco ueno)\b",
        r"\b(bcp|banco central|resolucion bancaria|resuelve|resolvio|resuelto|liquidacion|liquida)\b",
        r"\b(resolucion|resuelve|resolvio|resuelto|liquidacion|liquida|liquidar)\b",
    )),
    Anchor("UENO_02", "Imputación y detención de directivos de Ueno Bank", (
        r"\bueno\b",
        r"\b(directiv[oa]s?|ejecutiv[oa]s?|gerent[ea]s?|president[ea]? del banco|administrador[ea]s?)\b",
        r"\b(imputad[oa]s?|imputaron|imputa|imputacion|procesad[oa]s?)\b",
        r"\b(detenid[oa]s?|detencion|arrestad[oa]s?|aprehendid[oa]s?|detuvieron)\b",
    )),
    Anchor("UENO_03", "Renuncia de Santiago Peña", (
        r"\b(santiago pena|santi pena|presidente pena)\b",
        r"\b(renuncio|presento su renuncia|renuncia presentada|renuncia de santiago pena|renuncia del presidente pena)\b",
    )),
    Anchor("UENO_04", "Destitución de Santiago Peña por juicio político", (
        r"\b(santiago pena|santi pena|presidente pena)\b",
        r"\b(destituid[oa]|destituyeron|destitucion|removido|remocion)\b",
        r"\b(juicio politico|congreso|senado)\b",
    )),
    Anchor("UENO_05", "Imputación y detención de Santiago Peña", (
        r"\b(santiago pena|santi pena|presidente pena)\b",
        r"\b(imputad[oa]|imputaron|imputacion|procesado|imputa)\b",
        r"\b(detenid[oa]|detencion|arrestado|aprehendido|detuvieron)\b",
    )),
)

# Reject uncertainty and descriptions of a merely proposed action.
NEGATIVE = (
    r"\b(piden|pidieron|exigen|exigieron|solicitan|reclaman|proponen|propuesta)\b",
    r"\b(podria|podrian|posible|posibilidad|eventual|evalua|evaluan|analizan|analiza)\b",
    r"\b(si|ante una|buscan|intentan|intento de|rumor|rumores|falso|desmiente|niega|descarta)\b",
    r"\b(orden de detencion|pedido de detencion|solicitud de detencion|prision preventiva solicitada)\b",
    r"\b(no fue|no hay|sin|evita|evitar|evito)\b",
)


def classify(article) -> str | None:
    """Return a key only for an unambiguous, affirmative headline match.

    This intentionally favors precision over recall. It never infers the
    truth of a headline; human editorial verification is still required.
    """
    title = norm(article.title)
    if any(has(title, x) for x in NEGATIVE):
        return None
    matched = [a.key for a in ANCHORS
               if all(has(title, p) for p in a.required)
               and not any(has(title, p) for p in a.excluded)]
    return matched[0] if len(matched) == 1 else None


ANCHOR_BY_KEY = {a.key: a for a in ANCHORS}
