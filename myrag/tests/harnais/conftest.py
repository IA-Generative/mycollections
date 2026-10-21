"""Fixtures du harnais : une fiche à trois sources, quatre collections aux droits différents,
des identités, un connecteur « de théâtre » qui rend des passages canoniques et compte ses appels."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from typing import ClassVar

import pytest

from app.auth import CurrentUser
from app.harnais.contrat import Appelant, Etape, FicheAssistant, FicheSource, Passage
from app.harnais.interfaces import Connecteur
from tests.conftest import SUPERADMIN, personne

ALICE = personne("alice")  # créatrice de `mienne` ; lit `partagee` et `ouverte`
BOB = personne("bob")  # créateur de `partagee`, `ouverte`, `secrete` ; ne lit pas `mienne`
DEHORS = CurrentUser(sub="dehors", username="d", groups=["/g/autre"])  # ne lit que le public

IDENTITES = {"alice": ALICE, "bob": BOB, "dehors": DEHORS, "superadmin": SUPERADMIN}
#: Ce que chaque identité lit, parmi les quatre collections.
LISIBLES = {
    "alice": {"mienne", "partagee", "ouverte"},
    "bob": {"partagee", "ouverte", "secrete"},
    "dehors": {"ouverte"},
    "superadmin": {"mienne", "partagee", "ouverte", "secrete"},
}
#: Les sources de la fiche d'essai (`ouverte` n'en est pas une).
SOURCES_FICHE = ("mienne", "partagee", "secrete")


@pytest.fixture
def jeu(creer_collection, purger):
    """Quatre collections aux droits différents, aux noms uniques, purgées après le test."""
    n = uuid.uuid4().hex[:6]
    c = {k: f"t-har-{n}-{k}" for k in ("mienne", "partagee", "ouverte", "secrete")}
    creer_collection(c["mienne"], ALICE, scope="private", scope_groups=[], titre="Mes notes")
    creer_collection(c["partagee"], BOB, titre="Méthodes de l'équipe")
    creer_collection(c["ouverte"], BOB, scope="public", scope_groups=[], titre="Textes ouverts")
    creer_collection(c["secrete"], BOB, scope="private", scope_groups=[], titre="Secret de Bob")
    yield c
    for nom in c.values():
        purger(nom)


def fiche_d_essai(jeu: dict[str, str], ident: str, **modifs) -> FicheAssistant:
    """Trois sources : `mienne` (toujours), `partagee` (selon_question), `secrete` (sur_consigne)."""
    regimes = {"mienne": "toujours", "partagee": "selon_question", "secrete": "sur_consigne"}
    f = {
        "assistant": ident,
        "titre": "Assistant d'essai",
        "sources": [{"id": jeu[k], "type": "collection", "regime": regimes[k], "rang": i} for i, k in enumerate(SOURCES_FICHE, start=1)],
    }
    f.update(modifs)
    return FicheAssistant.model_validate(f)


@pytest.fixture
def assistant_publie(client, en_tant_que, jeu, ident_assistant):
    """L'assistant d'essai, enregistré puis publié par l'administration (qui gère tout)."""
    en_tant_que(SUPERADMIN)
    fiche = fiche_d_essai(jeu, ident_assistant)
    r = client.put(f"/api/assistants/{ident_assistant}", json=fiche.model_dump(mode="json"))
    assert r.status_code == 200, r.text
    assert client.post(f"/api/assistants/{ident_assistant}/publier").status_code == 200
    return ident_assistant


def passage(source: str, document: str, rang: int, *, etape: int = 1, score: float | None = None, texte: str | None = None, ident: str | None = None) -> Passage:
    return Passage(
        source=source,
        etape=etape,
        rang=rang,
        score=score,
        ident=ident if ident is not None else f"{document}-{rang}",
        document=document,
        titre=f"Document {document}",
        texte=texte or f"Texte de {document} (passage {rang}) sur le budget.",
    )


class Theatre(Connecteur):
    """Rend des passages canoniques par source et compte ses appels. `pannes[source]` : l'exception
    à lever ; `barriere` : un `asyncio.Event` que `chercher` attend (preuve du parallélisme)."""

    type: ClassVar[str] = "collection"

    def __init__(self, passages: dict[str, list[Passage]] | None = None, *, pannes: dict[str, BaseException] | None = None):
        self.passages = passages or {}
        self.pannes = pannes or {}
        self.appels: list[tuple[int, str, tuple[Passage, ...]]] = []
        self.entrees: list[int] = []
        self.entrees_vues = asyncio.Event()
        self.barriere: asyncio.Event | None = None
        self.attendus = 0

    async def chercher(self, etape: Etape, identite: Appelant, *, amont: Sequence[Passage] = ()) -> list[Passage]:
        self.appels.append((etape.n, etape.source, tuple(amont)))
        self.entrees.append(etape.n)
        if self.attendus and len(self.entrees) >= self.attendus:
            self.entrees_vues.set()
        if self.barriere is not None:
            await self.barriere.wait()
        if etape.source in self.pannes:
            raise self.pannes[etape.source]
        return [p.model_copy(update={"etape": etape.n, "rang": i}) for i, p in enumerate(self.passages.get(etape.source, []), start=1)]

    async def fiche(self) -> FicheSource:
        return FicheSource(id="theatre", type="collection", titre="Théâtre")

    def sources_appelees(self) -> list[str]:
        return [s for _, s, _ in self.appels]


@pytest.fixture
def theatre_de(jeu):
    """Un théâtre qui rend deux passages par collection du jeu, y compris `ouverte` (qu'aucune fiche ne cite)."""

    def _f(**options) -> Theatre:
        return Theatre({nom: [passage(nom, f"{cle}-doc", 1, score=0.9), passage(nom, f"{cle}-doc", 2, score=0.5)] for cle, nom in jeu.items()}, **options)

    return _f


@pytest.fixture
def theatre_branche(theatre_de, monkeypatch):
    """Le service des assistants cherche chez le théâtre plutôt que chez OpenRAG."""
    import app.config
    from app.routers import recherche

    theatre = theatre_de()
    monkeypatch.setattr("app.services.assistant_recherche.ConnecteurOpenRAG", lambda **_: theatre)
    monkeypatch.setattr(app.config.settings, "recherche_url_publique", "https://mycollections.fake-domain.name")
    recherche._fenetres.clear()
    return theatre
