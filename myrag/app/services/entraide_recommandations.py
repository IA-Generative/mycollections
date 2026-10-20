"""Avant de publier un appel, le réseau montre ce qui existe déjà : les collections et les
assistants que la personne peut lire et qui ressemblent à l'appel, et les rôles — anonymes — de
ceux qui ont soutenu une demande voisine. L'apparieur est celui du moteur des assistants (sac de
mots par défaut, embeddings si configurés)."""

from __future__ import annotations

from sqlalchemy import select

from app.auth import CurrentUser
from app.database import async_session
from app.harnais.contrat import FicheAssistant
from app.models.db import Soutien
from app.services import assistant_droits as droits
from app.services import assistant_recherche, assistant_store, collectif_store, collection_store, nommage

SEUIL = 0.15  # en deçà, la ressemblance n'est que des mots vides en commun
MAX_PAR_FAMILLE = 5


def _texte(titre: str, description: str) -> str:
    return f"{titre}. {description}".strip()


async def _appariees(texte: str, candidats: list[tuple[str, str]]) -> list[tuple[str, float]]:
    if not candidats:
        return []
    scores = await assistant_recherche.apparieur().apparier(texte, candidats)
    return [(i, s) for i, s in scores if s >= SEUIL][:MAX_PAR_FAMILLE]


async def _collections(texte: str, user: CurrentUser) -> list[dict]:
    lisibles = {c["name"]: c for c in await collection_store.list_collections() if droits.lisible(c, user)}
    candidats = [(n, _texte(nommage.titre_de(c), c.get("description") or "")) for n, c in lisibles.items()]
    return [
        {"type": "collection", "id": n, "titre": nommage.titre_de(lisibles[n]), "description": lisibles[n].get("description") or "", "score": s, "vers": f"/c/{n}"}
        for n, s in await _appariees(texte, candidats)
    ]


async def _assistants(texte: str, user: CurrentUser, hash_: str, superadmin: bool) -> list[dict]:
    visibles: dict[str, dict] = {}
    for a in await assistant_store.lister():
        if a.get("collection_name") or a.get("version_publiee") is None:
            continue  # le miroir d'une collection est déjà recommandé comme collection
        ligne = await assistant_store.lire(a["id"])
        voir, _, _ = await droits.droits(FicheAssistant.model_validate(ligne["fiche"]), ligne.get("cree_par_hash"), user=user, hash_=hash_, superadmin=superadmin)
        if voir:
            visibles[a["id"]] = a
    candidats = [(i, _texte(a["titre"], a.get("description") or "")) for i, a in visibles.items()]
    return [
        {"type": "assistant", "id": i, "titre": visibles[i]["titre"], "description": visibles[i].get("description") or "", "score": s, "vers": f"/assistants/{i}"}
        for i, s in await _appariees(texte, candidats)
    ]


async def _roles_des_soutiens(texte: str, hash_: str, ignorer: str | None) -> list[dict]:
    """Les demandes voisines et, pour chacune, combien de personnes tiennent quel rôle — sans identité."""
    demandes = [d for d in await collectif_store.lister_demandes(hash_) if d.etat != "close" and d.id != ignorer]
    par_id = {d.id: d for d in demandes}
    sortie = []
    for ident, score in await _appariees(texte, [(d.id, _texte(d.titre, d.usage)) for d in demandes]):
        async with async_session() as session:
            roles = (await session.execute(select(Soutien.role).where(Soutien.demande_id == ident))).scalars().all()
        decompte: dict[str, int] = {}
        for r in roles:
            decompte[r] = decompte.get(r, 0) + 1
        sortie.append({"demande_id": ident, "titre": par_id[ident].titre, "score": score, "vers": f"/demandes/{ident}", "roles": decompte})
    return sortie


async def recommander(appel: dict, user: CurrentUser, hash_: str, superadmin: bool) -> dict:
    texte = _texte(appel["titre"], appel.get("texte") or "")
    return {
        "collections": await _collections(texte, user),
        "assistants": await _assistants(texte, user, hash_, superadmin),
        "demandes_voisines": await _roles_des_soutiens(texte, hash_, appel.get("demande_id")),
    }
