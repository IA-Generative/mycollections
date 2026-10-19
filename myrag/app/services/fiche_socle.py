"""La fiche d'une collection dans le SOCLE (Open WebUI, « Mon assistant ») : ce qu'on y LIT.

Vocabulaire (ADR-0003) : « le socle » est Open WebUI ; « un assistant » est, dans le reste du
code, un assistant de recherche (app/harnais). Ce module s'appelait `fiche_assistant`.

Le nom de la fiche est le TITRE de la collection, son étiquette est sa CATÉGORIE : ce que
l'agent voit dans le sélecteur de modèles, et ce que montrent les applications qui listent
les modèles. L'identifiant `openrag-<name>` ne change pas.

Une seule fonction décide de ce qui part au socle — la publication et la resynchronisation
l'appellent toutes deux. Tout vient de la base : rien de ce que dit l'appelant.

    python -m app.services.fiche_socle --toutes [--a-sec]
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select

from app.database import async_session
from app.models.db import Categorie, Collection, Publication
from app.services import etats, owui_client
from app.services.nommage import titre_de, titre_depuis_alias


class GroupeInconnu(ValueError):
    """Un groupe saisi n'existe pas dans l'assistant : la fiche n'y viserait personne."""

    def __init__(self, noms: list[str]):
        self.noms = noms
        super().__init__("groupe inconnu de l'assistant : " + ", ".join(noms) + ". Indiquez le nom d'un groupe tel qu'il apparaît dans l'assistant.")


class PasPubliee(Exception):
    pass


class FicheVoulue(BaseModel):
    """Ce qui part au socle : tout vient de la base, rien de ce que dit l'appelant."""

    model_id: str
    name: str
    description: str = ""
    description_par_defaut: str = ""
    tags: list[str] = []
    tags_geres: set[str] = set()
    access_control: dict[str, Any] | None = None
    access_grants: list[dict[str, Any]] = []
    groupes_saisis: list[str] = []


def nom_de_fiche(collection: dict, alias_name: str | None) -> str:
    """Le nom saisi à la publication s'il en est un ; sinon le titre de la collection.
    Un alias qui n'est que l'identifiant déguisé (`📚 demo-x`, `MirAI demo-x`) ne compte
    pas, et les marques (`📚`) tombent : le sélecteur montre un nom, pas un pictogramme."""
    return titre_depuis_alias(alias_name, collection.get("name", "")) or titre_de(collection)


async def _voulue(name: str) -> FicheVoulue:
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
        return FicheVoulue(
            model_id=f"openrag-{name}",
            name=nom_de_fiche(fiche, pub.alias_name),
            description=description,
            description_par_defaut=(col.description or "").strip()[:500],
            tags=[categories[col.categorie]] if col.categorie in categories else [],
            tags_geres=set(categories.values()),
            access_control=ac,
            access_grants=owui_client.grants_de_partage(pub.visibility, groupes),
            # Les noms saisis : traduits en identifiants de groupes de l'assistant au moment de
            # poser la fiche (synchroniser_fiche), jamais envoyés tels quels.
            groupes_saisis=groupes if pub.visibility == "group" else [],
        )


async def synchroniser_fiche(name: str, *, a_sec: bool = False, client=None, garder_les_droits: bool = False) -> dict:
    """Pose (ou repose) la fiche de la collection dans l'assistant. `a_sec` : dit ce qui
    partirait, sans rien écrire. Lève PasPubliee si la collection n'a pas à y être.

    `garder_les_droits` : la portée de la fiche EXISTANTE est reconduite. Une publication
    pose la portée que son auteur vient de choisir ; une resynchronisation, non."""
    fiche = await _voulue(name)
    rendu = {"collection": name, "model_id": fiche.model_id, "nom": fiche.name, "tags": fiche.tags}
    if a_sec:
        return {**rendu, "a_sec": True}
    client = client or owui_client.OwuiClient()
    if fiche.groupes_saisis and not garder_les_droits:
        ids, inconnus = await client.ids_de_groupes(fiche.groupes_saisis)
        if inconnus:
            raise GroupeInconnu(inconnus)
        fiche = fiche.model_copy(
            update={
                "access_grants": owui_client.grants_de_partage("group", ids),
                "access_control": {"read": {"group_ids": ids, "user_ids": []}, "write": {"group_ids": ids, "user_ids": []}},
            }
        )
    await client.upsert_model(**fiche.model_dump(exclude={"groupes_saisis"}), garder_les_droits=garder_les_droits)
    return {**rendu, "a_sec": False}


async def publiees() -> list[str]:
    async with async_session() as session:
        lignes = (
            (
                await session.execute(
                    select(Publication.collection_name)
                    .join(Collection, Collection.name == Publication.collection_name)
                    .where(Publication.state == "published", Publication.alias_enabled.is_(True), Collection.archived_at.is_(None))
                    .order_by(Publication.collection_name)
                )
            )
            .scalars()
            .all()
        )
        return list(lignes)


async def resynchroniser_toutes(*, a_sec: bool = False) -> dict:
    """Après un changement de titre, de catégorie ou de libellé : reposer toutes les fiches.
    Une fiche qui échoue n'arrête pas les autres ; le bilan les nomme.

    JAMAIS les droits : des fiches ont été posées ou restreintes hors de Mes collections
    (corpus partagés accordés à un seul compte, alors que leur fiche ici dit « tout le
    monde ») — reposer la portée enregistrée les aurait ouvertes à tous, d'un clic."""
    client = None if a_sec else owui_client.OwuiClient()
    faites, echecs = [], []
    for name in await publiees():
        try:
            faites.append(await synchroniser_fiche(name, a_sec=a_sec, client=client, garder_les_droits=True))
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
