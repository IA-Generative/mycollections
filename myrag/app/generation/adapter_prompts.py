"""Adapter une fois les prompts de ragas en français, et les écrire dans le dépôt.

    cd myrag && MYCOLLECTIONS_GENERATION_LLM_URL=… MYCOLLECTIONS_GENERATION_LLM_CLE=… \\
        MYCOLLECTIONS_GENERATION_LLM_MODELE=… uv run python -m app.generation.adapter_prompts

Les fichiers écrits (`app/generation/prompts/{nom}_{prompt}_french.json`) sont RELUS À LA MAIN
avant d'être commités : ils font partie du code livré. Le moteur les charge à chaque run ; il ne
traduit jamais rien lui-même (pas d'appel au modèle pour cela pendant un run).
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.generation import exiger_prete, modele, moteur


async def adapter(dossier: Path, langue: str, traduire_instructions: bool) -> list[str]:
    compteurs = modele.Compteurs()
    llm = modele.fabriquer_llm(compteurs)
    transforms, dist = moteur.construire(llm, {cle: 1.0 for cle in moteur.SYNTHESES})
    ecrits = []
    for objet in [*transforms, *(s for s, _ in dist)]:
        adaptes = await objet.adapt_prompts(langue, llm=llm, adapt_instruction=traduire_instructions)
        objet.set_prompts(**adaptes)
        objet.save_prompts(str(dossier))
        ecrits += [f"{objet.name}_{nom}_{langue}.json" for nom in adaptes]
    print(f"{len(ecrits)} prompts écrits dans {dossier} — {compteurs.instantane()}")
    return ecrits


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dossier", type=Path, default=moteur.PROMPTS_DIR)
    p.add_argument("--langue", default=moteur.LANGUE)
    p.add_argument("--garder-instructions", action="store_true", help="ne traduire que les exemples (les instructions restent en anglais)")
    a = p.parse_args()
    exiger_prete()
    a.dossier.mkdir(parents=True, exist_ok=True)
    for nom in asyncio.run(adapter(a.dossier, a.langue, not a.garder_instructions)):
        print(" ", nom)


if __name__ == "__main__":
    main()
