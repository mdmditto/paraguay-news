"""Experimental conservative event-identity gates for staging only.

A headline's action label is a weak signal, not a factual verifier. We reject
explicitly incompatible primary-action labels, and require direct similarity
to the immutable seed. Unlabeled headlines are checked by seed similarity only.
"""
from __future__ import annotations
import re
from events.crisis_assignment import norm

# Ordered: distinguish procedural steps even when a headline mentions several.
# Headlines with multiple action classes are marked ambiguous rather than forced.
ACTION_PATTERNS = {
    'bank_resolution': r'\b(resolucion (?:de|del) (?:ueno|banco)|resuelv[ea]|resolvio|liquidacion bancaria|liquidan (?:a )?ueno|bcp (?:interviene|intervino) ueno)\b',
    'bank_deposit_repayment': r'\b(reembolso|devolucion|devolveran|devolvieron|cobro de depositos|pago a ahorristas|garantia de depositos|depositantes cobraran)\b',
    'investigation': r'\b(investiga(?:n|cion|ciones|r)?|indaga(?:n|cion)?|pesquisa|abre causa|investigaran)\b',
    'charges': r'\b(imputad[oa]s?|imputacion|imputaron|imputa(?:n)?|procesad[oa]s?|acusacion formal)\b',
    'arrest': r'\b(detenid[oa]s?|detencion|detuvieron|arrestad[oa]s?|aprehendid[oa]s?|capturad[oa]s?)\b',
    'search': r'\b(allanamiento|allanaron|allanan|allano|requisa|cateo)\b',
    'resignation': r'\b(renuncio|presento su renuncia|renuncia presentada|dimision|dimitio)\b',
    'impeachment_proposal': r'\b(piden juicio politico|promueven juicio politico|impulsan juicio politico|libelo acusatorio|presentan juicio politico)\b',
    'impeachment_removal': r'\b(destituid[oa]|destituyeron|destitucion|removido del cargo)\b',
    'candidacy': r'\b(candidatura|postulacion|precandidatura|internas presidenciales)\b',
    'appointment': r'\b(nombrad[oa]|designad[oa]|asumio como|nuevo presidente del bcp|proponen a .* para presidir)\b',
}

def action_labels(title):
    t = norm(title or '')
    return frozenset(key for key, pattern in ACTION_PATTERNS.items() if re.search(pattern, t))

# Some article titles contain both an investigation and an arrest, for example.
# Only reject when both headlines have a single, different primary action.
def incompatible_actions(candidate_labels, seed_labels):
    return len(candidate_labels) == 1 and len(seed_labels) == 1 and candidate_labels != seed_labels


def coherent_with_seed(article, seed_article, vector, seed_vector, *, threshold=0.84):
    """Return (accepted, reason, seed_cosine) for a prospective membership."""
    similarity = float(vector @ seed_vector)
    if similarity < threshold:
        return False, 'seed_similarity', similarity
    if incompatible_actions(action_labels(article.title), action_labels(seed_article.title)):
        return False, 'action_conflict', similarity
    return True, 'accepted', similarity
