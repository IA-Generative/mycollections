"""Résana : importer un dossier d'un espace dans une collection, puis le synchroniser.

Le service d'export (owuitools-resana, contrat `docs/export-v1.md`) agit avec la session Résana
**de la personne** : Mes collections lui relaie le jeton reçu du navigateur, jamais une adresse.
Voir docs/resana.md.

Règles de la v1 :
- la capacité `resana` est éteinte par défaut : sans elle, ces routes répondent 404 ;
- seule la personne qui a créé la collection y importe un dossier, et la collection doit être
  privée, sans groupe lecteur, vide et non publiée : ce qu'on importe de Résana reste à elle ;
- la synchronisation est réservée à cette même personne (ses droits Résana, sa session) ;
- un dossier importé l'est entier (sous-dossiers compris) ; « Synchroniser » le relit, retélécharge
  chaque document et ne réindexe que si un condensat (sha256) a changé, apparu ou disparu.

Le téléchargement se fait en tâche de fond, avec le jeton de la personne gardé en mémoire le temps
de la tâche (jamais écrit) ; l'écran suit l'avancement par `/status`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth import CurrentUser, current_user
from app.config import settings
from app.database import async_session
from app.models.db import Publication, SourceFile, utcnow
from app.routers import ingest as depot
from app.routers._commun import capacite
from app.routers._droits import gerer_la_collection, lire_la_collection
from app.services import formats
from app.services.chunker import Sensitivity, Strategy
from app.services.collectif_store import consigner
from app.services.collection_store import get_collection, get_source_config, update_collection
from app.services.connectors.resana import ClientExportResana, DocumentResana, ErreurResana, Fichier, nom_unique

logger = logging.getLogger("myrag.sources.resana")

router = APIRouter(prefix="/resana", tags=["Sources"], dependencies=[Depends(capacite("resana"))])

SOURCE = "resana"
#: Plafond d'un import ou d'une synchronisation, comme pour Drive : au-delà, un sous-dossier.
OCTETS_MAX_TOTAL = 500 * 1024 * 1024
TELECHARGEMENTS_PARALLELES = 4
#: Les erreurs qui arrêtent tout ; les autres (droits, taille d'un document) n'écartent que lui.
ERREURS_BLOQUANTES = {"session_absente", "jeton_invalide", "appelant_inconnu", "resana_indisponible", "service_injoignable", "reponse_illisible", "trop_volumineux_total"}
#: Ce que l'écran garde des documents écartés (le reste se compte).
ECARTES_MAX = 50

#: Une tâche par collection, dans ce processus.
_TACHES: dict[str, asyncio.Task] = {}


def _fabrique(base_url: str, secret: str, jeton: str) -> ClientExportResana:
    """Le client du service ; les tests la remplacent pour brancher un faux service."""
    return ClientExportResana(base_url, secret, jeton)


def _client(authorization: str | None) -> ClientExportResana:
    jeton = authorization.split(" ", 1)[1].strip() if authorization and authorization.lower().startswith("bearer ") else ""
    try:
        return _fabrique(settings.resana_export_url, settings.resana_export_secret, jeton)
    except ErreurResana as e:
        raise _http(e) from None


def _http(e: ErreurResana) -> HTTPException:
    """L'erreur du service, rendue à l'écran avec son code. Un 401 du service (jeton refusé par
    Résana, ou Mes collections inconnu de lui) ne dit pas que la session de Mes collections est
    finie : il devient un 502, pour que l'écran ne déconnecte pas la personne."""
    if e.statut == 401:
        statut = 502
    elif 400 <= e.statut < 500 or e.statut in (503, 504):
        statut = e.statut
    else:
        statut = 502
    return HTTPException(status_code=statut, detail=e.detail())


def _refus(statut: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=statut, detail={"code": code, "message": message, "reessayable": False})


def _occupee(collection: str) -> bool:
    tache = _TACHES.get(collection)
    return tache is not None and not tache.done()


async def _demarrer(collection: str, travail: Awaitable[None]) -> None:
    """Lance la tâche de fond ; les tests la remplacent pour l'attendre."""
    tache = asyncio.ensure_future(travail)
    _TACHES[collection] = tache
    tache.add_done_callback(lambda _t: _TACHES.pop(collection, None) if _TACHES.get(collection) is _t else None)


# --- Parcourir --------------------------------------------------------------------------------


@router.get("/espaces")
async def espaces(authorization: str | None = Header(default=None), user: CurrentUser = Depends(current_user)):
    """Les espaces Résana de la personne. Peut ouvrir sa session (jusqu'à 90 s)."""
    try:
        rendu = await _client(authorization).espaces()
    except ErreurResana as e:
        raise _http(e) from None
    return {"espaces": [{"id": e.id, "nom": e.nom} for e in sorted(rendu, key=lambda e: e.nom.lower())]}


@router.get("/espaces/{espace}/dossiers")
async def dossiers(espace: str, recherche: str = Query("", max_length=200), authorization: str | None = Header(default=None), user: CurrentUser = Depends(current_user)):
    try:
        rendu = await _client(authorization).dossiers(espace, recherche)
    except ErreurResana as e:
        raise _http(e) from None
    return {"dossiers": [{"id": d.id, "titre": d.titre, "parent_id": d.parent_id, "chemin": d.chemin} for d in rendu]}


@router.get("/espaces/{espace}/apercu")
async def apercu(espace: str, dossier: str = Query(..., min_length=1, max_length=200), authorization: str | None = Header(default=None), user: CurrentUser = Depends(current_user)):
    """Ce que l'import emporterait : le nombre de documents et leur taille approchée."""
    try:
        docs = await _client(authorization).documents(espace, dossier)
    except ErreurResana as e:
        raise _http(e) from None
    tailles = [d.taille_approx_mo for d in docs if d.taille_approx_mo is not None]
    return {
        "total": len(docs),
        "taille_approx_mo": round(sum(tailles), 1) if tailles else None,
        "documents": [{"titre": d.titre, "chemin": d.chemin} for d in docs[:20]],
    }


# --- Importer et synchroniser ------------------------------------------------------------------


class AjoutResana(BaseModel):
    collection: str
    espace_id: str = Field(min_length=1, max_length=200)
    espace_nom: str = Field("", max_length=300)
    dossier_id: str = Field(min_length=1, max_length=200)
    dossier_chemin: str = Field("", max_length=1000)


async def _a_des_documents(collection: str) -> bool:
    async with async_session() as session:
        return (await session.execute(select(SourceFile.id).where(SourceFile.collection_name == collection).limit(1))).first() is not None


async def _est_publiee(collection: str) -> bool:
    async with async_session() as session:
        pub = await session.get(Publication, collection)
        return bool(pub and pub.state == "published")


async def _exiger_importable(col: dict, user: CurrentUser) -> None:
    if not user.sub or col.get("created_by") != user.sub:
        raise _refus(403, "reserve_au_createur", "Seule la personne qui a créé la collection peut y importer un dossier Résana.")
    if col.get("source_type") == SOURCE:
        raise _refus(409, "deja_reliee", "Cette collection est déjà reliée à un dossier Résana : synchronisez-la.")
    if col.get("scope") != "private" or col.get("scope_groups"):
        raise _refus(409, "collection_non_privee", "Un dossier Résana ne s'importe que dans une collection privée, sans groupe lecteur.")
    if await _a_des_documents(col["name"]):
        raise _refus(409, "collection_non_vide", "Un dossier Résana s'importe dans une collection vide : créez-en une pour lui.")
    if await _est_publiee(col["name"]):
        raise _refus(409, "collection_publiee", "Retirez d'abord la collection de l'assistant : une collection Résana n'y est pas publiée.")


def _exiger_importeur(col: dict, user: CurrentUser) -> None:
    if not user.sub or col.get("created_by") != user.sub:
        raise _refus(403, "reserve_a_l_importeur", "Seule la personne qui a importé ce dossier Résana peut le synchroniser (avec sa propre session Résana).")


def _travail(action: str, total: int) -> dict:
    return {"etat": "en_cours", "action": action, "debut": utcnow().isoformat(), "total": total, "faits": 0}


@router.post("/add")
async def ajouter(req: AjoutResana, authorization: str | None = Header(default=None), user: CurrentUser = Depends(current_user)):
    """Relier une collection (vide, privée) à un dossier Résana et lancer l'import."""
    await gerer_la_collection(req.collection, user)
    col = await get_collection(req.collection)
    if not col:
        raise HTTPException(status_code=404, detail=f"Collection '{req.collection}' not found")
    await _exiger_importable(col, user)
    if _occupee(req.collection):
        raise _refus(409, "travail_en_cours", "Un import est déjà en cours pour cette collection.")
    client = _client(authorization)
    try:
        docs = await client.documents(req.espace_id, req.dossier_id)
    except ErreurResana as e:
        raise _http(e) from None
    if not docs:
        raise _refus(400, "dossier_vide", "Ce dossier ne contient aucun document.")
    cfg = {
        "espace_id": req.espace_id,
        "espace_nom": req.espace_nom.strip() or req.espace_id,
        "dossier_id": req.dossier_id,
        "dossier_chemin": req.dossier_chemin.strip() or req.dossier_id,
        "documents": {},
        "last_sync_at": None,
        "travail": _travail("import", len(docs)),
    }
    # Privée d'abord, documents ensuite : rien de Résana n'est jamais lisible hors de la personne.
    await update_collection(req.collection, {"scope": "private", "scope_groups": [], "source_type": SOURCE, "source_url": "", "source_config_json": json.dumps(cfg)})
    await _demarrer(req.collection, _executer(req.collection, client, req.espace_id, docs, "import", user))
    return {"status": "import_lance", "collection": req.collection, "total": len(docs)}


@router.post("/sync/{collection}")
async def synchroniser(collection: str, authorization: str | None = Header(default=None), user: CurrentUser = Depends(current_user)):
    await gerer_la_collection(collection, user)
    col = await get_collection(collection)
    if not col:
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
    if col.get("source_type") != SOURCE:
        raise _refus(400, "pas_resana", "Cette collection n'est pas reliée à Résana.")
    _exiger_importeur(col, user)
    if _occupee(collection):
        raise _refus(409, "travail_en_cours", "Une synchronisation est déjà en cours pour cette collection.")
    cfg = await get_source_config(collection)
    client = _client(authorization)
    try:
        docs = await client.documents(cfg.get("espace_id", ""), cfg.get("dossier_id", ""))
    except ErreurResana as e:
        raise _http(e) from None
    cfg["travail"] = _travail("synchronisation", len(docs))
    await update_collection(collection, {"source_config_json": json.dumps(cfg)})
    await _demarrer(collection, _executer(collection, client, cfg.get("espace_id", ""), docs, "synchronisation", user))
    return {"status": "synchro_lancee", "collection": collection, "total": len(docs)}


@router.get("/status/{collection}", dependencies=[Depends(lire_la_collection)])
async def statut(collection: str, user: CurrentUser = Depends(current_user)):
    col = await get_collection(collection)
    if not col:
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
    cfg = await get_source_config(collection)
    travail = dict(cfg.get("travail") or {})
    if travail.get("etat") == "en_cours" and not _occupee(collection):
        # Le service a redémarré pendant la tâche : on le dit, une synchronisation reprend.
        travail["etat"] = "interrompu"
    est_importeur = col.get("source_type") == SOURCE and bool(user.sub) and col.get("created_by") == user.sub
    return {
        "collection": collection,
        "configured": col.get("source_type") == SOURCE,
        "espace_nom": cfg.get("espace_nom"),
        "dossier_chemin": cfg.get("dossier_chemin"),
        "documents": len(cfg.get("documents") or {}),
        "last_sync_at": cfg.get("last_sync_at"),
        "travail": travail or None,
        "est_importeur": est_importeur,
    }


# --- La tâche de fond ----------------------------------------------------------------------------


async def _ecrire_config(collection: str, **champs) -> None:
    if not await get_collection(collection):
        return
    cfg = await get_source_config(collection)
    cfg.update(champs)
    await update_collection(collection, {"source_config_json": json.dumps(cfg)})


async def _avancer(collection: str, faits: int) -> None:
    cfg = await get_source_config(collection)
    if isinstance(cfg.get("travail"), dict):
        cfg["travail"]["faits"] = faits
        await update_collection(collection, {"source_config_json": json.dumps(cfg)})


async def _rapatrier(collection: str, client: ClientExportResana, espace: str, docs: list[DocumentResana]) -> tuple[list[tuple[DocumentResana, Fichier]], list[dict]]:
    """Télécharge chaque document (quelques-uns à la fois). Une erreur bloquante arrête tout et
    remonte ; un refus propre au document l'écarte."""
    recus: dict[int, tuple[DocumentResana, Fichier]] = {}
    ecartes: list[dict] = []
    file = list(enumerate(docs))
    etat = {"octets": 0, "faits": 0, "erreur": None}

    async def ouvrier() -> None:
        while file and etat["erreur"] is None:
            rang, doc = file.pop(0)
            try:
                f = await client.fichier(doc, espace)
            except ErreurResana as e:
                if e.code in ERREURS_BLOQUANTES:
                    etat["erreur"] = e
                    return
                ecartes.append({"id": doc.id, "titre": doc.titre, "raison": e.message})
                continue
            etat["octets"] += len(f.contenu)
            if etat["octets"] > OCTETS_MAX_TOTAL:
                etat["erreur"] = ErreurResana(413, "trop_volumineux_total")
                return
            recus[rang] = (doc, f)
            etat["faits"] += 1
            if etat["faits"] % 10 == 0:
                await _avancer(collection, etat["faits"])

    await asyncio.gather(*(ouvrier() for _ in range(TELECHARGEMENTS_PARALLELES)))
    if etat["erreur"] is not None:
        raise etat["erreur"]
    return [recus[r] for r in sorted(recus)], ecartes


def _irrecevable(nom: str, contenu: bytes) -> str | None:
    """Pourquoi ce fichier ne s'indexerait pas, ou None."""
    nature = formats.nature(nom, contenu)
    if nature is None:
        return "format non pris en charge"
    if nature is formats.Nature.DOCUMENT:
        return "trop volumineux pour l'indexation" if len(contenu) > depot.DOCUMENT_MAX_OCTETS else None
    try:
        texte = depot.texte_ou_refus(contenu, nom)
    except HTTPException:
        return "texte illisible"
    return None if texte.strip() else "document vide"


def _nom_de(doc: DocumentResana, f: Fichier) -> str:
    """Le nom donné par le service au fichier ; celui de la liste s'il porte seul une extension."""
    if formats.extension(f.nom) or not formats.extension(doc.nom_fichier):
        return f.nom
    return doc.nom_fichier


def _url(doc: DocumentResana) -> str:
    return doc.url_consultation if doc.url_consultation.startswith("https://") else ""


def _strategie(col: dict) -> tuple[Strategy, Sensitivity]:
    try:
        strategie = Strategy(col.get("strategy") or "auto")
    except ValueError:
        strategie = Strategy.AUTO
    try:
        sensibilite = Sensitivity(col.get("sensitivity") or "public")
    except ValueError:
        sensibilite = Sensitivity.PUBLIC
    return strategie, sensibilite


async def _retirer(collection: str, fichiers: list[str]) -> None:
    if not fichiers:
        return
    async with async_session() as session:
        lignes = (await session.execute(select(SourceFile).where(SourceFile.collection_name == collection, SourceFile.filename.in_(fichiers)))).scalars().all()
        for sf in lignes:
            if sf.storage_path:
                Path(sf.storage_path).unlink(missing_ok=True)
            await session.delete(sf)
        await session.commit()


async def _reindexer(collection: str, col: dict) -> int:
    """Vide la partition et renvoie toutes les sources gardées (comme la réindexation) : sans
    identifiant de fichier OpenRAG, c'est la seule façon de retirer l'ancienne version."""
    strategie, sensibilite = _strategie(col)
    client = depot.OpenRAGClient()
    try:
        await client.delete_partition(collection)
    except Exception as e:  # noqa: BLE001 — une partition encore absente
        logger.info("résana %s : partition non vidée (%s)", collection, type(e).__name__)
    await client.create_partition(collection)
    async with async_session() as session:
        sources = (await session.execute(select(SourceFile).where(SourceFile.collection_name == collection))).scalars().all()
    envoyes = 0
    for sf in sources:
        chemin = Path(sf.storage_path or "")
        if not chemin.exists():
            logger.warning("résana %s : source %s absente du disque", collection, sf.id)
            continue
        try:
            await depot._ingest_content(collection, sf.filename, chemin.read_bytes(), strategie, sensibilite, source_path=sf.original_url or sf.storage_path)
            envoyes += 1
        except HTTPException as e:
            logger.warning("résana %s : source %s non indexée (%s)", collection, sf.id, e.status_code)
    return envoyes


async def _executer(collection: str, client: ClientExportResana, espace: str, docs: list[DocumentResana], action: str, user: CurrentUser) -> None:
    try:
        bilan = await _comparer_et_appliquer(collection, client, espace, docs, action)
    except ErreurResana as e:
        logger.info("résana %s : %s arrêté (%s)", collection, action, e.code)
        await _ecrire_config(collection, travail={"etat": "echec", "action": action, "fin": utcnow().isoformat(), **e.detail()})
        return
    except Exception as e:  # noqa: BLE001 — la tâche de fond ne doit rien laisser « en cours »
        logger.exception("résana %s : %s en échec", collection, action)
        await _ecrire_config(
            collection,
            travail={
                "etat": "echec",
                "action": action,
                "fin": utcnow().isoformat(),
                "code": "erreur_interne",
                "message": f"Erreur interne ({type(e).__name__}).",
                "reessayable": True,
            },
        )
        return
    await consigner(
        "synchronisation", collection, "synchro.terminee", user.sub, collection_name=collection, detail={"source": SOURCE, **{k: v for k, v in bilan.items() if isinstance(v, int)}}
    )


async def _comparer_et_appliquer(collection: str, client: ClientExportResana, espace: str, docs: list[DocumentResana], action: str) -> dict:
    col = await get_collection(collection)
    if not col:
        raise ErreurResana(404, "introuvable")
    cfg = await get_source_config(collection)
    connus: dict[str, dict] = dict(cfg.get("documents") or {})
    recus, ecartes = await _rapatrier(collection, client, espace, docs)

    pris = {str(v.get("fichier", "")).lower() for v in connus.values()}
    gardes: dict[str, dict] = {}
    a_ecrire: list[tuple[str, bytes, str]] = []
    condensats: dict[str, str] = {}
    ajoutes = modifies = inchanges = 0
    for doc, f in recus:
        ancien = connus.get(doc.id)
        nom = ancien["fichier"] if ancien else _nom_de(doc, f)
        raison = _irrecevable(nom, f.contenu)
        if raison:
            ecartes.append({"id": doc.id, "titre": doc.titre, "raison": raison})
            continue
        if f.sha256 in condensats:
            ecartes.append({"id": doc.id, "titre": doc.titre, "raison": f"même contenu que « {condensats[f.sha256]} »"})
            continue
        condensats[f.sha256] = doc.titre
        if not ancien:
            nom = nom_unique(nom, doc.id, pris)
        gardes[doc.id] = {"sha256": f.sha256, "fichier": nom, "url": _url(doc), "titre": doc.titre, "version_fichier": doc.version_fichier, "modifie_le": doc.modifie_le}
        if ancien and ancien.get("sha256") == f.sha256:
            inchanges += 1
        else:
            a_ecrire.append((nom, f.contenu, _url(doc)))
            if ancien:
                modifies += 1
            else:
                ajoutes += 1
    del recus
    retires = [v["fichier"] for k, v in connus.items() if k not in gardes]

    if a_ecrire or retires:
        await _retirer(collection, retires)
        for nom, contenu, url in a_ecrire:
            await depot._enregistrer_source(collection, nom, contenu, depot.STRATEGIE_DOCUMENT, 0, url)
        await _reindexer(collection, col)

    bilan = {"ajoutes": ajoutes, "modifies": modifies, "retires": len(retires), "inchanges": inchanges, "ecartes": len(ecartes)}
    await _ecrire_config(
        collection,
        documents=gardes,
        last_sync_at=utcnow().isoformat(),
        travail={
            "etat": "termine" if (a_ecrire or retires) else "a_jour",
            "action": action,
            "fin": utcnow().isoformat(),
            "total": len(docs),
            "faits": len(docs),
            **bilan,
            "documents_ecartes": [{"titre": e["titre"], "raison": e["raison"]} for e in ecartes[:ECARTES_MAX]],
        },
    )
    return bilan
