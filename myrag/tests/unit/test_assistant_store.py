"""Le magasin des assistants : brouillon, versions immuables (une ligne par empreinte nouvelle,
sha256 du texte canonique), signature personne OU robot, journal des plans sans colonne de
contenu, purge du miroir."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import os
import sqlite3

import pytest

from app.harnais.contrat import FicheAssistant, canonique, empreinte
from app.services import assistant_store as store
from tests.unit.test_harnais_contrat import FICHE_SEJOUR


def _sql(requete: str, *params):
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        return con.execute(requete, params).fetchall()
    finally:
        con.close()


@pytest.fixture
def ident(ident_assistant):
    return ident_assistant


def _fiche(ident: str, **modifs) -> FicheAssistant:
    d = copy.deepcopy(FICHE_SEJOUR)
    d["assistant"] = ident
    d.update(modifs)
    return FicheAssistant.model_validate(d)


def test_brouillon_puis_versions(client, ident):
    fiche = _fiche(ident)
    a = asyncio.run(store.enregistrer_brouillon(fiche, auteur_hash="a" * 32))
    assert a["id"] == ident and a["version_publiee"] is None and len(a["sources"]) == 3
    assert asyncio.run(store.fiche_brouillon(ident)) == fiche
    assert asyncio.run(store.lire(ident))["fiche"]["consignes"][1]["id"] == "pays-a-accord"

    v1 = asyncio.run(store.publier(ident, auteur_hash="a" * 32))
    assert v1 == {"assistant": ident, "version": 1, "empreinte": empreinte(canonique(fiche)), "nouvelle": True}
    # Republier le même brouillon ne fait pas de version.
    assert asyncio.run(store.publier(ident, auteur_hash="b" * 32))["nouvelle"] is False
    assert len(asyncio.run(store.versions(ident))) == 1
    # Changer les canaux ne fait pas de version non plus ; changer le contenu, si.
    asyncio.run(store.enregistrer_brouillon(_fiche(ident, publication={"api": True})))
    assert asyncio.run(store.publier(ident, auteur_hash="a" * 32))["version"] == 1
    asyncio.run(store.enregistrer_brouillon(_fiche(ident, description="Autre description", publication={"api": True})))
    v2 = asyncio.run(store.publier(ident, auteur_hash="a" * 32))
    assert v2["version"] == 2 and v2["nouvelle"] is True
    numero, publiee = asyncio.run(store.version_publiee(ident))
    assert numero == 2 and publiee.description == "Autre description"
    assert publiee.publication.api is True and publiee.publication.socle is False, "les canaux sont ceux du brouillon, hors de la version"
    # Chaque version : son texte canonique a bien l'empreinte enregistrée ; les lignes sont immuables.
    for emp, contenu in _sql("SELECT empreinte, contenu_json FROM assistant_versions WHERE assistant_id = ?", ident):
        assert hashlib.sha256(contenu.encode("utf-8")).hexdigest() == emp
    assert [r[0] for r in _sql("SELECT numero FROM assistant_versions WHERE assistant_id = ? ORDER BY numero", ident)] == [1, 2]
    types = [r[0] for r in _sql("SELECT type FROM evenement WHERE objet_type = 'assistant' AND objet_id = ? ORDER BY cree_le", ident)]
    assert types == ["assistant.publie", "assistant.publie"]


def test_une_publication_est_signee_d_une_personne_ou_d_un_robot(client, ident):
    asyncio.run(store.enregistrer_brouillon(_fiche(ident)))
    with pytest.raises(ValueError):
        asyncio.run(store.publier(ident))
    with pytest.raises(ValueError):
        asyncio.run(store.publier(ident, auteur_hash="a" * 32, robot="banc"))
    assert asyncio.run(store.publier(ident, robot="banc"))["version"] == 1
    with pytest.raises(store.Introuvable):
        asyncio.run(store.publier("inconnu-xyz", robot="banc"))


def test_lister_sans_les_archives(client, ident):
    asyncio.run(store.enregistrer_brouillon(_fiche(ident)))
    assert ident in {a["id"] for a in asyncio.run(store.lister())}
    _sql_con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    _sql_con.execute("UPDATE assistants SET archive_le = CURRENT_TIMESTAMP WHERE id = ?", (ident,))
    _sql_con.commit()
    _sql_con.close()
    assert ident not in {a["id"] for a in asyncio.run(store.lister())}
    assert ident in {a["id"] for a in asyncio.run(store.lister(archives=True))}


def test_le_journal_des_plans_n_a_aucune_colonne_de_contenu(client):
    colonnes = {r[1] for r in _sql("PRAGMA table_info(plans_journal)")}
    assert {
        "assistant_id",
        "version",
        "empreinte",
        "canal",
        "planificateur",
        "consigne",
        "score_consigne",
        "reponse_fiable",
        "etapes_json",
        "duree_ms",
        "auteur_hash",
        "robot",
    } <= colonnes
    suspectes = {c for c in colonnes if any(m in c for m in ("question", "texte", "contenu", "reponse", "passage_", "extrait"))} - {"reponse_fiable"}
    assert not suspectes, suspectes


def test_deriver_identifiant():
    assert store.deriver_identifiant("codes-natinf") == "codes-natinf"
    assert store.deriver_identifiant("Mon Corpus_2024") == "mon-corpus_2024"
    assert store.deriver_identifiant("-ab-") == "ab-assistant"
    assert store.deriver_identifiant("") == "assistant"
    assert len(store.deriver_identifiant("x" * 100)) == 64
