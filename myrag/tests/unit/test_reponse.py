"""Le service qui répond à une question, sans HTTP : replis signalés, mention rendue à part."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.reponse import ErreurReponse, repondre


def _client(chat_reponses, recherche=None, fichiers=None):
    c = MagicMock()
    c.chat = AsyncMock(side_effect=chat_reponses)
    c.search = AsyncMock(return_value={"documents": recherche or []})
    c.list_files = AsyncMock(return_value=fichiers or [])
    return c


def _chat(texte, sources=None):
    import json

    return {"choices": [{"message": {"content": texte}}], "extra": json.dumps({"sources": sources or []})}


def _repondre(client, mention=None):
    with (
        patch("app.services.collectif_store.fiche", new=AsyncMock(return_value={"etat_collab": "publiee_tous"})),
        patch("app.services.etats.mention_verification", return_value=mention),
        patch("app.services.collection_store.get_system_prompt", new=AsyncMock(return_value="")),
    ):
        return asyncio.run(repondre("x", "Quel délai ?", client=client))


def test_rag_avec_sources():
    r = _repondre(_client([_chat("Deux mois.", [{"filename": "a.md", "content": "…"}])]))
    assert r.contenu == "Deux mois." and r.repli == "aucun" and r.source_names == ["a.md"] and not r.fallback_used


def test_repli_recherche_quand_le_rag_ne_cite_rien():
    c = _client([_chat(""), _chat("D'après le document, deux mois.")], recherche=[{"content": "Le délai est de deux mois.", "metadata": {"filename": "b.md"}}])
    r = _repondre(c)
    assert r.repli == "recherche" and "deux mois" in r.contenu and r.source_names == ["b.md"]


def test_repli_noms_de_fichiers_en_dernier_recours():
    c = _client([_chat(""), _chat("La collection parle de titres de séjour.")], fichiers=[{"filename": "titre.md", "file_size": 10}])
    r = _repondre(c)
    assert r.repli == "fichiers" and r.fallback_used


def test_la_mention_est_rendue_a_part():
    r = _repondre(_client([_chat("Deux mois.", [{"filename": "a.md"}])]), mention="en cours de vérification")
    assert r.mention == "en cours de vérification" and not r.contenu.startswith("⚠")


def test_openrag_en_panne():
    c = _client([RuntimeError("connexion refusée")])
    with pytest.raises(ErreurReponse):
        _repondre(c)


def test_debit_partage_suit_le_reglage(monkeypatch):
    from app.config import settings
    from app.services import debit

    monkeypatch.setattr(settings, "generation_appels_par_minute", 7)
    a = debit.partage()
    assert a is debit.partage() and a.par_minute == 7
    monkeypatch.setattr(settings, "generation_appels_par_minute", 9)
    assert debit.partage().par_minute == 9


# --- OpenRAG 2.2.1 et 2.3.1 : la forme des sources -----------------------------------------
#
# 2.2.1 : `extra` est une CHAÎNE JSON, les métadonnées d'une source documentaire sont au premier
# niveau. 2.3.1 : `extra` est un OBJET, les métadonnées passent sous `chunk` (`_id` compris) ;
# restent au premier niveau `source_type`, `chunk_url`, `file_url` (seulement si le passage a un
# champ `source`) et les scores. Les sources web ne changent pas. Une même réponse lue dans les
# deux formes doit donner EXACTEMENT les mêmes sources, noms, libellés et liens.

import copy  # noqa: E402
import json  # noqa: E402
from types import SimpleNamespace  # noqa: E402

_HAUT_23 = ("source_type", "chunk_url", "file_url", "vector_score", "rerank_score", "combined_score")

_DOC_A = {
    "source_type": "document",
    "_id": "4567",
    "file_id": "f-12",
    "partition": "ceseda-legifrance",
    "page": 3,
    "filename": "CESEDA_L423_1.md",
    "original_filename": "CESEDA-L423-1.md",
    "title": "CESEDA, art. L. 423-1",
    "url": "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000000000001",
    "source": "/app/data/CESEDA_L423_1.md",
    "article_num": "L423-1",
    "content": "# CESEDA\n## Article L. 423-1\nL'étranger marié avec un ressortissant français…",
    "chunk_url": "https://api.openrag.fake-domain.name/extract/4567",
    "file_url": "https://api.openrag.fake-domain.name/static/4567",
    "rerank_score": 0.81,
}
#: Un second passage du même fichier : une seule puce, un seul nom.
_DOC_A_BIS = {
    **_DOC_A,
    "_id": "4568",
    "page": 4,
    "chunk_url": "https://api.openrag.fake-domain.name/extract/4568",
    "file_url": "https://api.openrag.fake-domain.name/static/4568",
    "rerank_score": 0.52,
}
#: Une source « nue » : ni page, ni titre, ni url, ni `file_url` (pas de champ `source`), ni score.
_DOC_B = {
    "source_type": "document",
    "_id": "7001",
    "file_id": "f-13",
    "partition": "ceseda-legifrance",
    "filename": "faq.docx",
    "original_filename": "Foire aux questions.docx",
    "chunk_url": "https://api.openrag.fake-domain.name/extract/7001",
}
_WEB = {"source_type": "web", "url": "https://www.service-public.fr/particuliers/vosdroits/F2209", "title": "Carte de séjour", "snippet": "…"}


def _niche(s):
    """Une source à plat (2.2.1) → la même en forme 2.3.1 (métadonnées sous `chunk`)."""
    if s.get("source_type") == "web":
        return copy.deepcopy(s)
    haut = {k: s[k] for k in _HAUT_23 if k in s}
    return {"source_type": s.get("source_type", "document"), "chunk": {k: v for k, v in s.items() if k not in _HAUT_23}, **haut}


def _chat_221(texte, sources, **extra):
    return {"choices": [{"message": {"content": texte}}], "extra": json.dumps({"sources": copy.deepcopy(sources), "citations_reported": True, **extra})}


def _chat_231(texte, sources, **extra):
    return {"choices": [{"message": {"content": texte}}], "extra": {"sources": [_niche(s) for s in sources], "citations_reported": True, **extra}}


def _repondre_fige(client):
    """`repondre` avec une horloge figée : les liens signés portent la même échéance d'un appel à l'autre."""
    with patch("app.services.liens.time", SimpleNamespace(time=lambda: 1_800_000_000)):
        return _repondre(client)


_CLES_VUES = ("_id", "original_filename", "filename", "page", "title", "url", "libelle", "titre_section", "titre_document")
_CLES_VUES += ("chunk_url", "file_url", "source_type", "rerank_score")


def _vu(r):
    """Ce que l'application rend et ce que le front en tire : les sources (libellés, pages, liens
    signés), les noms, et les puces dédoublonnées comme `ChatMessage.vue`."""
    puces = []
    for s in r.sources:
        k = s.get("original_filename") or s.get("filename") or json.dumps(s)[:40]
        if k not in puces:
            puces.append(k)
    return {
        "contenu": r.contenu,
        "repli": r.repli,
        "noms": r.source_names,
        "puces": puces,
        "sources": [{k: s.get(k) for k in _CLES_VUES} for s in r.sources],
    }


_TOUTES = [_DOC_A, _DOC_A_BIS, _DOC_B, _WEB]


def test_221_sources_a_plat_ce_que_l_application_rend_aujourd_hui():
    """Non-régression : la forme 2.2.1 telle qu'elle est lue aujourd'hui."""
    v = _vu(_repondre_fige(_client([_chat_221("Deux mois [1].", _TOUTES)])))
    assert v["repli"] == "aucun" and v["contenu"] == "Deux mois [1]."
    assert v["noms"] == ["CESEDA-L423-1.md", "Foire aux questions.docx"]
    assert v["puces"][:2] == ["CESEDA-L423-1.md", "Foire aux questions.docx"] and len(v["puces"]) == 3  # + la source web
    a, a_bis, b, web = v["sources"]
    assert a["_id"] == "4567" and a["page"] == 3 and a["title"] == "CESEDA, art. L. 423-1" and a["libelle"] == "Article L. 423-1"
    assert a["chunk_url"].startswith("/api/openrag/extract/4567?exp=") and a["file_url"].startswith("/api/openrag/static/4567?exp=")
    assert a_bis["page"] == 4 and a_bis["chunk_url"].startswith("/api/openrag/extract/4568?")
    assert b["page"] is None and b["title"] is None and b["file_url"] is None and b["libelle"] is None
    assert b["chunk_url"].startswith("/api/openrag/extract/7001?")
    assert web["source_type"] == "web" and web["url"] == _WEB["url"] and web["chunk_url"] is None


def test_231_sources_sous_chunk_meme_resultat_qu_en_221():
    """2.3.1 : `extra` objet, métadonnées sous `chunk` → exactement ce que rend la 2.2.1."""
    v_221 = _vu(_repondre_fige(_client([_chat_221("Deux mois [1].", _TOUTES)])))
    v_231 = _vu(_repondre_fige(_client([_chat_231("Deux mois [1].", _TOUTES)])))
    assert v_231 == v_221


@pytest.mark.parametrize("forme", ["2.2.1", "2.3.1"])
def test_une_puce_par_fichier_dans_les_deux_formes(forme):
    """La fusion observée en 2.3 : toutes les puces en une seule. Ici, une par fichier."""
    chat = _chat_221 if forme == "2.2.1" else _chat_231
    v = _vu(_repondre_fige(_client([chat("Réponse.", [_DOC_A, _DOC_B])])))
    assert v["puces"] == ["CESEDA-L423-1.md", "Foire aux questions.docx"]
    assert v["noms"] == ["CESEDA-L423-1.md", "Foire aux questions.docx"]


@pytest.mark.parametrize("forme", ["2.2.1", "2.3.1"])
def test_source_nue_sans_file_url_ni_score(forme):
    chat = _chat_221 if forme == "2.2.1" else _chat_231
    r = _repondre_fige(_client([chat("Réponse.", [_DOC_B])]))
    (s,) = r.sources
    assert r.source_names == ["Foire aux questions.docx"] and "file_url" not in s and "rerank_score" not in s
    assert s["_id"] == "7001" and s["chunk_url"].startswith("/api/openrag/extract/7001?")
    assert "page" not in s and "title" not in s and "url" not in s


@pytest.mark.parametrize("forme", ["2.2.1", "2.3.1"])
def test_sans_chunk_url_le_lien_d_extrait_se_construit_depuis_l_identifiant(forme):
    """Le repli de `signer_les_liens_de_la_source` lit `_id` : en 2.3 il est sous `chunk`."""
    chat = _chat_221 if forme == "2.2.1" else _chat_231
    sans_lien = {k: v for k, v in _DOC_A.items() if k not in ("chunk_url", "file_url")}
    (s,) = _repondre_fige(_client([chat("Réponse.", [sans_lien])])).sources
    assert s["chunk_url"].startswith("/api/openrag/extract/4567?exp=")


@pytest.mark.parametrize("forme", ["2.2.1", "2.3.1"])
def test_liste_mixte_document_et_web(forme):
    chat = _chat_221 if forme == "2.2.1" else _chat_231
    r = _repondre_fige(_client([chat("Réponse.", [_WEB, _DOC_A])]))
    assert [s.get("source_type") for s in r.sources] == ["web", "document"]
    assert r.sources[0]["url"] == _WEB["url"] and "chunk" not in r.sources[0]
    assert r.sources[1]["original_filename"] == "CESEDA-L423-1.md" and "chunk" not in r.sources[1]
    assert r.source_names == ["CESEDA-L423-1.md"]


@pytest.mark.parametrize("forme", ["2.2.1", "2.3.1"])
def test_reponse_tronquee_non_streamee(forme):
    """2.3.1 peut poser `truncated: true` en non streamé : les sources restent lues."""
    chat = _chat_221 if forme == "2.2.1" else _chat_231
    r = _repondre_fige(_client([chat("Deux mo", [_DOC_A], truncated=True)]))
    assert r.contenu == "Deux mo" and r.repli == "aucun" and r.source_names == ["CESEDA-L423-1.md"]


@pytest.mark.parametrize(
    "extra",
    [None, "", "{}", {}, "null", "pas du json", "[]", [], {"sources": None}, '{"sources": null}'],
    ids=["None", "chaine-vide", "chaine-objet-vide", "objet-vide", "chaine-null", "chaine-invalide", "chaine-liste", "liste", "objet-sources-null", "chaine-sources-null"],
)
def test_extra_vide_ou_illisible_aucune_source_comme_aujourd_hui(extra):
    """Pas de sources lisibles → le repli par recherche prend le relais, sans panne."""
    sans_sources = {"choices": [{"message": {"content": ""}}], "extra": extra}
    c = _client([sans_sources, _chat("D'après le document, deux mois.")], recherche=[{"content": "Deux mois.", "metadata": {"filename": "b.md"}}])
    r = _repondre(c)
    assert r.repli == "recherche" and r.source_names == ["b.md"]


def test_extra_absent_aucune_source():
    c = _client([{"choices": [{"message": {"content": ""}}]}, _chat("Rien.")], recherche=[{"content": "x", "metadata": {"filename": "b.md"}}])
    assert _repondre(c).repli == "recherche"
