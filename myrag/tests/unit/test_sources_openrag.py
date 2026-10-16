"""Le décodage des sources d'OpenRAG : `extra` chaîne (2.2.1) ou objet (2.3.1), sources sous `chunk`."""

from __future__ import annotations

import json

import pytest

from app.services.sources_openrag import aplatir_source, lire_extra, sources_de

_A_PLAT = {"source_type": "document", "_id": "1", "filename": "a.md", "page": 2, "chunk_url": "https://x/extract/1", "rerank_score": 0.5}
_NICHEE = {"source_type": "document", "chunk": {"_id": "1", "filename": "a.md", "page": 2}, "chunk_url": "https://x/extract/1", "rerank_score": 0.5}
_WEB = {"source_type": "web", "url": "https://exemple.fake-domain.name/", "title": "t", "snippet": "s"}


def test_une_source_nichee_est_aplatie():
    assert aplatir_source(_NICHEE) == _A_PLAT


def test_une_source_a_plat_ou_web_passe_telle_quelle():
    assert aplatir_source(_A_PLAT) is _A_PLAT
    assert aplatir_source(_WEB) is _WEB


def test_le_premier_niveau_l_emporte_sur_chunk():
    assert aplatir_source({"chunk": {"chunk_url": "interne", "page": 1}, "chunk_url": "haut"}) == {"chunk_url": "haut", "page": 1}


@pytest.mark.parametrize("s", [None, "texte", 3, [], {"chunk": None}, {"chunk": "x"}])
def test_ce_qui_n_est_pas_une_source_nichee_ne_bouge_pas(s):
    assert aplatir_source(s) == s


@pytest.mark.parametrize("extra", [json.dumps({"sources": [_A_PLAT, _WEB]}), {"sources": [_NICHEE, _WEB]}], ids=["2.2.1", "2.3.1"])
def test_les_deux_formes_donnent_les_memes_sources(extra):
    assert sources_de(extra) == [_A_PLAT, _WEB]


@pytest.mark.parametrize("extra", [None, "", "{}", {}, "null", "pas du json", "[]", [], 3, '{"sources": null}', {"sources": "x"}])
def test_extra_vide_ou_illisible_rend_aucune_source(extra):
    assert sources_de(extra) == []


def test_lire_extra_rend_les_autres_cles():
    assert lire_extra('{"truncated": true}') == {"truncated": True}
    assert lire_extra({"citations_reported": True}) == {"citations_reported": True}
    assert sources_de({"cited_sources": [_NICHEE]}, "cited_sources") == [_A_PLAT]
