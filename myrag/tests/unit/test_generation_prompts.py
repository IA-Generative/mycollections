"""Les prompts français versionnés dans le dépôt se chargent sur les bons objets."""

import json
from pathlib import Path

import pytest

pytest.importorskip("ragas")

from app.generation import modele, moteur  # noqa: E402

DOSSIER = Path(moteur.__file__).parent / "prompts"


def test_chaque_objet_de_la_generation_a_ses_prompts_francais():
    llm = modele.fabriquer_llm(modele.Compteurs(), url="https://x.fake-domain.name/v1", cle="c", modele="m")
    transforms, dist = moteur.construire(llm, {cle: 1.0 for cle in moteur.SYNTHESES})
    objets = [*transforms, *(s for s, _ in dist)]
    assert moteur.charger_prompts(objets) == len(objets)
    for o in objets:
        for p in o.get_prompts().values():
            assert p.language == "french" and p.examples, (o.name, p.name)


@pytest.mark.parametrize("fichier", sorted(DOSSIER.glob("*.json")), ids=lambda f: f.name)
def test_fichiers_relus(fichier):
    d = json.loads(fichier.read_text(encoding="utf-8"))
    assert d["language"] == "french" and d["original_hash"] is None
    if "themes_personas_matching" in fichier.name:
        ex = d["examples"][0]
        noms = {p["name"] for p in ex["input"]["personas"]}
        assert set(ex["output"]["mapping"]) == noms, "les clés de l'exemple doivent être les noms des personas"
    if "query_answer_generation" in fichier.name:
        assert "seul saut" not in d["instruction"] and "en français" in d["instruction"]
