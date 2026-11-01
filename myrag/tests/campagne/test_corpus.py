"""Les fiches d'essai et le jeu de questions : alias résolus, préfixe imposé, application idempotente."""

from __future__ import annotations

import collections
import json

import httpx
import pytest

from app.harnais import fiche_yaml
from scripts.campagne import corpus
from scripts.campagne.cible import Cible
from tests.campagne.conftest import BASE, CORRESPONDANCE, JEU, FauxSso


def test_les_trois_fiches_se_resolvent_et_ne_portent_que_des_alias(variantes):
    assert [v.nom for v in variantes] == ["s0", "s1", "s2"]
    assert [v.assistant for v in variantes] == ["e2e-camp-sejour-s0", "e2e-camp-sejour-s1", "e2e-camp-sejour-s2"]
    for v in variantes:
        assert set(v.sources) == set(CORRESPONDANCE.values())  # chaque source est passée par la correspondance
        assert set(v.alias.values()) == set(CORRESPONDANCE)
    assert variantes[0].consignes == {} and variantes[1].consignes == {}
    assert set(variantes[2].consignes) == {"algeriens", "contentieux", "pieces"}  # « juridique » vaut toujours : jamais retenue
    relais = [e for c in variantes[2].fiche.consignes for e in c.chercher if e.avec]
    assert [(e.source, e.avec) for e in relais] == [("essai-jurisprudence", "article_trouve")]


def test_la_fiche_ecrite_se_relit_avec_la_meme_empreinte(variantes):
    for v in variantes:
        assert corpus.Variante(v.nom, fiche_yaml.charger(v.texte())).empreinte == v.empreinte


def test_le_jeu_compte_une_quarantaine_de_questions_de_chaque_sorte(questions, variantes):
    assert 35 <= len(questions) <= 45
    par = collections.Counter(q.categorie for q in questions)
    assert set(par) == set(corpus.CATEGORIES) and par["declenche"] >= 10 and par["voisine"] >= 8 and par["pieces"] >= 6
    s0, s2 = variantes[0], variantes[2]
    for q in questions:
        if q.categorie == "hors_champ":
            assert q.refus_attendu and not q.sources and q.consigne is None
        if q.categorie in ("declenche", "voisine", "pieces"):
            assert q.sources and not q.refus_attendu, q.id
        if q.categorie == "voisine":
            assert q.consigne is None, q.id
        if q.categorie == "injection":
            assert q.canari, q.id
        assert q.consigne_pour(s0) is None  # sans consigne dans la fiche, aucune n'est attendue
    assert {q.consigne_pour(s2) for q in questions if q.categorie in ("declenche", "pieces")} == {"algeriens", "contentieux", "pieces"}


def test_un_assistant_hors_du_prefixe_est_refuse(correspondance):
    texte = (JEU / "s0.yaml").read_text(encoding="utf-8").replace("e2e-camp-sejour-s0", "sejour-des-etrangers")
    with pytest.raises(corpus.CorpusInvalide, match="e2e-camp-"):
        corpus.resoudre_fiche(texte, correspondance)


def test_un_alias_inconnu_est_refuse(correspondance):
    del correspondance["jurisprudence"]
    with pytest.raises(corpus.CorpusInvalide, match="jurisprudence"):
        corpus.charger_variantes(JEU, correspondance)


def test_la_correspondance_est_obligatoire_et_bien_formee(tmp_path, monkeypatch):
    monkeypatch.delenv("CAMPAGNE_CORRESPONDANCE", raising=False)
    with pytest.raises(corpus.CorpusInvalide, match="CAMPAGNE_CORRESPONDANCE"):
        corpus.charger_correspondance()
    f = tmp_path / "c.json"
    f.write_text(json.dumps(["guide"]), encoding="utf-8")
    with pytest.raises(corpus.CorpusInvalide):
        corpus.charger_correspondance(f)


def _cible(horloge, gestionnaire):
    return Cible(BASE, FauxSso(horloge), client=httpx.Client(transport=httpx.MockTransport(gestionnaire)), horloge=horloge, dormir=horloge.dormir)


def test_appliquer_ne_reecrit_pas_une_fiche_deja_conforme(horloge, variantes):
    s2 = variantes[2]
    appels = []

    def gestionnaire(req):
        appels.append((req.method, req.url.path))
        if req.method == "GET":
            return httpx.Response(200, text=s2.texte())
        if req.url.path.endswith("/publier"):
            return httpx.Response(200, json={"version": 3, "nouvelle": False, "empreinte": s2.empreinte})
        return httpx.Response(500)

    sortie = corpus.appliquer(_cible(horloge, gestionnaire), s2, publier=True)
    assert sortie == {"assistant": "e2e-camp-sejour-s2", "avant": "conforme", "ecrit": False, "publie": {"version": 3, "nouvelle": False}}
    assert ("PUT", "/api/assistants/e2e-camp-sejour-s2/fiche.yaml") not in appels


def test_appliquer_remplace_une_fiche_absente_ou_differente(horloge, variantes):
    s1 = variantes[1]
    envoyes = []

    def gestionnaire(req):
        if req.method == "GET":
            return httpx.Response(404)
        envoyes.append(req.content.decode())
        return httpx.Response(200, json={"empreinte": s1.empreinte, "avertissements": []})

    sortie = corpus.appliquer(_cible(horloge, gestionnaire), s1)
    assert sortie["avant"] == "absent" and sortie["ecrit"] and sortie["publie"] is None
    assert fiche_yaml.charger(envoyes[0]).assistant == "e2e-camp-sejour-s1"


def test_la_cli_resoudre_ne_touche_pas_le_reseau(correspondance, capsys):
    assert corpus.main(["resoudre"]) == 0
    sortie = capsys.readouterr().out
    assert "e2e-camp-sejour-s2" in sortie and "questions : 40" in sortie


def test_la_cli_verifier_signale_une_fiche_differente(correspondance, horloge, variantes, capsys):
    def gestionnaire(req):
        return httpx.Response(200, text=variantes[0].texte())  # la fiche s0 servie pour toutes

    assert corpus.main(["verifier", "--cible", BASE], fabrique_cible=lambda base: _cible(horloge, gestionnaire)) == 1
    assert "s1 : e2e-camp-sejour-s1 · different" in capsys.readouterr().out
