"""Fixtures de la campagne, hors réseau : une horloge qui avance quand on dort, un faux SSO, une
correspondance d'alias inventée, et le jeu de questions public."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.campagne.cible import Jeton
from scripts.campagne.corpus import charger_questions, charger_variantes

ICI = Path(__file__).resolve().parent
JEU = ICI / "sejour-des-etrangers"
BASE = "https://mycollections.fake-domain.name"
AUTORITE = "https://sso.fake-domain.name/realms/essai"
JETON_URL = f"{AUTORITE}/protocol/openid-connect/token"
#: Les alias des fiches d'essai, résolus vers des identifiants inventés.
CORRESPONDANCE = {a: f"essai-{a}" for a in ("guide", "guide-md", "faq", "mobilite", "jurisprudence")}


class Horloge:
    """Le temps ne passe que quand on dort (ou qu'on l'avance)."""

    def __init__(self, t: float = 1_000_000.0):
        self.t = t
        self.sommes: list[float] = []

    def __call__(self) -> float:
        return self.t

    def dormir(self, s: float) -> None:
        self.sommes.append(s)
        self.t += s


class FauxSso:
    """La connexion par le navigateur, simulée : chaque appel rend un jeton neuf."""

    def __init__(self, horloge: Horloge, *, echoue: bool = False):
        self.horloge, self.echoue, self.connexions = horloge, echoue, 0

    def __call__(self) -> Jeton:
        self.connexions += 1
        if self.echoue and self.connexions > 1:
            raise RuntimeError("navigateur en panne")
        return Jeton(f"acces-{self.connexions}", f"renouv-{self.connexions}", self.horloge() + 300, AUTORITE, "client-essai")


@pytest.fixture
def horloge() -> Horloge:
    return Horloge()


@pytest.fixture
def correspondance(tmp_path, monkeypatch) -> dict[str, str]:
    chemin = tmp_path / "correspondance.json"
    chemin.write_text(json.dumps(CORRESPONDANCE), encoding="utf-8")
    monkeypatch.setenv("CAMPAGNE_CORRESPONDANCE", str(chemin))
    return dict(CORRESPONDANCE)


@pytest.fixture
def variantes(correspondance):
    return charger_variantes(JEU, correspondance)


@pytest.fixture
def questions(correspondance, variantes):
    return charger_questions(JEU / "questions.yaml", correspondance, variantes)
