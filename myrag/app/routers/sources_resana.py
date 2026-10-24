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
import hashlib
import json
import logging
import re
import shutil
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth import CurrentUser, current_user
from app.config import settings
from app.database import async_session
from app.models.db import Publication, SourceFile, utcnow
from app.routers import ingest as depot
from app.routers._commun import capacite
from app.routers._droits import gerer_la_collection, lire_la_collection
from app.services import formats, resana_perimetre
from app.services.chunker import Sensitivity, Strategy
from app.services.collectif_store import consigner
from app.services.collection_store import get_collection, get_source_config, update_collection
from app.services.connectors.resana import ClientExportResana, DocumentResana, EnPreparation, ErreurResana, nom_unique

logger = logging.getLogger("myrag.sources.resana")

router = APIRouter(prefix="/resana", tags=["Sources"], dependencies=[Depends(capacite("resana"))])

SOURCE = "resana"
#: Les fichiers reçus attendent sur le disque (jamais en mémoire) que la passe se termine : plus
#: de plafond par passe. Seule garde : laisser au moins cette place libre sur le volume.
PLACE_LIBRE_MIN = 1024 * 1024 * 1024
TELECHARGEMENTS_PARALLELES = 4
#: Documents confiés à OpenRAG en même temps : au-delà, il ne suit plus (« pas fini de lire en
#: 30 minutes » pour des centaines de PDF envoyés d'un coup).
ENVOIS_PARALLELES = 4
#: Les erreurs qui arrêtent tout ; les autres (droits, taille d'un document) n'écartent que lui.
ERREURS_BLOQUANTES = {"session_absente", "jeton_invalide", "appelant_inconnu", "resana_indisponible", "service_injoignable", "reponse_illisible", "disque_plein"}
#: Ce que l'écran garde des documents écartés (le reste se compte).
ECARTES_MAX = 50

MESSAGE_DOSSIER_VIDE = "Ce dossier ne contient aucun document."
MESSAGE_SELECTION_VIDE = "Aucun document dans les dossiers choisis : ajoutez au moins un dossier à la sélection."
MESSAGE_SYNCHRO_VIDE = "Le dossier Résana est vide : rien n'est retiré de la collection. Supprimez-la si c'est voulu."

#: Le client du service Résana d'une tâche en cours, par collection : la page de l'importeur lui
#: transmet son jeton frais à chaque lecture de l'état (`relayer_jeton`), pour que le téléchargement
#: survive à l'expiration du jeton de départ (15 min) tant que la page est ouverte.
_CLIENTS: dict[str, ClientExportResana] = {}

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
    """Ce que l'import emporterait : le nombre de documents et leur taille approchée. Un grand
    dossier se prépare côté service : 202 avec l'avancement, l'écran rappelle (Retry-After)."""
    try:
        docs = await _client(authorization).documents(espace, dossier)
    except EnPreparation as e:
        return JSONResponse(status_code=202, content={"en_preparation": True, "dossiers_lus": e.dossiers_lus, "dossiers": e.dossiers}, headers={"Retry-After": str(int(e.attente))})
    except ErreurResana as e:
        raise _http(e) from None
    tailles = [d.taille_approx_mo for d in docs if d.taille_approx_mo is not None]
    return {
        "total": len(docs),
        "taille_approx_mo": round(sum(tailles), 1) if tailles else None,
        "documents": [{"titre": d.titre, "chemin": d.chemin} for d in docs[:20]],
    }


@router.get("/espaces/{espace}/inventaire")
async def inventaire(
    espace: str, dossier: str = Query(..., min_length=1, max_length=200), authorization: str | None = Header(default=None), user: CurrentUser = Depends(current_user)
):
    """Le dossier choisi, sous-dossier par sous-dossier : combien de documents chacun contient,
    pour n'indexer que ce qui sert. 202 tant que le service prépare la liste d'un grand dossier."""
    client = _client(authorization)
    try:
        docs = await client.documents(espace, dossier)
        dossiers = await client.dossiers(espace)
    except EnPreparation as e:
        return JSONResponse(status_code=202, content={"en_preparation": True, "dossiers_lus": e.dossiers_lus, "dossiers": e.dossiers}, headers={"Retry-After": str(int(e.attente))})
    except ErreurResana as e:
        raise _http(e) from None
    a_la_racine, noeuds = resana_perimetre.inventaire(dossier, dossiers, docs)
    tailles = [d.taille_approx_mo for d in docs if d.taille_approx_mo is not None]
    return {
        "total": len(docs),
        "taille_approx_mo": round(sum(tailles), 1) if tailles else None,
        "documents_a_la_racine": a_la_racine,
        "dossiers": [n.vers_dict() for n in noeuds],
    }


@router.get("/existant")
async def existant(
    espace: str = Query(..., min_length=1, max_length=200),
    dossier: str = Query(..., min_length=1, max_length=200),
    chemin: str = Query("", max_length=1000),
    user: CurrentUser = Depends(current_user),
):
    """Les collections Résana de la personne qui couvrent déjà ce dossier, un dossier parent ou un
    sous-dossier : on propose de les reprendre plutôt que d'en créer une de plus. Seulement les
    siennes (règle v1 : une collection Résana est privée ; on ne révèle pas celles des autres)."""
    from app.services.collection_store import list_collections

    meme, parents, enfants = [], [], []
    cible = chemin.strip().rstrip("/") if chemin else ""
    for col in await list_collections(include_archived=False):
        if col.get("source_type") != SOURCE or not user.sub or col.get("created_by") != user.sub:
            continue
        cfg = await get_source_config(col["name"])
        if str(cfg.get("espace_id")) != espace:
            continue
        ligne = {"collection": col["name"], "titre": col.get("titre") or col["name"], "dossier_chemin": cfg.get("dossier_chemin"), **resana_perimetre.couverture(cfg)}
        autre = str(cfg.get("dossier_chemin") or "").rstrip("/")
        if str(cfg.get("dossier_id")) == dossier:
            meme.append(ligne)
        elif cible and autre and cible.startswith(autre + " / "):
            parents.append(ligne)
        elif cible and autre and autre.startswith(cible + " / "):
            enfants.append(ligne)
    return {"meme_dossier": meme, "dossier_parent": parents, "sous_dossiers": enfants}


# --- Importer et synchroniser ------------------------------------------------------------------


class AjoutResana(BaseModel):
    collection: str
    espace_id: str = Field(min_length=1, max_length=200)
    espace_nom: str = Field("", max_length=300)
    dossier_id: str = Field(min_length=1, max_length=200)
    dossier_chemin: str = Field("", max_length=1000)
    #: Les sous-dossiers à ne pas indexer (et tout ce qu'ils contiennent).
    exclus: list[str] = Field(default_factory=list, max_length=2000)


class SynchroResana(BaseModel):
    #: Absent : le périmètre ne change pas ; présent : il est remplacé avant la passe.
    exclus: list[str] | None = Field(default=None, max_length=2000)
    #: Vérification complète : retélécharger chaque document et comparer son empreinte, même si
    #: Résana annonce la même date et la même version (rare : un contenu changé sans nouvelle date).
    complet: bool = False


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


def _travail(action: str, docs: list[DocumentResana] | None) -> dict:
    """L'état d'un travail qui commence : la liste est prête (téléchargement), ou se prépare encore."""
    phase = "telechargement" if docs is not None else "preparation"
    return {"etat": "en_cours", "action": action, "phase": phase, "debut": utcnow().isoformat(), "total": len(docs or []), "faits": 0}


async def _liste_si_prete(client: ClientExportResana, espace: str, dossier: str) -> list[DocumentResana] | None:
    """La liste du dossier si le service l'a (aussitôt, ou en cache après l'aperçu) ; None si elle se
    prépare encore : la tâche de fond l'attendra. Les autres erreurs reviennent à l'écran."""
    try:
        return await client.documents(espace, dossier)
    except EnPreparation:
        return None
    except ErreurResana as e:
        raise _http(e) from None


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
    docs = await _liste_si_prete(client, req.espace_id, req.dossier_id)
    if docs is not None and not docs:
        raise _refus(400, "dossier_vide", MESSAGE_DOSSIER_VIDE)
    cfg = {
        "espace_id": req.espace_id,
        "espace_nom": req.espace_nom.strip() or req.espace_id,
        "dossier_id": req.dossier_id,
        "dossier_chemin": req.dossier_chemin.strip() or req.dossier_id,
        "documents": {},
        "last_sync_at": None,
        "perimetre": {"exclus": sorted({e for e in req.exclus if e and e != req.dossier_id})},
        "travail": _travail("import", docs),
    }
    # Privée d'abord, documents ensuite : rien de Résana n'est jamais lisible hors de la personne.
    await update_collection(req.collection, {"scope": "private", "scope_groups": [], "source_type": SOURCE, "source_url": "", "source_config_json": json.dumps(cfg)})
    await _demarrer(req.collection, _executer(req.collection, client, req.espace_id, req.dossier_id, docs, "import", user))
    return {"status": "import_lance", "collection": req.collection, "total": len(docs) if docs is not None else None}


@router.post("/sync/{collection}")
async def synchroniser(collection: str, corps: SynchroResana | None = None, authorization: str | None = Header(default=None), user: CurrentUser = Depends(current_user)):
    """Relire le dossier et réindexer ce qui a changé ; `exclus` change d'abord le périmètre
    (un dossier ajouté s'indexe, un dossier retiré sort de l'index) ; `complet` retélécharge tout
    pour comparer les empreintes."""
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
    espace, dossier = str(cfg.get("espace_id", "")), str(cfg.get("dossier_id", ""))
    docs = await _liste_si_prete(client, espace, dossier)
    if docs is not None and not docs:
        raise _refus(409, "dossier_vide", MESSAGE_SYNCHRO_VIDE)
    if corps is not None and corps.exclus is not None:
        cfg["perimetre"] = {"exclus": sorted({e for e in corps.exclus if e and e != dossier})}
    cfg["travail"] = _travail("synchronisation", docs)
    await update_collection(collection, {"source_config_json": json.dumps(cfg)})
    complet = bool(corps and corps.complet)
    await _demarrer(collection, _executer(collection, client, espace, dossier, docs, "synchronisation", user, complet=complet))
    return {"status": "synchro_lancee", "collection": collection, "total": len(docs) if docs is not None else None}


@router.get("/status/{collection}", dependencies=[Depends(lire_la_collection)])
async def statut(collection: str, authorization: str | None = Header(default=None), user: CurrentUser = Depends(current_user)):
    col = await get_collection(collection)
    if not col:
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
    if col.get("source_type") == SOURCE and user.sub and col.get("created_by") == user.sub:
        relayer_jeton(collection, authorization)
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
        "espace_id": cfg.get("espace_id") if est_importeur else None,
        "dossier_id": cfg.get("dossier_id") if est_importeur else None,
        "exclus": list((cfg.get("perimetre") or {}).get("exclus") or []) if est_importeur else [],
        **resana_perimetre.couverture({**cfg, "travail": travail}),
        "avis": resana_perimetre.avis(
            collection,
            {**cfg, "travail": travail},
            est_importeur=est_importeur,
            maintenant=datetime.now(timezone.utc),
            seuil_jours=settings.resana_fraicheur_jours,
            titre=col.get("titre") or "",
        ),
    }


def relayer_jeton(collection: str, authorization: str | None) -> bool:
    """Le jeton frais de la page de l'importeur passe à sa tâche en cours (s'il y en a une). Appelé
    seulement pour l'importeur : c'est son propre jeton, la tâche agit déjà en son nom. Le jeton
    n'est ni écrit ni journalisé. Rend True s'il a été transmis."""
    client = _CLIENTS.get(collection)
    if client is None or not authorization or not authorization.lower().startswith("bearer "):
        return False
    return client.renouveler_jeton(authorization.split(" ", 1)[1])


async def avis_pour(col: dict | None, user: CurrentUser) -> dict | None:
    """L'invitation à mettre à jour l'index Résana de `col`, pour cette personne, ou None :
    capacité éteinte, autre source, autre personne que l'importeur, index récent."""
    if not col or col.get("source_type") != SOURCE or not user.sub or col.get("created_by") != user.sub:
        return None
    from app.services import capacites

    if (await capacites.lire_async()).get("resana") is not True:
        return None
    cfg = await get_source_config(col["name"])
    travail = dict(cfg.get("travail") or {})
    if travail.get("etat") == "en_cours" and not _occupee(col["name"]):
        travail["etat"] = "interrompu"
    return resana_perimetre.avis(
        col["name"],
        {**cfg, "travail": travail},
        est_importeur=True,
        maintenant=datetime.now(timezone.utc),
        seuil_jours=settings.resana_fraicheur_jours,
        titre=col.get("titre") or "",
    )


# --- La tâche de fond ----------------------------------------------------------------------------


async def _ecrire_config(collection: str, **champs) -> None:
    if not await get_collection(collection):
        return
    cfg = await get_source_config(collection)
    cfg.update(champs)
    await update_collection(collection, {"source_config_json": json.dumps(cfg)})


async def _suivre(collection: str, **champs) -> None:
    """Met à jour l'avancement du travail en cours (lu par /status)."""
    cfg = await get_source_config(collection)
    if isinstance(cfg.get("travail"), dict):
        cfg["travail"].update(champs)
        await update_collection(collection, {"source_config_json": json.dumps(cfg)})


def a_relire(doc: DocumentResana, ancien: dict | None) -> bool:
    """Faut-il retélécharger ce document ? Oui s'il est nouveau, si Résana annonce une autre date ou
    une autre version, ou si la fiche gardée est incomplète. Sinon, rien à télécharger : la liste
    du dossier suffit (l'empreinte ne se vérifie qu'en vérification complète)."""
    if not ancien or not ancien.get("sha256") or not ancien.get("file_id"):
        return True
    if not doc.modifie_le and not doc.version_fichier:
        return True  # Résana ne dit rien : seule l'empreinte peut trancher
    return (doc.version_fichier, doc.modifie_le) != (ancien.get("version_fichier"), ancien.get("modifie_le"))


def identifiant_dans_l_index(ident: str, sha256: str) -> str:
    """L'identifiant du document chez OpenRAG, déduit du document Résana et de son contenu : un
    renvoi après une coupure retombe sur le même fichier (OpenRAG répond 409) au lieu d'en créer
    un second ; une nouvelle version a un autre identifiant."""
    propre = re.sub(r"[^A-Za-z0-9_.:-]", "", ident)[:48] or "doc"
    return f"resana-{propre}-{sha256[:16]}"


def _ordre(docs: list[DocumentResana], connus: dict[str, dict]) -> list[DocumentResana]:
    """Les nouveaux d'abord, puis les autres : si la session s'arrête en route, la passe suivante
    reprend là où c'est utile."""
    return sorted(docs, key=lambda d: 0 if d.id not in connus else 1)


@dataclass
class Recu:
    """Un document reçu, nouveau ou changé : son contenu attend sur le disque le temps de partir
    chez OpenRAG, puis il est effacé (Mes collections n'en garde que l'empreinte)."""

    doc: DocumentResana
    nom: str
    sha256: str
    chemin: Path
    taille: int


@dataclass
class Rapatriement:
    """Ce que le téléchargement a rapporté. `recus` : contenus nouveaux ou changés, en attente sur
    le disque ; `identiques` : documents relus sans changement de contenu ; `erreur` : ce qui l'a
    arrêté en route."""

    recus: list[Recu] = field(default_factory=list)
    identiques: list[DocumentResana] = field(default_factory=list)
    ecartes: list[dict] = field(default_factory=list)
    erreur: ErreurResana | None = None


def _attente(collection: str) -> Path:
    """Le dossier où attendent les fichiers d'une passe (vidé au début et à la fin de chaque passe)."""
    return Path(settings.data_dir) / "_resana_attente" / collection


def _place_libre(chemin: Path) -> int:
    return shutil.disk_usage(chemin).free


async def _rapatrier(collection: str, client: ClientExportResana, espace: str, docs: list[DocumentResana], connus: dict[str, dict]) -> Rapatriement:
    """Télécharge les documents à relire, quelques-uns à la fois. Un contenu identique au précédent
    est jeté aussitôt ; un contenu nouveau ou changé attend sur le disque, pas en mémoire. Une
    erreur bloquante (ou un disque presque plein) arrête le téléchargement : ce qui est déjà reçu
    reste utilisable."""
    r = Rapatriement()
    file = _ordre(docs, connus)
    etat = {"faits": 0}
    attente = _attente(collection)
    attente.mkdir(parents=True, exist_ok=True)

    async def ouvrier() -> None:
        while file and r.erreur is None:
            doc = file.pop(0)
            try:
                f = await client.fichier(doc, espace)
            except ErreurResana as e:
                if e.code in ERREURS_BLOQUANTES:
                    r.erreur = r.erreur or e
                    return
                r.ecartes.append({"id": doc.id, "titre": doc.titre, "raison": e.message})
                continue
            ancien = connus.get(doc.id) or {}
            if ancien.get("sha256") == f.sha256 and ancien.get("file_id"):
                r.identiques.append(doc)
            else:
                if _place_libre(attente) - len(f.contenu) < PLACE_LIBRE_MIN:
                    r.erreur = r.erreur or ErreurResana(507, "disque_plein", reessayable=True)
                    return
                chemin = attente / f"{len(r.recus):05d}-{hashlib.sha256(doc.id.encode()).hexdigest()[:16]}"
                await asyncio.to_thread(chemin.write_bytes, f.contenu)
                r.recus.append(Recu(doc=doc, nom=f.nom, sha256=f.sha256, chemin=chemin, taille=len(f.contenu)))
            etat["faits"] += 1
            if etat["faits"] % 10 == 0:
                await _suivre(collection, faits=etat["faits"])

    await asyncio.gather(*(ouvrier() for _ in range(TELECHARGEMENTS_PARALLELES)))
    rang = {d.id: i for i, d in enumerate(docs)}
    r.recus.sort(key=lambda x: rang[x.doc.id])
    return r


def _irrecevable(nom: str, contenu: bytes) -> str | None:
    """Pourquoi ce fichier ne s'indexerait pas, ou None."""
    nature = formats.nature(nom, contenu)
    if nature is None:
        return "format non pris en charge"
    if len(contenu) > depot.DOCUMENT_MAX_OCTETS:
        return "trop volumineux pour l'indexation"
    if nature is formats.Nature.DOCUMENT:
        return None
    try:
        texte = depot.texte_ou_refus(contenu, nom)
    except HTTPException:
        return "texte illisible"
    return None if texte.strip() else "document vide"


def _nom_de(doc: DocumentResana, nom_recu: str) -> str:
    """Le nom donné par le service au fichier ; celui de la liste s'il porte seul une extension."""
    if formats.extension(nom_recu) or not formats.extension(doc.nom_fichier):
        return nom_recu
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


async def _noter_sources(collection: str, documents: dict[str, dict]) -> None:
    """Une ligne `SourceFile` par document indexé, SANS copie du fichier (storage_path vide) : la
    liste des sources, la date du dernier dépôt et la purge restent justes ; l'original est dans
    Résana (`original_url`), le texte dans OpenRAG."""
    async with async_session() as session:
        lignes = {sf.filename: sf for sf in (await session.execute(select(SourceFile).where(SourceFile.collection_name == collection))).scalars().all()}
        voulus = {d["fichier"]: d for d in documents.values()}
        for nom, sf in lignes.items():
            if nom not in voulus:
                if sf.storage_path:
                    Path(sf.storage_path).unlink(missing_ok=True)
                await session.delete(sf)
        for nom, d in voulus.items():
            sf = lignes.get(nom) or SourceFile(collection_name=collection, filename=nom)
            if nom not in lignes:
                session.add(sf)
            sf.original_url = d.get("url") or ""
            sf.storage_path = ""
            sf.file_size = int(d.get("taille") or 0)
            sf.checksum = d.get("sha256") or ""
            sf.strategy_used = depot.STRATEGIE_DOCUMENT
            sf.last_indexed_at = utcnow()
        await session.commit()


async def _retirer_de_l_index(collection: str, identifiants: list[str]) -> None:
    indexeur = depot._indexeur()
    for identifiant in identifiants:
        try:
            await indexeur.retirer(collection, identifiant)
        except Exception as e:  # noqa: BLE001 — un retrait raté laisse un passage en trop, pas une panne
            logger.warning("résana %s : document %s non retiré de l'index (%s)", collection, identifiant, type(e).__name__)


async def _envoyer(collection: str, a_envoyer: list[tuple[str, Recu, dict]], sensibilite: Sensitivity) -> dict[str, tuple[str | None, str | None]]:
    """Confie les documents à OpenRAG, ENVOIS_PARALLELES à la fois, chacun suivi jusqu'au bout (un
    travail par document, visible dans les travaux). Rend {id Résana: (file_id, erreur)}. Chaque
    fichier en attente est effacé dès qu'il est parti."""
    from app.services.job_store import create_job, update_job

    verrou = asyncio.Semaphore(ENVOIS_PARALLELES)
    rendu: dict[str, tuple[str | None, str | None]] = {}
    faits = {"n": 0}

    async def un(nom: str, recu: Recu, meta: dict) -> None:
        async with verrou:
            job = await create_job(collection=collection, filename=nom, strategy=depot.STRATEGIE_DOCUMENT, sensitivity=sensibilite, source_path=meta.get("url") or "")
            await update_job(job["job_id"], total_chunks=1)
            contenu = await asyncio.to_thread(recu.chemin.read_bytes)
            recu.chemin.unlink(missing_ok=True)
            rendu[recu.doc.id] = await depot._indexer_document_background(
                job["job_id"], collection, nom, contenu, metadata=meta, file_id=identifiant_dans_l_index(recu.doc.id, recu.sha256)
            )
            del contenu
            faits["n"] += 1
            await _suivre(collection, faits=faits["n"])

    await asyncio.gather(*(un(nom, recu, meta) for nom, recu, meta in a_envoyer))
    return rendu


async def _comparer_et_appliquer(collection: str, client: ClientExportResana, espace: str, docs: list[DocumentResana], action: str, *, complet: bool = False) -> dict:
    col = await get_collection(collection)
    if not col:
        raise ErreurResana(404, "introuvable")
    cfg = await get_source_config(collection)
    connus: dict[str, dict] = dict(cfg.get("documents") or {})
    _, sensibilite = _strategie(col)

    # Ce que la liste suffit à dire : inchangés (même date, même version), et à relire.
    a_relire_ = [d for d in docs if complet or a_relire(d, connus.get(d.id))]
    stables = [d for d in docs if d not in a_relire_]
    await _suivre(collection, phase="telechargement", total=len(a_relire_), faits=0, inchanges_annonces=len(stables))
    r = await _rapatrier(collection, client, espace, a_relire_, connus)
    if r.erreur is not None and not r.recus and not r.identiques:
        raise r.erreur
    # Arrêté en route (session expirée, disque) : on garde ce qui est arrivé, sans rien retirer ;
    # les documents non relus restent dans leur dernière version.
    partiel = r.erreur is not None

    gardes: dict[str, dict] = {}
    for doc in stables:
        gardes[doc.id] = {**connus[doc.id], "url": _url(doc) or connus[doc.id].get("url", ""), "titre": doc.titre}
    for doc in r.identiques:
        gardes[doc.id] = {
            **connus[doc.id],
            "url": _url(doc) or connus[doc.id].get("url", ""),
            "titre": doc.titre,
            "version_fichier": doc.version_fichier,
            "modifie_le": doc.modifie_le,
        }
    pris = {str(v.get("fichier", "")).lower() for v in connus.values()}
    condensats = {v["sha256"]: v.get("titre", "") for v in gardes.values() if v.get("sha256")}
    ecartes = list(r.ecartes)
    a_envoyer: list[tuple[str, Recu, dict]] = []
    a_retirer: list[str] = []
    ajoutes = modifies = 0
    for recu in r.recus:
        doc = recu.doc
        ancien = connus.get(doc.id)
        nom = ancien["fichier"] if ancien and ancien.get("fichier") else _nom_de(doc, recu.nom)
        raison = _irrecevable(nom, await asyncio.to_thread(recu.chemin.read_bytes))
        if raison is None and recu.sha256 in condensats:
            raison = f"même contenu que « {condensats[recu.sha256]} »"
        if raison:
            ecartes.append({"id": doc.id, "titre": doc.titre, "raison": raison})
            if ancien and ancien.get("file_id"):
                a_retirer.append(ancien["file_id"])  # son ancienne version ne doit pas rester seule
            continue
        condensats[recu.sha256] = doc.titre
        if not ancien:
            nom = nom_unique(nom, doc.id, pris)
        if ancien and ancien.get("file_id"):
            a_retirer.append(ancien["file_id"])
        meta = {"url": _url(doc)} if _url(doc) else {}
        a_envoyer.append((nom, recu, meta))
        gardes[doc.id] = {
            "sha256": recu.sha256,
            "fichier": nom,
            "url": _url(doc),
            "titre": doc.titre,
            "version_fichier": doc.version_fichier,
            "modifie_le": doc.modifie_le,
            "taille": recu.taille,
        }
        if ancien:
            modifies += 1
        else:
            ajoutes += 1
    if partiel:
        for k, v in connus.items():
            gardes.setdefault(k, v)
        disparus: list[dict] = []
    else:
        disparus = [v for k, v in connus.items() if k not in gardes]
    a_retirer += [v["file_id"] for v in disparus if v.get("file_id")]

    # Les anciennes versions et les disparus sortent d'OpenRAG, document par document : la
    # partition n'est jamais vidée, la recherche continue pendant la mise à jour.
    try:
        await depot._indexeur().preparer(collection)
    except Exception:  # noqa: BLE001 — elle existe déjà, ou chaque envoi dira son échec
        pass
    await _retirer_de_l_index(collection, a_retirer)
    if a_envoyer:
        await _suivre(collection, phase="indexation", total=len(a_envoyer), faits=0)
    envois = await _envoyer(collection, a_envoyer, sensibilite)
    en_erreur = 0
    for ident, (file_id, erreur) in envois.items():
        if file_id:
            gardes[ident]["file_id"] = file_id
        if erreur:
            en_erreur += 1
            gardes[ident]["erreur"] = erreur
        else:
            gardes[ident].pop("erreur", None)
    # Un document qu'OpenRAG n'a même pas reçu n'est pas dans l'index : on l'oublie, la passe
    # suivante le renverra.
    for ident in [i for i, (file_id, _) in envois.items() if not file_id]:
        gardes.pop(ident, None)
    await _noter_sources(collection, gardes)

    bilan = {
        "ajoutes": ajoutes,
        "modifies": modifies,
        "retires": len(disparus),
        "inchanges": len(stables) + len(r.identiques),
        "ecartes": len(ecartes),
        "en_erreur": en_erreur,
    }
    travail = {
        "etat": "partiel" if partiel else ("termine" if (a_envoyer or disparus or a_retirer) else "a_jour"),
        "action": action,
        "complet": complet,
        "fin": utcnow().isoformat(),
        "total": len(docs),
        "faits": len(docs),
        **bilan,
        "documents_ecartes": [{"titre": e["titre"], "raison": e["raison"]} for e in ecartes[:ECARTES_MAX]],
    }
    champs: dict = {"documents": gardes, "travail": travail}
    if partiel and r.erreur is not None:
        travail.update({k: v for k, v in r.erreur.detail().items() if k in ("code", "message", "url_connexion")})
    else:
        champs["last_sync_at"] = utcnow().isoformat()
    await _ecrire_config(collection, **champs)
    return bilan


async def _filtrer(collection: str, client: ClientExportResana, espace: str, docs: list[DocumentResana]) -> list[DocumentResana]:
    """Le périmètre appliqué : sans exclusion, tout le dossier ; sinon l'arbre des dossiers dit ce
    que contient chaque dossier exclu."""
    exclus = list(((await get_source_config(collection)).get("perimetre") or {}).get("exclus") or [])
    if not exclus:
        return docs
    effectifs = resana_perimetre.exclus_effectifs(exclus, await client.dossiers(espace))
    return resana_perimetre.dans_le_perimetre(docs, effectifs)


async def _executer(
    collection: str, client: ClientExportResana, espace: str, dossier: str, docs: list[DocumentResana] | None, action: str, user: CurrentUser, *, complet: bool = False
) -> None:
    # Le dossier d'attente d'une passe précédente (service arrêté en route) ne sert plus.
    shutil.rmtree(_attente(collection), ignore_errors=True)
    _CLIENTS[collection] = client
    try:
        await _executer_passe(collection, client, espace, dossier, docs, action, user, complet=complet)
    finally:
        if _CLIENTS.get(collection) is client:
            del _CLIENTS[collection]
        shutil.rmtree(_attente(collection), ignore_errors=True)


async def _executer_passe(
    collection: str, client: ClientExportResana, espace: str, dossier: str, docs: list[DocumentResana] | None, action: str, user: CurrentUser, *, complet: bool = False
) -> None:
    try:
        if docs is None:

            async def suivi(e: EnPreparation) -> None:
                await _suivre(collection, dossiers_lus=e.dossiers_lus, dossiers=e.dossiers)

            docs = await client.documents(espace, dossier, attendre=True, suivi=suivi)
            if not docs:
                raise ErreurResana(400, "dossier_vide", MESSAGE_DOSSIER_VIDE)
        disponibles = len(docs)
        docs = await _filtrer(collection, client, espace, docs)
        if not docs:
            raise ErreurResana(400, "selection_vide", MESSAGE_SELECTION_VIDE)
        await _ecrire_config(collection, documents_disponibles=disponibles, documents_perimetre=len(docs))
        await _suivre(collection, phase="telechargement", total=len(docs))
        bilan = await _comparer_et_appliquer(collection, client, espace, docs, action, complet=complet)
    except ErreurResana as e:
        logger.info("résana %s : %s arrêté (%s)", collection, action, e.code)
        detail = e.detail()
        if e.code == "dossier_vide":
            detail["message"] = MESSAGE_DOSSIER_VIDE
        elif e.code == "selection_vide":
            detail["message"] = MESSAGE_SELECTION_VIDE
        await _ecrire_config(collection, travail={"etat": "echec", "action": action, "fin": utcnow().isoformat(), **detail})
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
