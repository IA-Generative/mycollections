"""La fusion des passages de plusieurs étapes : Reciprocal Rank Fusion (k = 60), avec un poids
par étape et un quota pour les sources `toujours`. Module pur : la sortie ne dépend ni de l'ordre
des étapes dans l'entrée ni d'aucun état."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from app.harnais.contrat import Passage

K_RRF = 60


def _cle(p: Passage) -> tuple[str, str, str]:
    """Un même morceau vu par deux étapes ne compte qu'une fois : (source, document, morceau)."""
    return (p.source, p.document, p.ident if p.ident else p.texte)


def fusionner(
    par_etape: Mapping[int, Sequence[Passage]],
    poids: Mapping[int, float],
    *,
    toujours: Collection[str] = (),
    quota: int = 1,
    limite: int | None = None,
    k: int = K_RRF,
) -> list[Passage]:
    """Les passages classés par score RRF décroissant : somme, sur les étapes, de
    `poids / (k + rang)`. Un poids nul (ou absent) retire l'étape de la fusion. Si `limite`
    est posée, chaque source de `toujours` garde au moins `quota` de ses meilleurs passages dans
    la sélection (ils prennent la place des derniers). Les rangs rendus sont 1..n ; le score est
    celui de la fusion."""
    scores: dict[tuple[str, str, str], float] = {}
    modele: dict[tuple[str, str, str], tuple[float, Passage]] = {}
    for n in sorted(par_etape):
        passages = par_etape[n]
        w = poids.get(n, 0.0)
        if w <= 0:
            continue
        vus: set[tuple[str, str, str]] = set()
        for position, p in enumerate(passages, start=1):
            c = _cle(p)
            if c in vus:
                continue
            vus.add(c)
            apport = w / (k + position)
            scores[c] = scores.get(c, 0.0) + apport
            # Le passage rendu est celui de l'étape qui l'a le mieux classé (à égalité : la plus petite étape).
            if c not in modele or (apport, -n) > (modele[c][0], -modele[c][1].etape):
                modele[c] = (apport, p)
    classes = sorted(scores, key=lambda c: (-scores[c], c))
    if limite is not None and len(classes) > limite:
        classes = _avec_quota(classes, modele, set(toujours), quota, limite)
    return [modele[c][1].model_copy(update={"rang": i, "score": round(scores[c], 6)}) for i, c in enumerate(classes, start=1)]


def _avec_quota(classes: list, modele: dict, toujours: set[str], quota: int, limite: int) -> list:
    reserves: list = []
    pris: dict[str, int] = {}
    for c in classes:
        source = modele[c][1].source
        if source in toujours and pris.get(source, 0) < quota:
            pris[source] = pris.get(source, 0) + 1
            reserves.append(c)
    reserves = reserves[:limite]
    choisis = set(reserves)
    for c in classes:
        if len(choisis) >= limite:
            break
        choisis.add(c)
    return [c for c in classes if c in choisis]
