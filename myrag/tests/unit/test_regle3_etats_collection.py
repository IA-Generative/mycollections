"""Règle 3 — amorcee → en_controle → publiee_groupe → publiee_tous, sans saut ;
non publiée à tous = jamais servie hors du groupe, réponses avec la mention."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.etats import (
    MENTION_VERIFICATION, RefusTransition, grille_complete, mention_verification, transition_collection,
)
from tests.conftest import SUPERADMIN, personne

GRILLE_OK = {"source_licence": "LO 2.0", "donnees_perso": "aucune", "fraicheur": "mensuelle", "relecture_n": 1}
GARANT = personne("garant")


class TestLaMachineEnPur:
    def test_l_ordre_est_strict(self):
        assert transition_collection("amorcee", "en_controle", None) == "en_controle"
        with pytest.raises(RefusTransition) as e:
            transition_collection("amorcee", "publiee_groupe", None)
        assert e.value.code == 409

    def test_publier_a_tous_exige_la_grille(self):
        with pytest.raises(RefusTransition) as e:
            transition_collection("publiee_groupe", "publiee_tous", {"source_licence": "LO"})
        assert e.value.code == 422
        assert transition_collection("publiee_groupe", "publiee_tous", GRILLE_OK) == "publiee_tous"

    def test_le_retour_au_groupe_est_permis(self):
        assert transition_collection("publiee_tous", "publiee_groupe", None) == "publiee_groupe"

    def test_le_forcage_saute_tout(self):
        assert transition_collection("amorcee", "publiee_tous", None, forcer=True) == "publiee_tous"
        with pytest.raises(RefusTransition):
            transition_collection("amorcee", "amorcee", None, forcer=True)

    def test_la_mention(self):
        assert mention_verification("en_controle") == MENTION_VERIFICATION
        assert mention_verification("publiee_tous") is None
        assert not grille_complete({**GRILLE_OK, "relecture_n": 0})


def _avancer(client, en_tant_que, nom, cible, qui=GARANT, **corps):
    en_tant_que(qui)
    return client.post(f"/api/collections/{nom}/etat", json={"cible": cible, **corps})


class TestSurLesRoutes:
    def test_une_collection_nait_amorcee_et_son_createur_est_garant(self, client, en_tant_que, creer_collection, nom):
        creer_collection(nom, GARANT)
        r = client.get(f"/api/collections/{nom}/etat")
        assert r.status_code == 200
        assert r.json()["etat"] == "amorcee" and r.json()["je_suis_garant"] is True
        assert r.json()["mention"] == MENTION_VERIFICATION

    def test_le_garant_ne_saute_pas_d_etape(self, client, en_tant_que, creer_collection, nom):
        creer_collection(nom, GARANT)
        assert _avancer(client, en_tant_que, nom, "publiee_groupe").status_code == 409
        assert _avancer(client, en_tant_que, nom, "en_controle").status_code == 200

    def test_un_lecteur_ne_change_pas_l_etat(self, client, en_tant_que, creer_collection, nom):
        creer_collection(nom, GARANT)
        assert _avancer(client, en_tant_que, nom, "en_controle", qui=personne("lecteur")).status_code == 403

    def test_publier_a_tous_sans_grille_est_refuse(self, client, en_tant_que, creer_collection, nom):
        creer_collection(nom, GARANT)
        _avancer(client, en_tant_que, nom, "en_controle")
        _avancer(client, en_tant_que, nom, "publiee_groupe")
        assert _avancer(client, en_tant_que, nom, "publiee_tous").status_code == 422
        client.put(f"/api/collections/{nom}/grille", json={"source_licence": "LO 2.0", "donnees_perso": "aucune", "fraicheur": "mensuelle"})
        assert _avancer(client, en_tant_que, nom, "publiee_tous").status_code == 422, "il manque la relecture"
        en_tant_que(personne("relecteur"))
        assert client.post(f"/api/collections/{nom}/grille/relire").status_code == 200
        assert _avancer(client, en_tant_que, nom, "publiee_tous").status_code == 200

    def test_un_superadmin_force_le_cycle_et_ca_se_voit(self, client, en_tant_que, creer_collection, nom):
        creer_collection(nom, GARANT)
        assert _avancer(client, en_tant_que, nom, "publiee_tous", qui=SUPERADMIN).status_code == 409, "sans forcer, même l'admin suit l'ordre"
        r = _avancer(client, en_tant_que, nom, "publiee_tous", qui=SUPERADMIN, forcer=True, motif="démo")
        assert r.status_code == 200 and r.json()["etat"] == "publiee_tous"
        assert _avancer(client, en_tant_que, nom, "amorcee", forcer=True).status_code == 403, "le garant ne force pas"
        journal = client.get(f"/api/collections/{nom}/journal").json()["evenements"]
        forces = [e for e in journal if e["type"] == "collection.etat" and e["detail"].get("force")]
        assert forces and forces[0]["detail"]["motif"] == "démo"

    def test_publier_tout_le_monde_est_refuse_avant_publiee_tous(self, client, en_tant_que, creer_collection, nom):
        creer_collection(nom, GARANT)
        _avancer(client, en_tant_que, nom, "en_controle")
        r = client.post(f"/api/collections/{nom}/publish", json={"visibility": "all"})
        assert r.status_code == 422 and "vérification" in r.text
        assert client.post(f"/api/collections/{nom}/publish", json={"visibility": "all", "state": "draft"}).status_code == 200

    def test_la_description_owui_porte_la_mention_au_groupe(self, client, en_tant_que, creer_collection, nom):
        creer_collection(nom, GARANT)
        _avancer(client, en_tant_que, nom, "en_controle")
        _avancer(client, en_tant_que, nom, "publiee_groupe")
        with patch("app.services.owui_client.OwuiClient") as cls:
            cls.return_value.upsert_model = AsyncMock(return_value={"id": f"openrag-{nom}"})
            r = client.post(f"/api/collections/{nom}/publish", json={"visibility": "group", "visibility_groups": ["/g/x"], "alias_description": "Décisions"})
            assert r.status_code == 200, r.text
            appel = cls.return_value.upsert_model.call_args.kwargs
        assert appel["description"].startswith("⚠ " + MENTION_VERIFICATION)
        assert appel["access_grants"] and all(g["principal_type"] == "group" for g in appel["access_grants"]), "au groupe, jamais user/*"

    def test_le_bac_a_sable_porte_la_mention(self, client, en_tant_que, creer_collection, nom):
        creer_collection(nom, GARANT)
        with patch("app.routers.playground.OpenRAGClient") as cls:
            cls.return_value.health_check = AsyncMock(return_value=True)
            cls.return_value.chat = AsyncMock(return_value={"choices": [{"message": {"content": "Réponse."}}], "extra": ""})
            r = client.post(f"/api/playground/{nom}/chat", json={"question": "?"})
        assert r.status_code == 200, r.text
        assert r.json()["mention"] == MENTION_VERIFICATION
        assert r.json()["response"].startswith("⚠ " + MENTION_VERIFICATION)

    def test_les_collections_anterieures_recoivent_un_etat(self, client, purger):
        """Rétro-remplissage : publiée « tout le monde » ⇒ publiee_tous ; sinon publiee_groupe."""
        import asyncio
        import os
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from app.database import _retro_remplir_etat_collab
        from app.models.db import Collection, Publication

        async def _jouer():
            # Un moteur propre au test : celui de l'application vit sur une autre boucle.
            moteur = create_async_engine(os.environ["DATABASE_URL"])
            async with async_sessionmaker(moteur)() as session:
                await session.execute(text("DELETE FROM collections WHERE name IN ('retro-tous','retro-groupe')"))
                await session.execute(text("DELETE FROM publications WHERE collection_name IN ('retro-tous','retro-groupe')"))
                # Des lignes d'AVANT la colonne : etat_collab à NULL, exprès.
                session.add(Collection(name="retro-tous", etat_collab=None))
                session.add(Collection(name="retro-groupe", etat_collab=None))
                session.add(Publication(collection_name="retro-tous", state="published", visibility="all"))
                await session.commit()
            async with moteur.begin() as conn:
                # Le défaut Python du modèle a posé « amorcee » : on remet NULL, comme
                # une base d'avant la colonne.
                await conn.execute(text("UPDATE collections SET etat_collab = NULL WHERE name LIKE 'retro-%'"))
                await _retro_remplir_etat_collab(conn)
                lignes = await conn.execute(text("SELECT name, etat_collab FROM collections WHERE name LIKE 'retro-%'"))
                resultat = dict(lignes.all())
            await moteur.dispose()
            return resultat
        etats = asyncio.run(_jouer())
        assert etats == {"retro-tous": "publiee_tous", "retro-groupe": "publiee_groupe"}
        purger("retro-tous"); purger("retro-groupe")
