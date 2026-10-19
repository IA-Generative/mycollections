"""Proposer des personas d'après les documents d'une collection.

Le modèle lit un échantillon de passages et décrit qui interrogerait ces documents, et dans
quelle situation. Rien n'est enregistré : la personne choisit ce qu'elle garde, et peut tout
modifier. Un seul appel au modèle, compté comme les autres.

Les passages sont des DONNÉES non fiables (un document peut contenir des instructions) : ils sont
neutralisés et encadrés (`security_utils`), et la réponse est validée champ par champ — un nom
trop long, une description vide ou un doublon sont écartés, jamais réécrits en silence.
"""

from __future__ import annotations

import asyncio
import json
import re
import time

from app.security_utils import neutralize_for_prompt, sanitize_oneline, wrap_untrusted

PASSAGES = 12
EXTRAIT_MAX = 600
NOMBRE_MAX = 6

CONSIGNE = """Tu aides à préparer l'évaluation d'un assistant qui répond à partir d'une collection de documents d'un ministère.
À partir des extraits ci-dessous, propose {nombre} personas DIFFÉRENTS : des personnes qui interrogeraient
vraisemblablement ces documents, chacune dans une situation précise (son métier, à qui elle répond, ce qu'elle cherche).
Varie les profils : agent qui répond à un usager, gestionnaire, encadrant, nouvel arrivant, usager lui-même si c'est pertinent.
{deja}
Réponds UNIQUEMENT par un JSON de la forme :
{{"personas": [{{"nom": "nom court du profil (60 caractères au plus)", "description_role": "une ou deux phrases : qui, dans quelle situation, ce qu'il cherche"}}]}}

{extraits}"""


def construire_prompt(passages: list[str], nombre: int, existants: list[str]) -> str:
    extraits = "\n\n".join(f"[{i + 1}] {neutralize_for_prompt(p, max_len=EXTRAIT_MAX)}" for i, p in enumerate(passages))
    deja = ""
    if existants:
        noms = ", ".join(sanitize_oneline(n, 120) for n in existants)
        deja = f"Ne reprends pas ces personas déjà définis : {noms}."
    return CONSIGNE.format(nombre=nombre, deja=deja, extraits=wrap_untrusted(extraits, label="EXTRAITS"))


def _json_dans(texte: str):
    texte = (texte or "").strip()
    bloc = re.search(r"```(?:json)?\s*(.*?)```", texte, flags=re.S)
    if bloc:
        texte = bloc.group(1)
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut < 0 or fin <= debut:
        raise ValueError("pas de JSON")
    return json.loads(texte[debut : fin + 1])


def lire_propositions(texte: str, existants: list[str], nombre: int) -> list[dict]:
    """Les personas proposés, validés : nom 2-60 caractères sur une ligne, description 20-600,
    pas de doublon (entre eux ni avec l'existant, à la casse près)."""
    donnees = _json_dans(texte)
    brutes = donnees.get("personas") if isinstance(donnees, dict) else donnees
    vus = {n.strip().lower() for n in existants}
    sortie = []
    for b in brutes if isinstance(brutes, list) else []:
        if not isinstance(b, dict):
            continue
        nom = sanitize_oneline(str(b.get("nom") or ""), 200)
        desc = " ".join(str(b.get("description_role") or "").split())
        if not (2 <= len(nom) <= 60) or not (20 <= len(desc) <= 600) or nom.lower() in vus:
            continue
        vus.add(nom.lower())
        sortie.append({"nom": nom, "description_role": desc})
        if len(sortie) >= nombre:
            break
    return sortie


async def proposer(name: str, nombre: int, existants: list[str]) -> dict:
    """{"propositions": [...], "passages": n, "compteurs": {...}, "duree_s": s}.
    Lève LookupError si aucun passage n'est lisible, ValueError si la réponse est illisible."""
    from app.generation import modele
    from app.generation.morceaux import lire_echantillon
    from app.generation.resultats import Compteurs
    from app.services.openrag_client import OpenRAGClient

    debut = time.monotonic()
    morceaux, nb_fichiers = await lire_echantillon(OpenRAGClient(timeout=60.0), name, PASSAGES, graine="personas")
    if not morceaux:
        raise LookupError(
            "Cette collection n'a encore aucun document indexé."
            if not nb_fichiers
            else "Aucun passage n'a pu être lu : l'indexation est peut-être encore en cours. Réessayez dans quelques minutes."
        )
    compteurs = Compteurs()
    llm = modele.fabriquer_llm(compteurs)
    prompt = construire_prompt([m.texte for m in morceaux], nombre, existants)

    from langchain_core.prompt_values import StringPromptValue

    resultat = await asyncio.to_thread(lambda: llm.generate_text(StringPromptValue(text=prompt), 1, 0.7))  # ty: ignore[invalid-argument-type]
    texte = resultat.generations[0][0].text
    propositions = lire_propositions(texte, existants, nombre)
    if not propositions:
        raise ValueError("Le modèle n'a proposé aucun persona exploitable. Réessayez.")
    return {"propositions": propositions, "passages": len(morceaux), "compteurs": compteurs.instantane(), "duree_s": round(time.monotonic() - debut, 1)}
