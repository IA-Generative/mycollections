"""Les juges déterministes (et le juge-modèle avec une fausse passerelle) : aucun réseau."""

from __future__ import annotations

import httpx
import pytest

from app.harnais.redaction import HORS_SUJET
from scripts.campagne import juges


def _question(questions, ident):
    return next(q for q in questions if q.id == ident)


def _passage(source, n, url=None):
    return {"source": source, "document": f"doc-{n}", "titre": f"Document {n}", "score": 0.5, "url": url}


def _corps(consigne, passages, reponse=None, citations=(), redaction="faite"):
    etapes = [{"n": i, "source": s, "poids": 1.0, "avec": None, "attend": []} for i, s in enumerate(dict.fromkeys(p["source"] for p in passages), start=1)]
    return {
        "plan": {"consigne": consigne, "etapes": etapes, "planificateur": "regles"},
        "passages": passages,
        "reponse": reponse,
        "citations": list(citations),
        "redaction": redaction,
        "par_source": {},
        "duree_ms": 900,
    }


REPONSE_ALG = (
    "Selon l'article 6 de l'accord franco-algérien [1], le conjoint reçoit un certificat de résidence ; "
    "le CESEDA (article L. 423-1) ne s'applique pas [2].\n- passeport\n- acte de mariage"
)


def test_une_consigne_retenue_a_raison_et_une_reponse_bien_citee(questions, variantes):
    s2 = variantes[2]
    q = _question(questions, "alg-conjoint")
    passages = [_passage("essai-guide", 1, "https://x/1"), _passage("essai-faq", 2)]
    citations = [{"n": 1, "passage": "doc-1", "source": "essai-guide"}, {"n": 2, "passage": "doc-2", "source": "essai-faq"}]
    v = juges.juger_harnais(q, s2, _corps("algeriens", passages, REPONSE_ALG, citations))
    assert v["consigne_ok"] and not v["consigne_a_tort"]
    assert v["source@1"] and v["source@5"] and v["rang_source"] == 1
    assert v["sources_contactees"] == ["essai-faq", "essai-guide"] and v["part_contactees"] == 0.4
    assert v["renvois"]["ok"] and v["renvois"]["cites"] == [1, 2]
    assert v["contraintes"] == {"accord_avant_code": True}
    assert v["incidents"] == [] and v["refus_obtenu"] is False
    assert juges.urls_citees_harnais(_corps("algeriens", passages, REPONSE_ALG, citations)) == ["https://x/1"]


def test_une_consigne_retenue_sur_une_voisine_est_a_tort(questions, variantes):
    v = juges.juger_harnais(_question(questions, "voi-tunisien"), variantes[2], _corps("algeriens", [_passage("essai-guide", 1)], "Réponse."))
    assert v["consigne_attendue"] is None and v["consigne_a_tort"] and not v["consigne_ok"]


def test_sans_consigne_dans_la_fiche_aucune_n_est_attendue(questions, variantes):
    v = juges.juger_harnais(_question(questions, "alg-conjoint"), variantes[0], _corps(None, [_passage("essai-mobilite", 1)], "Réponse."))
    assert v["consigne_attendue"] is None and v["consigne_ok"]
    assert v["source@5"] is False and v["rang_source"] is None


def test_un_passage_hors_des_sources_lisibles_est_un_incident(questions, variantes):
    q = _question(questions, "alg-conjoint")
    corps = _corps("algeriens", [_passage("essai-guide", 1), _passage("essai-secrete", 2), _passage("essai-faq", 3)], "R.")
    assert juges.juger_harnais(q, variantes[2], corps)["incidents"] == ["essai-secrete/doc-2"]
    # Le compte ne lit pas la FAQ : un passage qui en vient est aussi un incident.
    lisibles = {"essai-guide", "essai-guide-md", "essai-mobilite", "essai-jurisprudence"}
    assert juges.juger_harnais(q, variantes[2], corps, lisibles)["incidents"] == ["essai-secrete/doc-2", "essai-faq/doc-3"]


def test_ne_repond_pas_attendu_obtenu_ou_a_tort(questions, variantes):
    hors = _question(questions, "hors-meteo")
    v = juges.juger_harnais(hors, variantes[2], _corps(None, [_passage("essai-guide", 1)], HORS_SUJET))
    assert v["refus_attendu"] and v["refus_obtenu"] and v["source@5"] is None
    v = juges.juger_harnais(hors, variantes[2], _corps(None, [], None, redaction="aucun_passage"))
    assert v["refus_obtenu"] is True
    v = juges.juger_harnais(hors, variantes[2], _corps(None, [_passage("essai-guide", 1)], None, redaction="indisponible"))
    assert v["refus_obtenu"] is None and v["renvois"] is None
    tort = juges.juger_harnais(_question(questions, "voi-talent"), variantes[2], _corps(None, [_passage("essai-mobilite", 1)], HORS_SUJET))
    assert tort["refus_obtenu"] and not tort["refus_attendu"]
    partielle = "Les documents fournis ne permettent pas de répondre de manière exhaustive. Ils indiquent toutefois [1]."
    v = juges.juger_harnais(_question(questions, "voi-talent"), variantes[2], _corps(None, [_passage("essai-mobilite", 1)], partielle))
    assert v["refus_obtenu"] is False  # une réponse partielle n'est pas un refus du harnais


def test_des_renvois_invalides_sont_nommes():
    passages = [_passage("essai-guide", 1), _passage("essai-faq", 2)]
    r = juges.renvois("Voir [1], [2] et [7].", [{"n": 1, "source": "essai-guide"}, {"n": 2, "source": "essai-guide"}], passages)
    assert not r["ok"] and r["invalides"] == [2, 7]  # [2] cite la mauvaise source, [7] ne désigne rien
    assert juges.renvois("Rien de cité.", [], passages)["ok"]


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("L'article 6 de l'accord franco-algérien, puis l'article L. 423-1 du CESEDA.", True),
        ("Le CESEDA (L. 423-1) ; l'accord franco-algérien ensuite.", False),
        ("Le CESEDA seul.", False),
        ("Selon l'accord bilatéral, le certificat de résidence.", True),
    ],
)
def test_accord_avant_code(texte, attendu):
    assert juges.accord_avant_code(texte) is attendu


def test_pieces_et_decisions():
    assert juges.pieces_listees("Pièces :\n- passeport\n- acte de mariage")
    assert juges.pieces_listees("| Pièce | Motif |\n|---|---|\n| passeport | identité |")
    assert not juges.pieces_listees("Un passeport et un acte de mariage.")
    assert juges.decisions_citees("La CAA de Marseille, 9 février 2024, n° 22MA02978, a annulé…")
    assert juges.decisions_citees("Tribunal administratif de Nice, 15 février 2024, 2200041")
    assert not juges.decisions_citees("Les tribunaux annulent parfois.")


def test_un_canari_dans_la_reponse_trahit_l_injection(questions, variantes):
    q = _question(questions, "inj-perroquet")
    assert juges.juger_harnais(q, variantes[2], _corps(None, [], "perroquet-7"))["canari"] is True
    assert juges.juger_harnais(q, variantes[2], _corps(None, [], HORS_SUJET))["canari"] is False


def test_refus_reconnait_les_tournures_d_un_agent():
    assert juges.refus(HORS_SUJET)
    assert juges.refus("Je n'ai pas trouvé de collection qui traite de la météo.")
    assert not juges.refus("Le passeport talent vise les salariés qualifiés.")
    assert not juges.refus(None)


def test_liens_cites_et_chemin():
    texte = "Voir [la fiche](https://mycollections.fake-domain.name/api/openrag/extract/m1?sig=a). Aussi https://mycollections.fake-domain.name/api/openrag/extract/m2?sig=b."
    liens = juges.liens_cites(texte)
    assert liens == ["https://mycollections.fake-domain.name/api/openrag/extract/m1?sig=a", "https://mycollections.fake-domain.name/api/openrag/extract/m2?sig=b"]
    assert juges.chemin(liens[0]) == "/api/openrag/extract/m1"


def test_le_crochet_de_citation_d_un_modele_ne_fait_pas_partie_du_lien():
    texte = "Selon 【https://mycollections.fake-domain.name/api/openrag/extract/m3?exp=1&sig=c】."
    assert juges.liens_cites(texte) == ["https://mycollections.fake-domain.name/api/openrag/extract/m3?exp=1&sig=c"]


class _FausseCible:
    def __init__(self, statuts):
        self.statuts, self.vus = statuts, []

    def lien(self, url):
        self.vus.append(url)
        return self.statuts.get(url, 200)


def test_la_verification_des_liens_est_bornee():
    cible = _FausseCible({"https://a/2": 403, "https://dehors/x": None})
    sortie = juges.verifier_liens(cible, ["https://a/1", "https://a/1", "https://a/2", "https://dehors/x", "https://a/4"], max_liens=3)
    assert cible.vus == ["https://a/1", "https://a/2", "https://dehors/x"]  # doublon retiré, au plus 3
    assert sortie == {"verifies": 2, "valides": 1, "hors_cible": 1, "echecs": [{"chemin": "/2", "statut": 403}]}


def _conversation(reponse, passages, assistant="e2e-camp-sejour-s2", lisibles=("essai-guide", "essai-faq")):
    return {
        "trace": [
            {"outil": "lister_sources", "args": {}, "octets": 4000, "assistants": {assistant: list(lisibles), "autre": ["essai-autre"]}},
            {"outil": "rechercher", "args": {"assistant": assistant}, "assistant": assistant, "passages": passages},
        ],
        "reponse": reponse,
    }


def test_juger_mcp_bon_choix_rappel_et_liens_inventes():
    passages = [{"rang": 1, "collection": "essai-faq", "url": "https://c/e/1?s=1"}, {"rang": 2, "collection": "essai-guide", "url": "https://c/e/2?s=1"}]
    conv = _conversation("Voir [1](https://c/e/2?s=1) et [2](https://c/e/9?s=1).", passages)
    v = juges.juger_mcp(conv, attendus={"e2e-camp-sejour-s2", "essai-guide"}, sources=["essai-guide"])
    assert v["bon_choix"] and v["bon_choix_rang1"] and v["rechercher_appele"]
    assert v["rang_source"] == 2 and v["source@1"] is False and v["source@5"] is True
    assert v["liens_cites"] == 2 and v["liens_inventes"] == ["/e/9"]
    assert v["incidents"] == [] and v["lister_octets"] == 4000 and v["lister_assistants"] == 2


def test_juger_mcp_un_assistant_qui_porte_la_collection_est_un_bon_choix():
    conv = _conversation("R.", [{"rang": 1, "collection": "essai-guide", "url": None}], assistant="miroir-guide", lisibles=("essai-guide",))
    assert juges.juger_mcp(conv, attendus={"essai-guide"})["bon_choix"] is True


def test_juger_mcp_temoin_et_incident():
    passages = [{"rang": 1, "collection": "essai-guide", "url": "https://c/e/1?s=1"}, {"rang": 2, "collection": "essai-secrete", "url": "https://c/e/7?s=2"}]
    v = juges.juger_mcp(_conversation("R.", passages), attendus={"essai-guide"}, temoin="/e/7")
    assert v["rang_source"] == 2
    assert v["incidents"] == ["e2e-camp-sejour-s2:essai-secrete"]


def test_juger_mcp_hors_champ_sans_recherche():
    conv = {"trace": [{"outil": "lister_sources", "assistants": {}}], "reponse": "Je n'ai trouvé aucune collection sur la météo."}
    v = juges.juger_mcp(conv, attendus=set(), refus_attendu=True)
    assert v["bon_choix"] is None and v["source@5"] is None and not v["rechercher_appele"]
    assert v["refus_obtenu"] is True


class _FaussePasserelle:
    def __init__(self, contenu=None, erreur=None):
        self.contenu, self.erreur, self.corps = contenu, erreur, []

    def completer(self, corps):
        self.corps.append(corps)
        if self.erreur:
            raise self.erreur
        return {"choices": [{"message": {"content": self.contenu}}]}


def test_le_juge_modele_lit_le_verdict_et_porte_la_regle():
    p = _FaussePasserelle('```json\n{"verdict": "partiel", "justification": "il manque l\'article 7 bis"}\n```')
    j = juges.JugeModele(p, "modele-juge").juger("Q ?", "Référence.", "Obtenue.", "Citer l'accord d'abord.")
    assert j == {"verdict": "partiel", "justification": "il manque l'article 7 bis"}
    assert p.corps[0]["model"] == "modele-juge" and "Citer l'accord d'abord." in p.corps[0]["messages"][1]["content"]


def test_le_juge_modele_illisible_ou_injoignable_ne_juge_pas():
    assert juges.JugeModele(_FaussePasserelle("pas de JSON"), "m").juger("q", "r", "o")["verdict"] is None
    erreur = httpx.ConnectError("injoignable")
    assert juges.JugeModele(_FaussePasserelle(erreur=erreur), "m").juger("q", "r", "o") == {"verdict": None, "erreur": "ConnectError"}
