"""La fiche d'une collection dans l'assistant (OpenWebUI) : ce qu'on y LIT.

Le nom de la fiche est le TITRE de la collection, son étiquette est sa CATÉGORIE : ce que
l'agent voit dans le sélecteur de modèles, et ce que montrent les applications qui listent
les modèles. L'identifiant `openrag-<name>` ne change pas.

Une seule fonction décide de ce qui part au socle — la publication et la resynchronisation
l'appellent toutes deux. Tout vient de la base : rien de ce que dit l'appelant.

    python -m app.services.fiche_assistant --toutes [--a-sec]
"""

from __future__ import annotations

import json

from sqlalchemy import select

from app.database import async_session
from app.models.db import Categorie, Collection, Publication
from app.services import etats
from app.services.nommage import titre_de, titre_depuis_alias
from app.services import owui_client


class PasPubliee(Exception):
    pass


def nom_de_fiche(collection: dict, alias_name: str | None) -> str:
    """Le nom saisi à la publication s'il en est un ; sinon le titre de la collection.
    Un alias qui n'est que l'identifiant déguisé (`📚 demo-x`, `MirAI demo-x`) ne compte
    pas, et les marques (`📚`) tombent : le sélecteur montre un nom, pas un pictogramme."""
    return titre_depuis_alias(alias_name, collection.get("name", "")) or titre_de(collection)


async def _voulue(name: str) -> dict:
    async with async_session() as session:
        col = await session.get(Collection, name)
        pub = await session.get(Publication, name)
        if not col or not pub or pub.state != "published" or not pub.alias_enabled or col.archived_at:
            raise PasPubliee(name)
        categories = {c.cle: c.libelle for c in (await session.execute(select(Categorie))).scalars().all()}
        fiche = col.to_dict()
        groupes = json.loads(pub.visibility_groups_json or "[]")
        mention = etats.mention_verification(col.etat_collab or "amorcee")
        saisie = (pub.alias_description or "").strip()
        description = f"⚠ {mention} — {saisie}".rstrip(" —") if mention else saisie
        ac = None
        if pub.visibility == "group" and groupes:
            ac = {"read": {"group_ids": groupes, "user_ids": []}, "write": {"group_ids": groupes, "user_ids": []}}
        return {
            "model_id": f"openrag-{name}",
            "name": nom_de_fiche(fiche, pub.alias_name),
            "description": description,
            "description_par_defaut": (col.description or "").strip()[:500],
            "tags": [categories[col.categorie]] if col.categorie in categories else [],
            "tags_geres": set(categories.values()),
            "access_control": ac,
            "access_grants": owui_client.grants_de_partage(pub.visibility, groupes),
        }


async def synchroniser_fiche(name: str, *, a_sec: bool = False, client=None) -> dict:
    """Pose (ou repose) la fiche de la collection dans l'assistant. `a_sec` : dit ce qui
    partirait, sans rien écrire. Lève PasPubliee si la collection n'a pas à y être."""
    v = await _voulue(name)
    rendu = {"collection": name, "model_id": v["model_id"], "nom": v["name"], "tags": v["tags"]}
    if a_sec:
        return {**rendu, "a_sec": True}
    await (client or owui_client.OwuiClient()).upsert_model(**v)
    return {**rendu, "a_sec": False}


async def publiees() -> list[str]:
    async with async_session() as session:
        lignes = (await session.execute(
            select(Publication.collection_name)
            .join(Collection, Collection.name == Publication.collection_name)
            .where(Publication.state == "published", Publication.alias_enabled.is_(True),
                   Collection.archived_at.is_(None))
            .order_by(Publication.collection_name)
        )).scalars().all()
        return list(lignes)


async def resynchroniser_toutes(*, a_sec: bool = False) -> dict:
    """Après un changement de titre, de catégorie ou de libellé : reposer toutes les fiches.
    Une fiche qui échoue n'arrête pas les autres ; le bilan les nomme."""
    client = None if a_sec else owui_client.OwuiClient()
    faites, echecs = [], []
    for name in await publiees():
        try:
            faites.append(await synchroniser_fiche(name, a_sec=a_sec, client=client))
        except Exception as e:  # noqa: BLE001 — le bilan dit tout, rien ne se perd
            echecs.append({"collection": name, "erreur": f"{type(e).__name__}: {e}"[:300]})
    return {"a_sec": a_sec, "fiches": faites, "echecs": echecs}


if __name__ == "__main__":
    import asyncio
    import sys

    if "--toutes" not in sys.argv:
        sys.exit(__doc__)
    from app.database import init_db

    async def _main():
        await init_db()
        print(json.dumps(await resynchroniser_toutes(a_sec="--a-sec" in sys.argv), ensure_ascii=False, indent=2))
    asyncio.run(_main())
