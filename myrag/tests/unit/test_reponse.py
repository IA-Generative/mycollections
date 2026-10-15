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
