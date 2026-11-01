"""Le rapport d'une nuit : mesures, seuils go / no-go, tendance, alertes en tête."""

from __future__ import annotations

import json

from scripts.campagne import rapport


def _h(
    variante,
    question,
    *,
    consigne_attendue=None,
    consigne_obtenue=None,
    source5=True,
    juge="conforme",
    consignes=False,
    contraintes=None,
    refus=(False, False),
    statut="joue",
    duree=1000,
    part=0.4,
):
    return {
        "cle": f"harnais|{variante}|{question}|2026-11-01",
        "phase": "harnais",
        "variante": variante,
        "question": question,
        "nuit": "2026-11-01",
        "statut": statut,
        "http": 200,
        "executer": 1,
        "consignes_fiche": consignes,
        "texte": f"Question {question} ?",
        "resultat": {"duree_ms": duree, "passages": [["essai-guide", "Fiche", 0.5, "d1"]]},
        "verdicts": {
            "consigne_attendue": consigne_attendue,
            "consigne_obtenue": consigne_obtenue,
            "consigne_ok": consigne_attendue == consigne_obtenue,
            "consigne_a_tort": consigne_obtenue is not None and consigne_obtenue != consigne_attendue,
            "part_contactees": part,
            "source@1": source5,
            "source@5": source5,
            "relais": [],
            "incidents": [],
            "refus_attendu": refus[0],
            "refus_obtenu": refus[1],
            "renvois": {"ok": True, "cites": [1], "invalides": []},
            "contraintes": contraintes or {},
        },
        "liens": {"verifies": 1, "valides": 1},
        "juge": {"verdict": juge} if juge else None,
    }


def _lignes():
    return [
        _h("s0", "q1", juge="partiel", part=1.0),
        _h("s0", "q2", juge="non_conforme", part=1.0, source5=False),
        _h("s2", "q1", consigne_attendue="algeriens", consigne_obtenue="algeriens", consignes=True, contraintes={"accord_avant_code": True}),
        _h("s2", "q2", consigne_attendue="algeriens", consigne_obtenue=None, consignes=True, contraintes={"accord_avant_code": False}),
        _h("s2", "q3", consigne_obtenue="pieces", consignes=True, refus=(True, True)),
    ]


def test_les_mesures_du_harnais_par_variante():
    m = rapport.mesures(_lignes())
    h = m["harnais"]
    assert (h["base"], h["essai"]) == ("s0", "s2")
    s2 = h["variantes"]["s2"]
    assert s2["consigne_a_raison_pct"] == 50.0 and s2["consigne_a_tort_pct"] == 33.3
    assert s2["accord_avant_code_pct"] == 50.0 and s2["refus_a_raison_pct"] == 100.0
    assert s2["sources_contactees_pct"] == 40.0 and s2["juge_conforme_pct"] == 100.0
    assert h["variantes"]["s0"]["consigne_a_raison_pct"] is None  # une fiche sans consigne ne se mesure pas là-dessus
    assert h["variantes"]["s0"]["source5_pct"] == 50.0
    assert h["ecart_score"] == 1.5  # q1, q2 jugées dans les deux : 2 − 0,5
    assert m["incidents"] == 0 and h["liens_valides_pct"] == 100.0


def test_la_derniere_ligne_d_un_essai_l_emporte():
    lignes = [_h("s0", "q1", statut="erreur", juge=None), _h("s0", "q1")]
    assert rapport.mesures(lignes)["harnais"]["variantes"]["s0"]["essais"] == 1


def test_les_seuils_disent_ok_ko_ou_non_mesure():
    s = {x["clef"]: x for x in rapport.seuils(rapport.mesures(_lignes()))}
    assert s["harnais.variantes.{essai}.consigne_a_raison_pct"]["statut"] == "KO"
    assert s["harnais.variantes.{essai}.sources_contactees_pct"]["statut"] == "OK"
    assert s["incidents"]["statut"] == "OK"
    assert s["mcp.agent.bon_choix_pct"]["statut"] == "non mesuré"
    assert rapport.verdict_global(list(s.values())) == "NO-GO"


def test_le_rapport_s_ecrit_compare_a_la_nuit_precedente_et_alerte_en_tete(tmp_path):
    avant = tmp_path / "2026-10-31"
    avant.mkdir()
    (avant / "essais.jsonl").write_text("\n".join(json.dumps(d) for d in _lignes()[:2]))
    rapport.ecrire(avant)
    nuit = tmp_path / "2026-11-01"
    nuit.mkdir()
    (nuit / "essais.jsonl").write_text("\n".join(json.dumps(d) for d in _lignes()) + "\n{coupée")
    (nuit / "etat.json").write_text(json.dumps({"nuit": "2026-11-01", "executions": [{"arret": {"motif": "5xx", "detail": "11 erreurs serveur"}, "reconnexions": 1}]}))
    synthese, mesures = rapport.ecrire(nuit)
    texte = synthese.read_text()
    assert texte.splitlines()[2].startswith("> **ARRÊT (5xx)**")
    assert "## Go / no-go : NO-GO" in texte and "## Tendance (nuit du 2026-10-31)" in texte
    assert "consigne None au lieu de algeriens" in texte and "Question q2 ?" in texte
    m = json.loads(mesures.read_text())
    assert m["verdict"] == "NO-GO" and m["arret"]["motif"] == "5xx" and m["consommation"]["reconnexions"] == 1


def test_les_mesures_mcp():
    def ligne(q, bon, source5, categorie="declenche", refus=None, lister=8000):
        return {
            "cle": f"mcp|agent|{q}|n",
            "phase": "mcp",
            "variante": "agent",
            "question": q,
            "statut": "joue",
            "appels_modele": 3,
            "attendu": {"categorie": categorie},
            "conversation": {"duree_ms": 4000},
            "verdicts": {
                "bon_choix": bon,
                "bon_choix_rang1": bon,
                "rechercher_appele": source5 is not None,
                "source@5": source5,
                "refus_obtenu": refus,
                "appels_outils": 2,
                "lister_octets": lister,
                "lister_assistants": 12,
                "incidents": [],
            },
        }

    m = rapport.mesures([ligne("a", True, True), ligne("b", False, False), ligne("c", None, None, "hors_champ", True)])
    agent = m["mcp"]["agent"]
    assert agent["bon_choix_pct"] == 50.0 and agent["rechercher_appele_pct"] == 100.0 and agent["hors_catalogue_pct"] == 100.0
    assert agent["lister_jetons_estimes"] == 2000 and agent["appels_modele"] == 9
    assert m["mcp"]["rappel5_pct"] == 50.0
