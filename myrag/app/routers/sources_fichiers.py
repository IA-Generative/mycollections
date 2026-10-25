"""Fichiers : importer un dossier d'une instance de Drive (La Suite numérique) dans une collection,
puis le mettre à jour. Voir docs/fichiers.md.

Même contrat que Résana (docs/resana.md), dont on réutilise le moteur (`sources_resana`, sous le
profil `fichiers`, `app/services/synchro_profil.py`) :

- la capacité `fichiers` est éteinte par défaut : sans elle, ces routes répondent 404 ;
- plusieurs instances, déclarées par `MYCOLLECTIONS_FICHIERS_INSTANCES` ; chacune porte le niveau de
  sensibilité le plus haut qu'elle est censée contenir. La collection prend ce niveau et ne descend
  jamais en dessous (`app/services/sensibilite.py`) ;
- Drive est lu avec le jeton de la personne : ses droits, rien de plus ; la collection naît privée à
  qui l'importe, et lui seul la met à jour ;
- « Mettre à jour » relit les dossiers et ne réindexe que ce qui a changé (date de modification,
  puis empreinte) ; un fichier supprimé dans Drive sort de l'index.

Le vocabulaire du moteur est celui de Résana : l'« espace » est ici l'instance.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.auth import CurrentUser, current_user
from app.routers import sources_resana as moteur
from app.routers._commun import capacite
from app.routers._droits import gerer_la_collection, lire_la_collection
from app.services import nommage, resana_ecarts, resana_perimetre, sensibilite
from app.services.chunker import Sensitivity
from app.services.collection_store import get_collection, get_source_config, update_collection
from app.services.connectors.fichiers import ClientFichiers
from app.services.connectors.resana import ErreurResana
from app.services.fichiers_instances import Instance, instance, lisibles_par
from app.services.synchro_profil import Profil, sous

logger = logging.getLogger("myrag.sources.fichiers")

router = APIRouter(prefix="/fichiers", tags=["Sources"], dependencies=[Depends(capacite("fichiers"))])

SOURCE = "fichiers"
PROFIL = Profil(source=SOURCE, nom="Fichiers", prefixe_index="fichiers-", dossier_attente="_fichiers_attente")

MESSAGE_DOSSIER_VIDE = "Ce dossier ne contient aucun document."
MESSAGE_SYNCHRO_VIDE = "Le dossier est vide dans Fichiers : rien n'est retiré de la collection. Supprimez-la si c'est voulu."


def _fabrique(inst: Instance, jeton: str) -> ClientFichiers:
    """Le client de l'instance ; les tests la remplacent pour brancher un faux Drive."""
    return ClientFichiers(inst, jeton)


def _instance(ident: str, user: CurrentUser) -> Instance:
    inst = instance(ident)
    if inst is None or not inst.ouverte_a(user.groups):
        raise moteur._refus(404, "instance_inconnue", "Cette instance de Fichiers n'est pas proposée ici.")
    return inst


def _client(inst: Instance, authorization: str | None) -> ClientFichiers:
    jeton = authorization.split(" ", 1)[1].strip() if authorization and authorization.lower().startswith("bearer ") else ""
    try:
        return _fabrique(inst, jeton)
    except ErreurResana as e:
        raise moteur._http(e) from None


def _avec_profil(travail):
    return sous(PROFIL, travail)


# --- Parcourir --------------------------------------------------------------------------------


@router.get("/instances")
async def instances(user: CurrentUser = Depends(current_user)):
    """Les instances que la personne peut importer, avec leur zone et leur plafond de sensibilité,
    et les niveaux que leurs collections peuvent prendre (le plafond de l'instance, ou plus haut)."""
    return {
        "instances": [
            {**i.publique(), "sensibilite_libelle": sensibilite.libelle(i.sensibilite_max), "niveaux_permis": sensibilite.niveaux_permis(i.sensibilite_max)}
            for i in lisibles_par(user.groups)
        ]
    }


@router.get("/espaces/{ident}/dossiers")
async def dossiers(ident: str, recherche: str = Query("", max_length=200), authorization: str | None = Header(default=None), user: CurrentUser = Depends(current_user)):
    """Tous les dossiers que la personne voit dans l'instance (son espace, ce qu'on lui partage)."""
    client = _client(_instance(ident, user), authorization)
    try:
        rendu = await client.dossiers(ident, recherche)
    except ErreurResana as e:
        raise moteur._http(e) from None
    return {"dossiers": [{"id": d.id, "titre": d.titre, "parent_id": d.parent_id, "chemin": d.chemin} for d in rendu]}


@router.get("/espaces/{ident}/apercu")
async def apercu(ident: str, dossier: str = Query(..., min_length=1, max_length=200), authorization: str | None = Header(default=None), user: CurrentUser = Depends(current_user)):
    client = _client(_instance(ident, user), authorization)
    try:
        docs = await client.documents(ident, dossier)
    except ErreurResana as e:
        raise moteur._http(e) from None
    tailles = [d.taille_approx_mo for d in docs if d.taille_approx_mo is not None]
    return {"total": len(docs), "taille_approx_mo": round(sum(tailles), 1) if tailles else None, "documents": [{"titre": d.titre, "chemin": d.chemin} for d in docs[:20]]}


@router.get("/espaces/{ident}/inventaire")
async def inventaire(
    ident: str, dossier: str = Query(..., min_length=1, max_length=200), authorization: str | None = Header(default=None), user: CurrentUser = Depends(current_user)
):
    client = _client(_instance(ident, user), authorization)
    try:
        docs = await client.documents(ident, dossier)
    except ErreurResana as e:
        raise moteur._http(e) from None
    a_la_racine, noeuds = resana_perimetre.inventaire(dossier, client.dossiers_vus(), docs)
    tailles = [d.taille_approx_mo for d in docs if d.taille_approx_mo is not None]
    return {
        "total": len(docs),
        "taille_approx_mo": round(sum(tailles), 1) if tailles else None,
        "documents_a_la_racine": a_la_racine,
        "dossiers": [n.vers_dict() for n in noeuds],
    }


@router.get("/existant")
async def existant(espace: str = Query(..., min_length=1, max_length=40), user: CurrentUser = Depends(current_user)):
    """Les collections Fichiers de la personne déjà ancrées sur cette instance (les siennes seulement)."""
    from app.services.collection_store import list_collections

    rendu = []
    for col in await list_collections(include_archived=False):
        if col.get("source_type") != SOURCE or not user.sub or col.get("created_by") != user.sub:
            continue
        cfg = await get_source_config(col["name"])
        if str(moteur._espace_de(cfg).get("id")) != espace:
            continue
        rendu.append(
            {
                **resana_perimetre.couverture(cfg),
                "collection": col["name"],
                "titre": col.get("titre") or col["name"],
                "chemins": [d.get("chemin") or d["id"] for d in moteur._dossiers_de(cfg)],
            }
        )
    return {"collections": rendu}


@router.get("/proposition")
async def proposition(
    espace: str = Query(..., min_length=1, max_length=40),
    dossier: str = Query(..., min_length=1, max_length=200),
    suffixe: str = Query("", max_length=30),
    user: CurrentUser = Depends(current_user),
):
    """L'identifiant que recevra la collection (`fichiers-<instance>-<dossier>[-<suffixe>]`) et s'il
    est libre. Le serveur seul le pose."""
    nom = nommage.identifiant_fichiers(espace, dossier, suffixe)
    motif = nommage.motif_de_refus(nom, source=SOURCE)
    pris = bool(await get_collection(nom))
    return {"identifiant": nom, "disponible": not pris and motif is None, "motif": nommage.MOTIFS.get(motif) if motif else None}


# --- Importer et mettre à jour ----------------------------------------------------------------


class CreationFichiers(BaseModel):
    espace_id: str = Field(min_length=1, max_length=40)
    dossiers: list[moteur.DossierChoisi] = Field(min_length=1, max_length=50)
    exclus: list[str] = Field(default_factory=list, max_length=2000)
    titre: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    #: Absente : le plafond de l'instance. Plus basse que lui : refusée (409).
    sensibilite: str | None = None
    suffixe: str = Field("", max_length=30)


def _exiger_importeur(col: dict, user: CurrentUser) -> None:
    if not user.sub or col.get("created_by") != user.sub:
        raise moteur._refus(403, "reserve_a_l_importeur", "Seule la personne qui a importé ce dossier peut le mettre à jour (avec ses propres droits dans Fichiers).")


def plancher_de(cfg: dict) -> Sensitivity:
    """Le niveau des documents de la collection : celui noté à l'import (le plafond de l'instance)."""
    return sensibilite.niveau((cfg.get("espace") or {}).get("sensibilite_max"), Sensitivity.INTERNAL)


async def refus_sensibilite(collection: str, demande: str) -> str | None:
    """Pour la fiche (PATCH) : la phrase de refus si `demande` est sous le niveau des documents de
    l'instance d'origine, sinon None."""
    cfg = await get_source_config(collection)
    nom_instance = str((cfg.get("espace") or {}).get("nom") or "l'instance")
    return sensibilite.refus_plancher(sensibilite.niveau(demande), plancher_de(cfg), nom_instance)


def _travail(action: str, docs) -> dict:
    return moteur._travail(action, docs)


async def _lancer(nom: str, client: ClientFichiers, espace: dict, dossiers: list[dict], exclus: list[str], docs, user: CurrentUser) -> None:
    cfg = {
        "espace": espace,
        "documents": {},
        "last_sync_at": None,
        "perimetre": {"dossiers": dossiers, "exclus": sorted({e for e in exclus if e and e not in {d["id"] for d in dossiers}})},
        "travail": _travail("import", docs),
    }
    # Privée d'abord, documents ensuite : rien de Fichiers n'est jamais lisible hors de la personne.
    await update_collection(nom, {"scope": "private", "scope_groups": [], "source_type": SOURCE, "source_url": "", "source_config_json": json.dumps(cfg)})
    await moteur._demarrer(nom, _avec_profil(moteur._executer(nom, client, str(espace["id"]), dossiers, docs, "import", user)))


@router.post("/collections")
async def creer(req: CreationFichiers, authorization: str | None = Header(default=None), user: CurrentUser = Depends(current_user)):
    """Créer une collection ancrée sur un dossier d'une instance et lancer son indexation, en un
    appel. L'identifiant est posé ici ; la sensibilité est au moins celle de l'instance."""
    from app.routers.collections import CreateCollectionRequest, creer_collection

    inst = _instance(req.espace_id, user)
    demande = sensibilite.niveau(req.sensibilite, inst.sensibilite_max) if req.sensibilite else inst.sensibilite_max
    if req.sensibilite and Sensitivity._missing_(req.sensibilite) is None and req.sensibilite not in {s.value for s in Sensitivity}:
        raise moteur._refus(422, "sensibilite_inconnue", f"Sensibilité inconnue : {req.sensibilite}")
    refus = sensibilite.refus_plancher(demande, inst.sensibilite_max, inst.titre)
    if refus:
        raise moteur._refus(409, "sensibilite_incompatible", refus)
    dossiers = moteur._dossiers_propres(req.dossiers)
    nom = nommage.identifiant_fichiers(inst.id, dossiers[0]["id"], req.suffixe)
    existante = await get_collection(nom)
    if existante:
        mienne = existante.get("created_by") == user.sub
        raise moteur._refus(
            409,
            "identifiant_pris",
            f"Vous avez déjà une collection sur ce dossier (« {existante.get('titre') or nom} ») : mettez-la à jour, ou donnez un suffixe pour en créer une seconde."
            if mienne
            else "Une collection porte déjà cet identifiant : donnez un suffixe.",
        )
    client = _client(inst, authorization)
    try:
        docs = await moteur._lister(client, inst.id, dossiers)
    except ErreurResana as e:
        raise moteur._http(e) from None
    if not docs:
        raise moteur._refus(400, "dossier_vide", MESSAGE_DOSSIER_VIDE)
    espace = {"id": inst.id, "nom": inst.titre, "hote": inst.hote_public or "", "sensibilite_max": inst.sensibilite_max.value}
    chemins = " · ".join(d["chemin"] for d in dossiers)
    await creer_collection(
        CreateCollectionRequest(
            name=nom,
            titre=req.titre.strip(),
            description=req.description.strip() or f"Dossier « {chemins} » de {inst.titre}.",
            sensitivity=demande,
            scope="private",
            scope_groups=[],
        ),
        user,
        source=SOURCE,
    )
    await _lancer(nom, client, espace, dossiers, req.exclus, docs, user)
    return {"status": "import_lance", "collection": nom, "total": len(docs), "sensibilite": demande.value}


async def _collection_fichiers(collection: str, user: CurrentUser) -> dict:
    await gerer_la_collection(collection, user)
    col = await get_collection(collection)
    if not col:
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
    if col.get("source_type") != SOURCE:
        raise moteur._refus(400, "pas_fichiers", "Cette collection n'est pas reliée à Fichiers.")
    return col


@router.post("/sync/{collection}")
async def synchroniser(collection: str, corps: moteur.SynchroResana | None = None, authorization: str | None = Header(default=None), user: CurrentUser = Depends(current_user)):
    """Relire les dossiers et réindexer ce qui a changé ; `dossiers`/`exclus` changent d'abord la
    sélection ; `complet` retélécharge tout ; `incomplets` renvoie les documents mal indexés."""
    col = await _collection_fichiers(collection, user)
    _exiger_importeur(col, user)
    if moteur._occupee(collection):
        raise moteur._refus(409, "travail_en_cours", "Une mise à jour est déjà en cours pour cette collection.")
    cfg = await get_source_config(collection)
    espace = str(moteur._espace_de(cfg).get("id") or "")
    inst = _instance(espace, user)
    client = _client(inst, authorization)
    avant = moteur._dossiers_de(cfg)
    dossiers = moteur._dossiers_propres(corps.dossiers) if corps is not None and corps.dossiers else avant
    try:
        docs = await moteur._lister(client, espace, dossiers)
    except ErreurResana as e:
        raise moteur._http(e) from None
    if not docs:
        raise moteur._refus(409, "dossier_vide", MESSAGE_SYNCHRO_VIDE)
    perimetre = dict(cfg.get("perimetre") or {})
    perimetre["dossiers"] = dossiers
    if corps is not None and corps.exclus is not None:
        perimetre["exclus"] = sorted({e for e in corps.exclus if e and e not in {d["id"] for d in dossiers}})
    cfg["perimetre"] = perimetre
    cfg["travail"] = _travail("synchronisation", docs)
    await update_collection(collection, {"source_config_json": json.dumps(cfg)})
    ajoutes = [d["chemin"] for d in dossiers if d["id"] not in {x["id"] for x in avant}]
    retires = [d["chemin"] for d in avant if d["id"] not in {x["id"] for x in dossiers}]
    if ajoutes or retires:
        await moteur.consigner(
            "synchronisation", collection, "perimetre.modifie", user.sub, collection_name=collection, detail={"source": SOURCE, "ajoutes": ajoutes, "retires": retires}
        )
    complet = bool(corps and corps.complet)
    reprendre = moteur.a_reprendre(cfg) if corps is not None and corps.incomplets else set()
    action = "reindexation" if reprendre else "synchronisation"
    await moteur._demarrer(collection, _avec_profil(moteur._executer(collection, client, espace, dossiers, docs, action, user, complet=complet, reprendre=reprendre)))
    return {"status": "synchro_lancee", "collection": collection, "total": len(docs), "a_reprendre": len(reprendre)}


@router.post("/qualite/{collection}")
async def relire_la_qualite(collection: str, user: CurrentUser = Depends(current_user)):
    """Relire auprès de l'indexeur ce que vaut chaque document, sans rien renvoyer ni lire Fichiers."""
    await _collection_fichiers(collection, user)
    if moteur._occupee(collection):
        raise moteur._refus(409, "travail_en_cours", "Une mise à jour est en cours pour cette collection.")
    try:
        lues = await moteur.depot._indexeur().qualites(collection)
    except Exception:  # noqa: BLE001
        raise moteur._refus(502, "indexeur_injoignable", "Le moteur de recherche ne répond pas : réessayez dans un instant.") from None
    cfg = await get_source_config(collection)
    documents = dict(cfg.get("documents") or {})
    mises_a_jour = moteur.appliquer_qualites(documents, lues)
    if mises_a_jour:
        await moteur._ecrire_config(collection, documents=documents)
    return {"collection": collection, "mises_a_jour": mises_a_jour, "qualite": moteur.bilan_qualite({**cfg, "documents": documents})}


@router.get("/status/{collection}", dependencies=[Depends(lire_la_collection)])
async def statut(collection: str, authorization: str | None = Header(default=None), user: CurrentUser = Depends(current_user)):
    from datetime import datetime, timezone

    from app.config import settings

    col = await get_collection(collection)
    if not col:
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
    est_importeur = col.get("source_type") == SOURCE and bool(user.sub) and col.get("created_by") == user.sub
    if est_importeur:
        moteur.relayer_jeton(collection, authorization)
    cfg = await get_source_config(collection)
    travail = dict(cfg.get("travail") or {})
    if travail.get("etat") == "en_cours" and not moteur._occupee(collection):
        travail["etat"] = "interrompu"
    if travail.get("documents_ecartes"):
        travail["documents_ecartes"] = moteur._ecartes_du_travail(cfg)
    espace = moteur._espace_de(cfg)
    inst = instance(str(espace.get("id") or ""))
    avis = resana_perimetre.avis(
        collection,
        {**cfg, "travail": travail},
        est_importeur=est_importeur,
        maintenant=datetime.now(timezone.utc),
        seuil_jours=settings.resana_fraicheur_jours,
        titre=col.get("titre") or "",
    )
    if avis:
        avis = {**avis, "code": avis["code"].replace("resana_", "fichiers_", 1), "message": avis["message"].replace("Résana", "Fichiers", 1)}
    return {
        "collection": collection,
        "configured": col.get("source_type") == SOURCE,
        "source": SOURCE,
        "espace": {k: v for k, v in espace.items() if k in ("id", "nom", "hote", "sensibilite_max")},
        "espace_nom": espace.get("nom"),
        "sensibilite_min": plancher_de(cfg).value,
        "dossiers": [{"id": d["id"], "chemin": d.get("chemin"), **({"url": inst.url_dossier(d["id"])} if inst else {})} for d in moteur._dossiers_de(cfg)],
        "dossier_chemin": " · ".join(d.get("chemin") or d["id"] for d in moteur._dossiers_de(cfg)),
        "documents": len(cfg.get("documents") or {}),
        "qualite": moteur.bilan_qualite(cfg),
        "last_sync_at": cfg.get("last_sync_at"),
        "travail": travail or None,
        "est_importeur": est_importeur,
        "espace_id": espace.get("id") if est_importeur else None,
        "exclus": list((cfg.get("perimetre") or {}).get("exclus") or []) if est_importeur else [],
        **resana_perimetre.couverture({**cfg, "travail": travail}),
        "avis": avis,
    }


@router.get("/ecartes/{collection}", dependencies=[Depends(lire_la_collection)])
async def ecartes(collection: str, format: str = Query("csv", pattern="^(json|csv)$")):
    col = await get_collection(collection)
    if not col or col.get("source_type") != SOURCE:
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
    liste = moteur._ecartes_complets(await get_source_config(collection))
    nom = f"{collection}-documents-ecartes.{format}"
    entete = {"Content-Disposition": f'attachment; filename="{nom}"'}
    if format == "json":
        return JSONResponse({"collection": collection, "total": len(liste), "ecartes": [{**e, **resana_ecarts.expliquer(e["code"])} for e in liste]}, headers=entete)
    return Response(resana_ecarts.vers_csv(liste), media_type="text/csv; charset=utf-8", headers=entete)
