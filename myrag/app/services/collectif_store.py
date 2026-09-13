"""Le collectif : demandes, soutiens, abonnements, états de collection, grille,
propositions, signalements — et le journal qui va avec chaque geste.

Toute décision d'état se prend ICI, côté serveur, dans la transaction qui écrit :
aucune route n'accepte un état en entrée. Toute identité est un condensé.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import delete, func, select

from app.config import settings
from app.database import async_session
from app.models.db import (
    Abonnement, Amorce, Collection, Demande, Evenement, GrilleControle, Proposition,
    Signalement, Soutien, utcnow,
)
from app.services import etats, journal, relais
from app.services.pseudo import SelAbsent, condenser


class Introuvable(LookupError):
    pass


class Conflit(RuntimeError):
    pass


class Interdit(PermissionError):
    pass


# ─── Signature d'un geste ─────────────────────────────────────────────────────────

def signature(sub: str | None) -> dict:
    """Les arguments de journal.ecrire pour une personne — ou, sans sel, pour le service."""
    if sub:
        try:
            return {"auteur_hash": condenser(sub)}
        except SelAbsent:
            pass
    return {"robot": "service", "detail": {"sans_sel": True}}


def _fusion_detail(sig: dict, detail: dict | None) -> dict:
    d = dict(sig.get("detail") or {})
    d.update(detail or {})
    return {**{k: v for k, v in sig.items() if k != "detail"}, "detail": d}


# ─── Demandes ─────────────────────────────────────────────────────────────────────

async def _enrichir(session, demandes: list[Demande], sub_hash: str | None) -> list[dict]:
    if not demandes:
        return []
    ids = [d.id for d in demandes]
    soutiens = (await session.execute(select(Soutien).where(Soutien.demande_id.in_(ids)))).scalars().all()
    par_demande: dict[str, list[Soutien]] = {}
    for s in soutiens:
        par_demande.setdefault(s.demande_id, []).append(s)
    abonnes: set[str] = set()
    if sub_hash:
        abonnes = set((await session.execute(
            select(Abonnement.objet_id).where(
                Abonnement.objet_type == "demande", Abonnement.objet_id.in_(ids), Abonnement.sub_hash == sub_hash
            )
        )).scalars().all())
    derniers = await journal.derniers_par_objet(session, "demande")
    maintenant = utcnow()
    resultat = []
    for d in demandes:
        mes = [s for s in par_demande.get(d.id, []) if sub_hash and s.sub_hash == sub_hash]
        liste = par_demande.get(d.id, [])
        roles: dict[str, int] = {}
        for s in liste:
            roles[s.role] = roles.get(s.role, 0) + 1
        fiche = d.to_dict()
        fiche.update({
            "nb_soutiens": len({s.sub_hash for s in liste}),
            "garant": any(s.role == "garant" for s in liste),
            "roles": roles,
            "temps_declare_min": sum(s.temps_declare_min or 0 for s in liste),
            "soutenue_par_moi": bool(mes),
            "mon_role": mes[0].role if mes else None,
            "abonne": d.id in abonnes,
            "sommeil": etats.en_sommeil(d.etat, derniers.get(d.id), maintenant, settings.sommeil_jours),
            "seuil_atteint": len({s.sub_hash for s in liste}) >= d.seuil,
        })
        resultat.append(fiche)
    return resultat


async def _abonnes_dans(session, objet_type: str, objet_id: str) -> list[str]:
    return list((await session.execute(select(Abonnement.sub_hash).where(
        Abonnement.objet_type == objet_type, Abonnement.objet_id == objet_id))).scalars().all())


async def _abonner_dans(session, objet_type: str, objet_id: str, sub_hash: str) -> None:
    existant = await session.get(Abonnement, (objet_type, objet_id, sub_hash))
    if not existant:
        session.add(Abonnement(objet_type=objet_type, objet_id=objet_id, sub_hash=sub_hash))


async def creer_demande(donnees: dict, sub_hash: str, seuil: int) -> dict:
    async with async_session() as session:
        d = Demande(**donnees, seuil=seuil, cree_par_hash=sub_hash)
        session.add(d)
        await session.flush()
        await _abonner_dans(session, "demande", d.id, sub_hash)
        journal.ecrire(session, "demande", d.id, "demande.creee", auteur_hash=sub_hash,
                       detail={"frequence": d.frequence, "seuil": seuil})
        await session.commit()
        return (await _enrichir(session, [d], sub_hash))[0]


async def lister_demandes(sub_hash: str | None, etat: str | None = None) -> list[dict]:
    async with async_session() as session:
        stmt = select(Demande).order_by(Demande.maj_le.desc())
        if etat:
            stmt = stmt.where(Demande.etat == etat)
        demandes = (await session.execute(stmt)).scalars().all()
        return await _enrichir(session, list(demandes), sub_hash)


async def lire_demande(ident: str, sub_hash: str | None) -> dict:
    async with async_session() as session:
        d = await session.get(Demande, ident)
        if not d:
            raise Introuvable(ident)
        return (await _enrichir(session, [d], sub_hash))[0]


async def auteur_de(ident: str) -> str:
    async with async_session() as session:
        d = await session.get(Demande, ident)
        if not d:
            raise Introuvable(ident)
        return d.cree_par_hash


async def modifier_demande(ident: str, champs: dict, sub_hash: str) -> dict:
    async with async_session() as session:
        d = await session.get(Demande, ident)
        if not d:
            raise Introuvable(ident)
        for k, v in champs.items():
            setattr(d, k, v)
        d.maj_le = utcnow()
        journal.ecrire(session, "demande", d.id, "demande.modifiee", auteur_hash=sub_hash,
                       detail={"champs": sorted(champs)})
        await session.commit()
        return (await _enrichir(session, [d], sub_hash))[0]


async def _recalculer_etat(session, d: Demande, sub_hash: str) -> None:
    """Le passage en chantier — jamais décidé par un client."""
    if d.etat != "ouverte":
        return
    lignes = (await session.execute(select(Soutien).where(Soutien.demande_id == d.id))).scalars().all()
    nb = len({s.sub_hash for s in lignes})
    a_garant = any(s.role == "garant" for s in lignes)
    if etats.demande_atteint_le_chantier(nb, a_garant, d.seuil):
        journal.ecrire(session, "demande", d.id, "seuil.atteint", robot="serveur",
                       detail={"soutiens": nb, "seuil": d.seuil, "garant": True})
        journal.ecrire(session, "demande", d.id, "demande.etat", robot="serveur",
                       detail={"de": d.etat, "vers": "chantier"})
        d.etat = "chantier"
        d.maj_le = utcnow()


async def soutenir(ident: str, sub_hash: str, role: str, temps: int | None) -> dict:
    async with async_session() as session:
        d = await session.get(Demande, ident)
        if not d:
            raise Introuvable(ident)
        if d.etat in ("realisee", "close"):
            raise Conflit("cette demande n'accepte plus de soutien")
        if role == "garant":
            autre = (await session.execute(select(Soutien).where(
                Soutien.demande_id == ident, Soutien.role == "garant", Soutien.sub_hash != sub_hash
            ))).scalars().first()
            if autre:
                raise Conflit("cette demande a déjà un garant")
        s = await session.get(Soutien, (ident, sub_hash))
        if s:
            s.role, s.temps_declare_min = role, temps
        else:
            session.add(Soutien(demande_id=ident, sub_hash=sub_hash, role=role, temps_declare_min=temps))
        await _abonner_dans(session, "demande", ident, sub_hash)
        await session.flush()
        nb = (await session.execute(
            select(func.count(func.distinct(Soutien.sub_hash))).where(Soutien.demande_id == ident)
        )).scalar_one()
        journal.ecrire(session, "demande", ident, "soutien.ajoute", auteur_hash=sub_hash,
                       detail={"role": role, "temps_declare_min": temps, "nb_soutiens": int(nb)})
        avant = d.etat
        await _recalculer_etat(session, d, sub_hash)
        abonnes = await _abonnes_dans(session, "demande", ident) if d.etat != avant else []
        await session.commit()
        if d.etat != avant:
            relais.planifier(abonnes, f"« {d.titre} » : le seuil est atteint, un garant est là — le chantier démarre.")
        return (await _enrichir(session, [d], sub_hash))[0]


async def retirer_soutien(ident: str, sub_hash: str) -> dict:
    async with async_session() as session:
        d = await session.get(Demande, ident)
        if not d:
            raise Introuvable(ident)
        s = await session.get(Soutien, (ident, sub_hash))
        if s:
            await session.delete(s)
            await session.flush()
            nb = (await session.execute(
                select(func.count(func.distinct(Soutien.sub_hash))).where(Soutien.demande_id == ident)
            )).scalar_one()
            journal.ecrire(session, "demande", ident, "soutien.retire", auteur_hash=sub_hash,
                           detail={"role": s.role, "nb_soutiens": int(nb)})
        await session.commit()
        return (await _enrichir(session, [d], sub_hash))[0]


async def retirer_garant(ident: str, admin_hash: str) -> dict:
    async with async_session() as session:
        d = await session.get(Demande, ident)
        if not d:
            raise Introuvable(ident)
        await session.execute(delete(Soutien).where(Soutien.demande_id == ident, Soutien.role == "garant"))
        journal.ecrire(session, "demande", ident, "garant.retire", auteur_hash=admin_hash)
        await session.commit()
        return (await _enrichir(session, [d], admin_hash))[0]


async def abonner(objet_type: str, objet_id: str, sub_hash: str, oui: bool) -> bool:
    async with async_session() as session:
        if oui:
            await _abonner_dans(session, objet_type, objet_id, sub_hash)
        else:
            await session.execute(delete(Abonnement).where(
                Abonnement.objet_type == objet_type, Abonnement.objet_id == objet_id, Abonnement.sub_hash == sub_hash
            ))
        await session.commit()
        return oui


async def clore_demande(ident: str, sub_hash: str, doublon_de: str | None, motif: str | None) -> dict:
    async with async_session() as session:
        d = await session.get(Demande, ident)
        if not d:
            raise Introuvable(ident)
        if doublon_de and not await session.get(Demande, doublon_de):
            raise Introuvable(doublon_de)
        journal.ecrire(session, "demande", ident, "demande.etat", auteur_hash=sub_hash,
                       detail={"de": d.etat, "vers": "close", "doublon_de": doublon_de, "motif": motif})
        d.etat, d.doublon_de, d.motif_cloture, d.maj_le = "close", doublon_de, motif, utcnow()
        await session.commit()
        return (await _enrichir(session, [d], sub_hash))[0]


async def journal_de(objet_type: str, objet_id: str, limite: int, avant: datetime | None) -> dict:
    async with async_session() as session:
        lignes, suivant = await journal.lire(session, objet_type, objet_id, limite=limite, avant=avant)
        return {"evenements": [e.to_dict() for e in lignes], "suivant": suivant.isoformat() if suivant else None}


# ─── Collections : état, garant, grille ───────────────────────────────────────────

async def fiche(name: str) -> dict:
    """La fiche brute d'une collection, garant compris (jamais servie telle quelle)."""
    async with async_session() as session:
        c = await session.get(Collection, name)
        if not c:
            raise Introuvable(name)
        return {
            "name": c.name, "etat_collab": c.etat_collab or "amorcee", "garant_hash": c.garant_hash,
            "demande_id": c.demande_id, "scope": c.scope, "created_by": c.created_by,
            "scope_groups": json.loads(c.scope_groups_json or "[]"), "archived_at": c.archived_at,
        }


async def initialiser_collection(name: str, sub: str | None, *, demande_id: str | None = None,
                                 garant_pressenti: str = "", grille: dict | None = None,
                                 robot: str | None = None) -> None:
    """À la création : état amorcée, créateur garant, grille (pré-remplie ou vide), journal."""
    async with async_session() as session:
        c = await session.get(Collection, name)
        if not c:
            raise Introuvable(name)
        c.etat_collab = c.etat_collab or "amorcee"
        sig = {"robot": robot} if robot else signature(sub)
        if c.garant_hash is None and sig.get("auteur_hash"):
            c.garant_hash = sig["auteur_hash"]
        if demande_id:
            c.demande_id = demande_id
        if garant_pressenti:
            c.garant_pressenti = garant_pressenti
        g = await session.get(GrilleControle, name)
        if not g:
            g = GrilleControle(collection_name=name)
            session.add(g)
        for champ in ("source_licence", "donnees_perso", "fraicheur"):
            if (grille or {}).get(champ) and not getattr(g, champ):
                setattr(g, champ, grille[champ])
        journal.ecrire(session, "collection", name, "collection.creee", collection_name=name,
                       **_fusion_detail(sig, {"etat": c.etat_collab}))
        await session.commit()


async def lire_etat(name: str, sub_hash: str | None, superadmin: bool) -> dict:
    async with async_session() as session:
        c = await session.get(Collection, name)
        if not c:
            raise Introuvable(name)
        g = await session.get(GrilleControle, name)
        grille = g.to_dict() if g else {}
        etat = c.etat_collab or "amorcee"
        je_suis_garant = bool(sub_hash) and c.garant_hash == sub_hash
        return {
            "collection": name, "etat": etat, "etats": list(etats.ETATS_COLLECTION),
            "mention": etats.mention_verification(etat),
            "garant": bool(c.garant_hash), "garant_pressenti": c.garant_pressenti or "",
            "je_suis_garant": je_suis_garant,
            "transitions_possibles": etats.transitions_possibles(etat, grille) if (je_suis_garant or superadmin) else [],
            "grille_complete": etats.grille_complete(grille),
        }


async def changer_etat(name: str, cible: str, sub_hash: str, *, forcer: bool, motif: str) -> dict:
    async with async_session() as session:
        c = await session.get(Collection, name)
        if not c:
            raise Introuvable(name)
        g = await session.get(GrilleControle, name)
        de = c.etat_collab or "amorcee"
        vers = etats.transition_collection(de, cible, g.to_dict() if g else {}, forcer=forcer)
        c.etat_collab = vers
        detail = {"de": de, "vers": vers}
        if forcer:
            detail.update({"force": True, "motif": motif})
        journal.ecrire(session, "collection", name, "collection.etat", auteur_hash=sub_hash,
                       collection_name=name, detail=detail)
        abonnes = await _abonnes_dans(session, "collection", name)
        if c.demande_id:
            abonnes += await _abonnes_dans(session, "demande", c.demande_id)
        if vers == "publiee_tous" and c.demande_id:
            d = await session.get(Demande, c.demande_id)
            if d and d.etat in ("ouverte", "chantier"):
                journal.ecrire(session, "demande", d.id, "demande.etat", robot="serveur",
                               detail={"de": d.etat, "vers": "realisee", "collection": name})
                d.etat, d.collection_name, d.maj_le = "realisee", name, utcnow()
        await session.commit()
    libelles = {"amorcee": "amorcée", "en_controle": "en contrôle", "publiee_groupe": "publiée au groupe", "publiee_tous": "publiée à tous"}
    relais.planifier(abonnes, f"La collection « {name} » est désormais {libelles.get(vers, vers)}"
                              + (" (forçage par l'administration)." if forcer else "."))
    return await lire_etat(name, sub_hash, True)


async def lire_grille(name: str) -> dict:
    async with async_session() as session:
        g = await session.get(GrilleControle, name)
        d = g.to_dict() if g else GrilleControle(collection_name=name).to_dict()
        d["complete"] = etats.grille_complete(d)
        return d


async def maj_grille(name: str, champs: dict, sub_hash: str) -> dict:
    async with async_session() as session:
        g = await session.get(GrilleControle, name)
        if not g:
            g = GrilleControle(collection_name=name)
            session.add(g)
        for k, v in champs.items():
            if k == "couverture":
                g.couverture_json = json.dumps(v or {}, ensure_ascii=False)
            else:
                setattr(g, k, v)
        g.maj_par_hash, g.maj_le = sub_hash, utcnow()
        journal.ecrire(session, "collection", name, "grille.maj", auteur_hash=sub_hash,
                       collection_name=name, detail={"champs": sorted(champs)})
        await session.commit()
    return await lire_grille(name)


async def poser_couverture(name: str, couverture: dict, robot: str) -> None:
    """La couverture réelle constatée à l'import (juridictions, dates, lignes) : écrite
    par le connecteur, jamais par une personne — la grille la montre telle quelle."""
    async with async_session() as session:
        g = await session.get(GrilleControle, name)
        if not g:
            g = GrilleControle(collection_name=name)
            session.add(g)
        g.couverture_json = json.dumps(couverture, ensure_ascii=False, default=str)
        g.maj_le = utcnow()
        journal.ecrire(session, "collection", name, "grille.maj", robot=robot, collection_name=name,
                       detail={"champs": ["couverture"]})
        await session.commit()


async def relire(name: str, sub_hash: str) -> dict:
    async with async_session() as session:
        g = await session.get(GrilleControle, name)
        if not g:
            g = GrilleControle(collection_name=name)
            session.add(g)
        relecteurs = json.loads(g.relecteurs_json or "[]")
        if sub_hash not in relecteurs:
            relecteurs.append(sub_hash)
            g.relecteurs_json = json.dumps(relecteurs)
            g.relecture_n = len(relecteurs)
            g.maj_le = utcnow()
            journal.ecrire(session, "collection", name, "grille.relue", auteur_hash=sub_hash,
                           collection_name=name, detail={"relecture_n": g.relecture_n})
        await session.commit()
    return await lire_grille(name)


# ─── Propositions ─────────────────────────────────────────────────────────────────

async def creer_proposition(name: str, donnees: dict, sub_hash: str) -> dict:
    async with async_session() as session:
        p = Proposition(collection_name=name, auteur_hash=sub_hash, **donnees)
        session.add(p)
        await session.flush()
        journal.ecrire(session, "proposition", p.id, "proposition.deposee", auteur_hash=sub_hash,
                       collection_name=name, detail={"cible_type": p.cible_type, "cible_ref": p.cible_ref})
        journal.ecrire(session, "collection", name, "proposition.deposee", auteur_hash=sub_hash,
                       collection_name=name, detail={"proposition": p.id})
        await session.commit()
        return p.to_dict()


async def lister_propositions(name: str, etat: str | None = None) -> list[dict]:
    async with async_session() as session:
        stmt = select(Proposition).where(Proposition.collection_name == name).order_by(Proposition.cree_le.desc())
        if etat:
            stmt = stmt.where(Proposition.etat == etat)
        return [p.to_dict() for p in (await session.execute(stmt)).scalars().all()]


async def lire_proposition(name: str, ident: str) -> dict:
    async with async_session() as session:
        p = await session.get(Proposition, ident)
        if not p or p.collection_name != name:
            raise Introuvable(ident)
        lignes, _ = await journal.lire(session, "proposition", ident, limite=journal.LIMITE_MAX)
        return {"proposition": p.to_dict(), "historique": [e.to_dict() for e in lignes]}


async def appliquer_proposition(p: Proposition) -> dict:
    """Point d'extension du lot 2 : appliquer dans Grist ou poser la version du fichier,
    puis réindexer. Au lot 1, la publication est un acte de décision, sans effet matériel."""
    return {"appliquee": False, "motif": "application matérielle : lot 2"}


async def decider_proposition(name: str, ident: str, decision: str, motif: str | None, sub_hash: str) -> dict:
    async with async_session() as session:
        p = await session.get(Proposition, ident)
        if not p or p.collection_name != name:
            raise Introuvable(ident)
        if p.etat != "proposee":
            raise Conflit(f"la proposition est déjà « {p.etat} »")
        p.etat, p.motif_refus, p.decide_par_hash, p.decide_le = decision, motif, sub_hash, utcnow()
        detail = {"motif": motif} if motif else {}
        if decision == "publiee":
            detail["application"] = await appliquer_proposition(p)
        type_ = "proposition.publiee" if decision == "publiee" else "proposition.refusee"
        journal.ecrire(session, "proposition", ident, type_, auteur_hash=sub_hash, collection_name=name, detail=detail)
        journal.ecrire(session, "collection", name, type_, auteur_hash=sub_hash, collection_name=name,
                       detail={"proposition": ident, **detail})
        destinataires = [p.auteur_hash] + await _abonnes_dans(session, "collection", name)
        await session.commit()
        relais.planifier(destinataires, f"Proposition sur « {name} » {'publiée' if decision == 'publiee' else 'refusée'}"
                                        + (f" — motif : {motif}" if motif else "") + ".")
        return p.to_dict()


# ─── Signalements ─────────────────────────────────────────────────────────────────

async def creer_signalement(name: str, donnees: dict, sub_hash: str) -> dict:
    async with async_session() as session:
        s = Signalement(collection_name=name, auteur_hash=sub_hash, **donnees)
        session.add(s)
        await session.flush()
        journal.ecrire(session, "signalement", s.id, "signalement.depose", auteur_hash=sub_hash,
                       collection_name=name, detail={"motif": s.motif, "fichier_id": s.fichier_id})
        journal.ecrire(session, "collection", name, "signalement.depose", auteur_hash=sub_hash,
                       collection_name=name, detail={"signalement": s.id, "motif": s.motif})
        await session.commit()
        return s.to_dict()


async def lister_signalements(name: str, etat: str | None = None) -> list[dict]:
    async with async_session() as session:
        stmt = select(Signalement).where(Signalement.collection_name == name).order_by(Signalement.cree_le.desc())
        if etat:
            stmt = stmt.where(Signalement.etat == etat)
        return [s.to_dict() for s in (await session.execute(stmt)).scalars().all()]


async def traiter_signalement(name: str, ident: str, etat: str, sub_hash: str) -> dict:
    async with async_session() as session:
        s = await session.get(Signalement, ident)
        if not s or s.collection_name != name:
            raise Introuvable(ident)
        de = s.etat
        s.etat, s.traite_par_hash, s.traite_le = etat, sub_hash, utcnow()
        journal.ecrire(session, "signalement", ident, "signalement.traite", auteur_hash=sub_hash,
                       collection_name=name, detail={"de": de, "vers": etat})
        journal.ecrire(session, "collection", name, "signalement.traite", auteur_hash=sub_hash,
                       collection_name=name, detail={"signalement": ident, "vers": etat})
        auteur = s.auteur_hash
        await session.commit()
        relais.planifier([auteur], f"Votre signalement sur « {name} » est {'clos' if etat == 'clos' else 'pris en compte'}.")
        return s.to_dict()


# ─── Journal depuis les routes historiques ────────────────────────────────────────

async def consigner(objet_type: str, objet_id: str, type_: str, sub: str | None = None, *,
                    robot: str | None = None, collection_name: str | None = None, detail: dict | None = None) -> None:
    """Écrire un événement hors d'une transaction du collectif (routes historiques, jobs)."""
    sig = {"robot": robot} if robot else signature(sub)
    async with async_session() as session:
        journal.ecrire(session, objet_type, objet_id, type_, collection_name=collection_name,
                       **_fusion_detail(sig, detail))
        await session.commit()


async def delier_collection(name: str) -> None:
    """À la purge : les abonnements tombent, la demande d'origine se détache (dans le journal)."""
    async with async_session() as session:
        await session.execute(delete(Abonnement).where(Abonnement.objet_type == "collection", Abonnement.objet_id == name))
        demandes = (await session.execute(select(Demande).where(Demande.collection_name == name))).scalars().all()
        for d in demandes:
            d.collection_name = None
            journal.ecrire(session, "demande", d.id, "collection.purgee", robot="serveur", detail={"collection": name})
        await session.commit()


# ─── Amorces ──────────────────────────────────────────────────────────────────────

async def etats_des_amorces() -> dict[str, dict]:
    async with async_session() as session:
        return {a.id: a.to_dict() for a in (await session.execute(select(Amorce))).scalars().all()}


async def marquer_amorce(ident: str, etat_import: str, *, collection_name: str | None = None,
                         detail: dict | None = None, erreur: str | None = None) -> dict:
    async with async_session() as session:
        a = await session.get(Amorce, ident)
        if not a:
            a = Amorce(id=ident)
            session.add(a)
        a.etat_import = etat_import
        if collection_name:
            a.collection_name = collection_name
        if detail is not None:
            a.detail_json = json.dumps(detail, ensure_ascii=False)
        a.erreur = erreur
        if etat_import in ("termine", "echec"):
            a.dernier_import_le = utcnow()
        await session.commit()
        return a.to_dict()


# ─── Ce que la cloche de la barre commune affiche (lot 4) ─────────────────────────

async def suivi_pour(sub_hash: str) -> dict:
    """Les demandes que je soutiens ou que je suis, celles à un soutien du seuil, les
    collections que je suis — pour la cloche, en un appel."""
    async with async_session() as session:
        miennes = set((await session.execute(select(Soutien.demande_id).where(Soutien.sub_hash == sub_hash))).scalars().all())
        miennes |= set((await session.execute(select(Abonnement.objet_id).where(
            Abonnement.objet_type == "demande", Abonnement.sub_hash == sub_hash))).scalars().all())
        ouvertes = list((await session.execute(select(Demande).where(Demande.etat.in_(("ouverte", "chantier")))
                                               .order_by(Demande.maj_le.desc()))).scalars().all())
        enrichies = await _enrichir(session, ouvertes, sub_hash)
        suivies = [d for d in enrichies if d["id"] in miennes]
        presque = [d for d in enrichies if d["etat"] == "ouverte" and not d["soutenue_par_moi"]
                   and d["nb_soutiens"] >= max(1, d["seuil"] - 1)][:5]
        collections = list((await session.execute(select(Abonnement.objet_id).where(
            Abonnement.objet_type == "collection", Abonnement.sub_hash == sub_hash))).scalars().all())
        cles = ("id", "titre", "etat", "nb_soutiens", "seuil", "garant", "sommeil", "soutenue_par_moi", "mon_role", "collection_name")
        return {"demandes": [{k: d[k] for k in cles} for d in suivies],
                "presque_au_seuil": [{k: d[k] for k in cles} for d in presque],
                "collections": collections}


async def collections_publiees_a_tous() -> list[dict]:
    async with async_session() as session:
        lignes = (await session.execute(select(Collection).where(
            Collection.etat_collab == "publiee_tous", Collection.archived_at.is_(None)).order_by(Collection.name))).scalars().all()
        return [{"name": c.name, "description": c.description or ""} for c in lignes]


async def deposer_version(name: str, document: str, nom_fichier: str, contenu: bytes, sub_hash: str,
                          signalement_id: str) -> dict:
    """Une nouvelle version proposée pour un document cité : rangée à part, jamais
    servie, en attente de la décision du garant (proposition de type fichier)."""
    from pathlib import Path
    from app.routers.ingest import safe_filename, ensure_within
    base = Path(settings.data_dir) / "_versions_proposees"
    dossier = ensure_within(base, base / safe_filename(name))
    dossier.mkdir(parents=True, exist_ok=True)
    nom_sur = f"{signalement_id[:8]}-{safe_filename(nom_fichier)}"
    chemin = ensure_within(dossier, dossier / nom_sur)
    chemin.write_bytes(contenu)
    return await creer_proposition(name, {
        "cible_type": "fichier", "cible_ref": document, "avant": document, "apres": str(chemin.name),
        "justification": f"Nouvelle version déposée avec le signalement {signalement_id} (document obsolète).",
        "source": None,
    }, sub_hash)
