"""La source Fichiers (docs/fichiers.md) : instances déclarées, plafond de sensibilité, import d'un
dossier de Drive et mise à jour par le moteur partagé avec Résana.

Un faux Drive répond (`_faux_drive`) ; OpenRAG est remplacé. Aucun appel réseau."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers import sources_fichiers, sources_resana
from app.services import fichiers_instances, nommage, sensibilite
from app.services.chunker import Sensitivity
from app.services.connectors.fichiers import ClientFichiers
from tests.conftest import personne
from tests.unit._faux_drive import API, HOTE, JETON, STOCKAGE, Element, FauxDrive

IMPORTEUR = personne("importeur-fichiers")
AUTRE = personne("autre-fichiers")
ENTETE = {"Authorization": f"Bearer {JETON}"}
INSTANCES = [
    {"id": "public", "titre": "Fichiers interministériel", "url": "https://public.fake-domain.name", "sensibilite_max": "public", "zone": "internet"},
    {"id": "beta", "titre": "Mes fichiers (bêta)", "url": API, "hote_public": HOTE, "stockage_url": STOCKAGE, "sensibilite_max": "internal", "zone": "internet, bêta"},
    {"id": "rie", "titre": "Fichiers RIE", "url": "https://rie.fake-domain.name", "sensibilite_max": "restricted", "groupes": ["/g/agents-rie"]},
]
COLLECTION = "fichiers-beta-d1"


def _arbre() -> FauxDrive:
    return FauxDrive().ajouter(
        Element("d1", "Pôle juridique", "folder"),
        Element("d2", "Notes", "folder", parent="d1"),
        Element("d3", "Archives", "folder", parent="d1"),
        Element("f1", "avis-a.md", parent="d2", contenu=b"# Avis A\n\nPremier texte fictif."),
        Element("f2", "avis-b.md", parent="d2", contenu=b"# Avis B\n\nDeuxieme texte fictif."),
        Element("f3", "vieux.md", parent="d3", contenu=b"# Vieux\n\nTexte fictif archive."),
        Element("f4", "racine.md", parent="d1", contenu=b"# Racine\n\nTexte fictif a la racine."),
        Element("autre", "Autre dossier", "folder"),
    )


def _purger(*noms):
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1], timeout=30)
    try:
        from tests.conftest import TABLES_PAR_COLLECTION

        for n in noms:
            for t in TABLES_PAR_COLLECTION:
                con.execute(f"DELETE FROM {t} WHERE collection_name = ?", (n,))
            con.execute("DELETE FROM collections WHERE name = ?", (n,))
        con.commit()
    finally:
        con.close()


@pytest.fixture
def drive(monkeypatch):
    """Les instances déclarées, le faux Drive, la tâche de fond attendue sur place, OpenRAG remplacé."""
    faux = _arbre()
    monkeypatch.setattr(fichiers_instances.settings, "fichiers_instances", json.dumps(INSTANCES))
    monkeypatch.setattr(sources_fichiers, "_fabrique", lambda inst, jeton: ClientFichiers(inst, jeton, transport=faux.transport()))

    async def sur_place(collection, travail):
        await travail

    async def sans_pause(_s):
        return None

    monkeypatch.setattr(sources_resana, "_demarrer", sur_place)
    monkeypatch.setattr(sources_resana, "_pause", sans_pause)
    from app.services.openrag_client import EnvoiDocument

    openrag = MagicMock()
    openrag.delete_partition = AsyncMock()
    openrag.create_partition = AsyncMock()
    openrag.delete_file = AsyncMock()
    openrag.upload_document = AsyncMock(side_effect=lambda partition, nom, contenu, mime, metadata=None, file_id=None: EnvoiDocument(file_id=file_id or nom, task_id=""))
    monkeypatch.setattr(sources_resana.depot, "OpenRAGClient", MagicMock(return_value=openrag))
    faux.openrag, faux.envois = openrag, openrag.upload_document
    _purger(COLLECTION, f"{COLLECTION}-bis")
    yield faux
    _purger(COLLECTION, f"{COLLECTION}-bis")


def _creer(client, **extra):
    corps = {"espace_id": "beta", "dossiers": [{"id": "d1", "chemin": "Pôle juridique"}], "titre": "Notes du pôle juridique", **extra}
    return client.post("/api/sources/fichiers/collections", json=corps, headers=ENTETE)


def _cfg(nom=COLLECTION) -> dict:
    from app.services.collection_store import get_source_config

    return asyncio.run(get_source_config(nom))


# --- Le module de sensibilité -------------------------------------------------------------------


def test_l_echelle_va_du_moins_au_plus_protege():
    assert sensibilite.compatible("public", "internal") and not sensibilite.compatible("personal", "internal")
    assert sensibilite.compatible("restricted", "restricted")
    # Une ancienne valeur se range au plus protecteur.
    assert sensibilite.rang("secret") == sensibilite.rang("restricted")
    assert sensibilite.niveaux_permis("controlled") == ["controlled", "restricted"]


def test_le_plafond_des_destinations_se_lit_prudemment(monkeypatch):
    brut = json.dumps({"chat": "internal", "recherche": "inconnu", "telepathie": "public"})
    assert sensibilite.plafonds_destinations(brut) == {"chat": Sensitivity.INTERNAL}
    assert sensibilite.plafonds_destinations("{pas du json") == {}
    monkeypatch.setattr(fichiers_instances.settings, "destinations_sensibilite_max", brut)
    assert sensibilite.admise("internal", "chat") and not sensibilite.admise("personal", "chat")
    assert sensibilite.admise("restricted", "recherche"), "sans plafond lisible : aucune restriction"
    assert "jusqu'au niveau « Interne »" in sensibilite.refus_destination("personal", "chat")


# --- Les instances -------------------------------------------------------------------------------


def test_les_instances_declarees_et_leurs_fautes(monkeypatch):
    brut = [*INSTANCES, {"id": "beta", "titre": "doublon", "url": API}, {"id": "X!", "titre": "faute", "url": API}, {"id": "sansurl", "titre": "t", "url": "ftp://x"}]
    monkeypatch.setattr(fichiers_instances.settings, "fichiers_instances", json.dumps(brut))
    i = fichiers_instances.instances()
    assert list(i) == ["public", "beta", "rie"] and i["beta"].titre == "Mes fichiers (bêta)"
    assert "url" not in i["beta"].publique() and i["beta"].publique()["hote"] == HOTE
    assert [x.id for x in fichiers_instances.lisibles_par(IMPORTEUR.groups)] == ["public", "beta"]
    assert i["beta"].url_consultation("f1") == f"https://{HOTE}/explorer/items/files/f1"


def test_sans_declaration_drive_url_donne_l_instance_implicite(monkeypatch):
    monkeypatch.setattr(fichiers_instances.settings, "fichiers_instances", "")
    monkeypatch.setattr(fichiers_instances.settings, "drive_url", API)
    monkeypatch.setattr(fichiers_instances.settings, "drive_public_host", HOTE)
    i = fichiers_instances.instances()
    assert list(i) == ["drive"] and i["drive"].sensibilite_max == Sensitivity.INTERNAL
    monkeypatch.setattr(fichiers_instances.settings, "drive_url", "")
    assert fichiers_instances.instances() == {}


def test_la_capacite_eteinte_ferme_les_routes(client, en_tant_que, capacites, drive):
    en_tant_que(IMPORTEUR)
    capacites(fichiers=False)
    assert client.get("/api/sources/fichiers/instances").status_code == 404


def test_les_instances_vues_par_la_personne(client, en_tant_que, drive):
    en_tant_que(IMPORTEUR)
    r = client.get("/api/sources/fichiers/instances").json()["instances"]
    assert [x["id"] for x in r] == ["public", "beta"], "l'instance RIE est réservée à son groupe"
    beta = r[1]
    assert beta["sensibilite_max"] == "internal" and beta["niveaux_permis"][0] == "internal" and "public" not in beta["niveaux_permis"]
    assert client.get("/api/sources/fichiers/espaces/rie/dossiers", headers=ENTETE).status_code == 404


# --- Parcourir ------------------------------------------------------------------------------------


def test_l_arbre_des_dossiers_et_l_apercu(client, en_tant_que, drive):
    en_tant_que(IMPORTEUR)
    d = client.get("/api/sources/fichiers/espaces/beta/dossiers", headers=ENTETE).json()["dossiers"]
    assert {x["id"]: x["chemin"] for x in d} == {"d1": "Pôle juridique", "d2": "Pôle juridique/Notes", "d3": "Pôle juridique/Archives", "autre": "Autre dossier"}
    assert next(x for x in d if x["id"] == "d2")["parent_id"] == "d1"
    a = client.get("/api/sources/fichiers/espaces/beta/apercu?dossier=d1", headers=ENTETE).json()
    assert a["total"] == 4
    inv = client.get("/api/sources/fichiers/espaces/beta/inventaire?dossier=d1", headers=ENTETE).json()
    assert inv["documents_a_la_racine"] == 1 and {n["id"]: n["documents"] for n in inv["dossiers"]} == {"d2": 2, "d3": 1}


def test_un_jeton_refuse_par_drive_ne_deconnecte_pas(client, en_tant_que, drive):
    en_tant_que(IMPORTEUR)
    r = client.get("/api/sources/fichiers/espaces/beta/dossiers", headers={"Authorization": "Bearer autre-jeton"})
    assert r.status_code == 502 and r.json()["detail"]["code"] == "jeton_invalide"


# --- Importer -------------------------------------------------------------------------------------


def test_importer_un_dossier(client, en_tant_que, drive):
    en_tant_que(IMPORTEUR)
    p = client.get("/api/sources/fichiers/proposition?espace=beta&dossier=d1").json()
    assert p == {"identifiant": COLLECTION, "disponible": True, "motif": None}
    r = _creer(client)
    assert r.status_code == 200, r.text
    assert r.json()["collection"] == COLLECTION and r.json()["sensibilite"] == "internal"
    fiche = client.get(f"/api/collections/{COLLECTION}").json()
    assert fiche["scope"] == "private" and fiche["source_type"] == "fichiers" and fiche["sensitivity"] == "internal"
    assert fiche["source_resume"]["type"] == "fichiers" and fiche["source_resume"]["documents_indexes"] == 4
    # Le moteur partagé, sous le profil Fichiers : identifiants, métadonnées, dossier d'attente.
    envois = drive.envois.await_args_list
    assert len(envois) == 4
    assert all(c.kwargs["file_id"].startswith("fichiers-f") for c in envois)
    meta = next(c.kwargs["metadata"] for c in envois if c.args[1] == "avis-a.md")
    assert meta["source"] == "fichiers" and meta["espace"] == "Mes fichiers (bêta)" and meta["dossier"] == "Pôle juridique/Notes"
    assert meta["url"] == f"https://{HOTE}/explorer/items/files/f1" and meta["sensitivity"] == "internal"
    # Les octets sont lus au stockage, avec la signature que rend Drive (media-auth).
    assert len([u for u in drive.requetes if u.startswith(STOCKAGE)]) == 4
    assert not os.path.exists(os.path.join(os.environ["DATA_DIR"], "_fichiers_attente", COLLECTION))
    statut = client.get(f"/api/sources/fichiers/status/{COLLECTION}", headers=ENTETE).json()
    assert statut["configured"] and statut["est_importeur"] and statut["travail"]["etat"] == "termine" and statut["travail"]["ajoutes"] == 4
    assert statut["sensibilite_min"] == "internal" and statut["dossiers"][0]["url"] == f"https://{HOTE}/explorer/items/d1"
    # Le journal dit d'où vient la synchronisation.
    from tests.unit.test_resana_routes import _sql

    lignes = _sql("SELECT detail_json FROM evenement WHERE collection_name = ? AND type = 'synchro.terminee'", (COLLECTION,))
    assert lignes and json.loads(lignes[-1][0])["source"] == "fichiers"


def test_une_sensibilite_sous_le_plafond_de_l_instance_est_refusee(client, en_tant_que, drive):
    en_tant_que(IMPORTEUR)
    r = _creer(client, sensibilite="public")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "sensibilite_incompatible"
    assert "Mes fichiers (bêta)" in r.json()["detail"]["message"]
    r = _creer(client, sensibilite="personal")
    assert r.status_code == 200 and r.json()["sensibilite"] == "personal"
    # Par la fiche : monter est permis, descendre sous l'instance non.
    assert client.patch(f"/api/collections/{COLLECTION}", json={"sensitivity": "public"}).status_code == 409
    assert client.patch(f"/api/collections/{COLLECTION}", json={"sensitivity": "internal"}).status_code == 200
    assert client.patch(f"/api/collections/{COLLECTION}", json={"sensitivity": "controlled"}).status_code == 200


def test_la_portee_et_la_source_restent_verrouillees(client, en_tant_que, drive):
    en_tant_que(IMPORTEUR)
    assert _creer(client).status_code == 200
    r = client.patch(f"/api/collections/{COLLECTION}", json={"scope": "public"})
    assert r.status_code == 409 and "Fichiers" in r.json()["detail"]
    # Le préfixe est réservé : une création manuelle le refuse.
    r = client.post("/api/collections", json={"name": "fichiers-beta-xyz", "titre": "t"})
    assert r.status_code in (403, 422)
    assert nommage.motif_de_refus("fichiers-beta-xyz") == "fichiers" and nommage.motif_de_refus("fichiers-beta-xyz", source="fichiers") is None


def test_un_second_import_du_meme_dossier_demande_un_suffixe(client, en_tant_que, drive):
    en_tant_que(IMPORTEUR)
    assert _creer(client).status_code == 200
    r = _creer(client)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "identifiant_pris"
    assert _creer(client, suffixe="bis").json()["collection"] == f"{COLLECTION}-bis"


# --- Mettre à jour -------------------------------------------------------------------------------


def test_la_mise_a_jour_ne_relit_que_ce_qui_a_change(client, en_tant_que, drive):
    en_tant_que(IMPORTEUR)
    assert _creer(client).status_code == 200
    avant = len(drive.telechargements())
    # Rien n'a bougé : rien n'est téléchargé.
    assert client.post(f"/api/sources/fichiers/sync/{COLLECTION}", headers=ENTETE).status_code == 200
    assert len(drive.telechargements()) == avant and _cfg()["travail"]["etat"] == "a_jour"
    # Un fichier modifié, un supprimé, un ajouté.
    drive.elements["f1"].contenu = b"# Avis A\n\nTexte fictif revu."
    drive.elements["f1"].modifie_le = "2026-10-20T10:00:00Z"
    del drive.elements["f2"]
    drive.ajouter(Element("f5", "nouveau.md", parent="d2", contenu=b"# Nouveau\n\nTexte fictif neuf."))
    ancien_f2 = _cfg()["documents"]["f2"]["file_id"]
    assert client.post(f"/api/sources/fichiers/sync/{COLLECTION}", headers=ENTETE).status_code == 200
    t = _cfg()["travail"]
    assert (t["ajoutes"], t["modifies"], t["retires"], t["inchanges"]) == (1, 1, 1, 2)
    assert len(drive.telechargements()) == avant + 2
    retires = [c.args for c in drive.openrag.delete_file.await_args_list]
    assert any(ancien_f2 in a for a in retires), "un fichier supprimé dans Drive sort de l'index"


def test_seul_l_importeur_met_a_jour(client, en_tant_que, drive):
    en_tant_que(IMPORTEUR)
    assert _creer(client).status_code == 200
    from app.main import app
    from app.routers import _droits

    en_tant_que(AUTRE)
    app.dependency_overrides[_droits.gerer_la_collection] = lambda: None
    r = client.post(f"/api/sources/fichiers/sync/{COLLECTION}", headers=ENTETE)
    assert r.status_code in (403, 404)


def test_un_document_vide_est_ecarte_et_un_fichier_recu_vide_est_redemande(client, en_tant_que, drive):
    drive.ajouter(Element("f6", "vide.md", parent="d2", contenu=b""), Element("f7", "rate.md", parent="d2", contenu=b"# Rate\n\nTexte fictif.", recu=b""))
    en_tant_que(IMPORTEUR)
    assert _creer(client).status_code == 200
    cfg = _cfg()
    assert set(cfg["documents"]) == {"f1", "f2", "f3", "f4"}
    raisons = {e["id"]: e["raison"] for e in cfg["travail"]["documents_ecartes"]}
    assert "vide dans Fichiers" in raisons["f6"] and "renvoyé ce fichier vide" in raisons["f7"]
    codes = {e["id"]: e["code"] for e in cfg["travail"]["documents_ecartes"]}
    assert codes["f6"] == "vide" and codes["f7"] == "fichier_vide"
    # Reçu vide : redemandé (deux reprises) ; vide pour de bon : jamais téléchargé.
    assert len([u for u in drive.requetes if u.startswith(STOCKAGE) and "/f7/" in u]) == 3
    assert not [u for u in drive.requetes if u.startswith(STOCKAGE) and "/f6/" in u]
    # Le stockage rend enfin le fichier : la mise à jour suivante le prend.
    drive.elements["f7"].recu = None
    client.post(f"/api/sources/fichiers/sync/{COLLECTION}", headers=ENTETE)
    assert "f7" in _cfg()["documents"]


def test_une_session_perdue_en_route_garde_l_acquis(client, en_tant_que, drive):
    en_tant_que(IMPORTEUR)
    drive.pannes["/api/v1.0/items/media-auth/"] = 401
    assert _creer(client).status_code == 200
    t = _cfg()["travail"]
    assert t["etat"] == "echec" and t["code"] == "jeton_invalide" and "reconnectez-vous" in t["message"]


def test_les_identifiants_de_resana_ne_changent_pas():
    """Hors d'une passe Fichiers, le moteur reste celui de Résana : ses identifiants dans l'index
    ne bougent pas (un autre préfixe renverrait tous les documents déjà indexés)."""
    sha = "a" * 64
    assert sources_resana.identifiant_dans_l_index("123", sha) == f"resana-123-{'a' * 16}"
    assert sources_resana._attente("x").name == "x" and sources_resana._attente("x").parent.name == "_resana_attente"


# --- Destinations ---------------------------------------------------------------------------------


def test_publier_demande_un_groupe_une_confirmation_et_respecte_le_plafond(client, en_tant_que, drive, monkeypatch):
    en_tant_que(IMPORTEUR)
    assert _creer(client, sensibilite="personal").status_code == 200
    with pytest.MonkeyPatch.context() as m:
        from app.routers import publication

        m.setattr(publication, "_synchroniser_owui", AsyncMock(), raising=False)
        r = client.post(f"/api/collections/{COLLECTION}/publish", json={"state": "published", "visibility": "all"})
        assert r.status_code == 409 and "Fichiers" in r.json()["detail"]
        r = client.post(f"/api/collections/{COLLECTION}/publish", json={"state": "published", "visibility": "group", "visibility_groups": ["/g/equipe"]})
        assert r.status_code == 409 and "confirmez" in r.json()["detail"]
        monkeypatch.setattr(fichiers_instances.settings, "destinations_sensibilite_max", json.dumps({"chat": "internal"}))
        r = client.post(
            f"/api/collections/{COLLECTION}/publish", json={"state": "published", "visibility": "group", "visibility_groups": ["/g/equipe"], "droits_resana_confirmes": True}
        )
        assert r.status_code == 409 and "jusqu'au niveau « Interne »" in r.json()["detail"]


def test_la_recherche_respecte_son_plafond(client, en_tant_que, drive, monkeypatch):
    en_tant_que(IMPORTEUR)
    assert _creer(client, sensibilite="personal").status_code == 200
    from app.routers import recherche

    lisibles = [f["name"] for f in asyncio.run(recherche._collections_lisibles(IMPORTEUR))]
    assert COLLECTION in lisibles
    monkeypatch.setattr(fichiers_instances.settings, "destinations_sensibilite_max", json.dumps({"recherche": "internal"}))
    lisibles = [f["name"] for f in asyncio.run(recherche._collections_lisibles(IMPORTEUR))]
    assert COLLECTION not in lisibles


# --- Le client ------------------------------------------------------------------------------------


def test_le_client_presente_le_nom_public_au_service_interne_et_suit_l_adresse_publique_sans_stockage():
    faux = _arbre()
    vus: list[dict] = []
    transport = faux.transport()

    def avec_espion(req):
        vus.append(dict(req.headers))
        return transport.handle_request(req)

    import httpx

    beta = fichiers_instances.Instance.model_validate(INSTANCES[1])
    c = ClientFichiers(beta, JETON, transport=httpx.MockTransport(avec_espion))
    docs = asyncio.run(c.documents("beta", "d2"))
    assert vus[0]["host"] == HOTE and vus[0]["x-forwarded-proto"] == "https"
    # Sans stockage déclaré : on suit l'adresse publique du fichier, avec le jeton de la personne.
    sans = fichiers_instances.Instance.model_validate({**INSTANCES[1], "stockage_url": ""})
    c = ClientFichiers(sans, JETON, transport=faux.transport())
    docs = asyncio.run(c.documents("beta", "d2"))
    f = asyncio.run(c.fichier(docs[0], "beta"))
    assert f.contenu.startswith(b"# Avis") and any(u.startswith(f"https://{HOTE}/media/") for u in faux.requetes)


def test_un_document_lu_apres_le_delai_de_suivi_n_est_ni_retire_ni_renvoye(client, en_tant_que, drive, monkeypatch):
    """Mesuré en bêta le 2026-10-25 : la file de l'indexeur était si longue que les documents ont été
    lus après les 30 minutes de suivi. La mise à jour suivante le demande à l'indexeur au lieu de les
    retirer puis de les renvoyer au bout de la file."""
    from app.routers import ingest
    from app.services.openrag_client import EnvoiDocument, EtatTache, FichierOpenRAG

    monkeypatch.setattr(ingest, "SUIVI_DOCUMENT_MAX_S", -1)  # « pas fini de lire » aussitôt
    # Une tâche à suivre, qui reste en file.
    drive.openrag.upload_document.side_effect = lambda partition, nom, contenu, mime, metadata=None, file_id=None: EnvoiDocument(file_id=file_id or nom, task_id="t")
    drive.openrag.task_state = AsyncMock(return_value=EtatTache(task_state="QUEUED"))
    en_tant_que(IMPORTEUR)
    assert _creer(client).status_code == 200
    cfg = _cfg()
    assert cfg["travail"]["en_erreur"] == 4 and all("pas fini de lire" in d["erreur"] for d in cfg["documents"].values())
    # L'indexeur a fini depuis : sa partition les porte, avec leur qualité.
    lus = [FichierOpenRAG(file_id=d["file_id"], degraded_stages=[]) for d in cfg["documents"].values()]
    drive.openrag.list_files = AsyncMock(return_value=lus)
    drive.envois.reset_mock()
    drive.openrag.delete_file.reset_mock()
    assert client.post(f"/api/sources/fichiers/sync/{COLLECTION}", headers=ENTETE).status_code == 200
    t = _cfg()["travail"]
    assert drive.envois.await_count == 0 and drive.openrag.delete_file.await_count == 0
    assert t["etat"] == "a_jour" and t["en_erreur"] == 0 and t["inchanges"] == 4
    assert all(d.get("qualite", {}).get("etat") == "complet" and not d.get("erreur") for d in _cfg()["documents"].values())


def test_un_fichier_en_analyse_attend_et_un_fichier_suspect_n_est_pas_indexe(client, en_tant_que, drive):
    """Les états de Drive relevés dans drive-migrator : `analyzing` (antivirus en cours) se reprend à la
    mise à jour suivante, `suspicious` sort de la liste (Drive le cache aux membres) et donc de
    l'index, `file_too_large_to_analyze` se lit."""
    drive.ajouter(
        Element("f8", "en-analyse.md", parent="d2", contenu=b"# En analyse\n\nTexte fictif.", etat="analyzing"),
        Element("f9", "suspect.md", parent="d2", contenu=b"# Suspect\n\nTexte fictif.", etat="suspicious"),
        Element("f10", "gros.md", parent="d2", contenu=b"# Gros\n\nTexte fictif.", etat="file_too_large_to_analyze"),
    )
    en_tant_que(IMPORTEUR)
    assert _creer(client).status_code == 200
    cfg = _cfg()
    assert set(cfg["documents"]) == {"f1", "f2", "f3", "f4", "f10"}
    codes = {e["id"]: e["code"] for e in cfg["travail"]["documents_ecartes"]}
    assert codes == {"f8": "en_cours_d_analyse"}
    # Ni l'un ni l'autre n'est téléchargé.
    assert not [u for u in drive.telechargements() if "/f8/" in u or "/f9/" in u]

    # L'analyse finie, la mise à jour le prend ; le suspect reste écarté.
    drive.elements["f8"].etat = "ready"
    assert client.post(f"/api/sources/fichiers/sync/{COLLECTION}", headers=ENTETE).status_code == 200
    cfg = _cfg()
    assert "f8" in cfg["documents"] and "f9" not in cfg["documents"]

    # Un document indexé, revu et de nouveau en analyse, garde sa version ; un document devenu
    # suspect sort de l'index.
    sha_f1 = cfg["documents"]["f1"]["sha256"]
    fichier_f2 = cfg["documents"]["f2"]["file_id"]
    drive.elements["f1"].contenu, drive.elements["f1"].modifie_le, drive.elements["f1"].etat = b"# Avis A\n\nRevu.", "2026-10-21T10:00:00Z", "analyzing"
    drive.elements["f2"].etat = "suspicious"
    drive.openrag.delete_file.reset_mock()
    assert client.post(f"/api/sources/fichiers/sync/{COLLECTION}", headers=ENTETE).status_code == 200
    cfg = _cfg()
    assert cfg["documents"]["f1"]["sha256"] == sha_f1, "la version déjà indexée reste"
    assert "f2" not in cfg["documents"]
    retires = [c.args for c in drive.openrag.delete_file.await_args_list]
    assert any(fichier_f2 in a for a in retires) and not any(cfg["documents"]["f1"]["file_id"] in a for a in retires)
    # La passe suivante, l'analyse finie, prend la nouvelle version.
    drive.elements["f1"].etat = "ready"
    client.post(f"/api/sources/fichiers/sync/{COLLECTION}", headers=ENTETE)
    assert _cfg()["documents"]["f1"]["sha256"] != sha_f1


def test_le_client_relit_l_etat_d_un_fichier_demande_hors_liste():
    """Un fichier demandé sans être passé par la liste : son état est relu dans Drive avant tout téléchargement."""
    from app.services.connectors.resana import ErreurResana

    faux = _arbre().ajouter(Element("s1", "suspect.md", parent="d2", contenu=b"x", etat="suspicious"), Element("a1", "analyse.md", parent="d2", contenu=b"x", etat="analyzing"))
    c = ClientFichiers(fichiers_instances.Instance.model_validate(INSTANCES[1]), JETON, transport=faux.transport())
    with pytest.raises(ErreurResana) as e:
        asyncio.run(c.fichier("s1", "beta"))
    assert (e.value.statut, e.value.code, e.value.reessayable) == (422, "fichier_suspect", False)
    with pytest.raises(ErreurResana) as e:
        asyncio.run(c.fichier("a1", "beta"))
    assert (e.value.code, e.value.reessayable) == ("en_cours_d_analyse", True)
    assert not faux.telechargements()


def test_un_csv_et_un_json_partent_vers_l_indexeur_sous_un_nom_qu_il_lit(client, en_tant_que, drive):
    """L'indexeur choisit son lecteur à l'extension : un .csv ou un .json envoyé sous son nom était
    refusé (parcours e2e des formats, 2026-10-26). Ils partent en `.txt` ; un Markdown garde son nom."""
    drive.ajouter(
        Element("f8", "donnees.csv", parent="d2", contenu="rubrique;valeur\ncontrôle;texte fictif\n".encode()),
        Element("f9", "note.json", parent="d2", contenu=b'{"note": "texte fictif"}'),
    )
    en_tant_que(IMPORTEUR)
    assert _creer(client).status_code == 200
    noms = {c.args[1] for c in drive.envois.await_args_list}
    assert {"donnees.csv.txt", "note.json.txt", "avis-a.md"} <= noms
    assert {"f8", "f9"} <= set(_cfg()["documents"])
