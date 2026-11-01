"""La ligne de commande de la fiche YAML : `verifier` hors réseau, `exporter` et `appliquer` contre
un service simulé ; le jeton vient d'une variable d'environnement, jamais d'un argument."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.harnais.contrat import canonique, empreinte
from app.harnais.fiche_yaml import charger
from scripts import fiche

EXEMPLE = Path(__file__).resolve().parents[3] / "docs" / "exemples" / "assistants" / "sejour-des-etrangers.yaml"
CIBLE = "https://mycollections.fake-domain.name"


def test_verifier_affiche_l_empreinte(capsys):
    assert fiche.main(["verifier", str(EXEMPLE)]) == 0
    attendu = empreinte(canonique(charger(EXEMPLE.read_bytes())))
    assert f"empreinte sha256:{attendu}" in capsys.readouterr().out


def test_verifier_dit_les_erreurs(tmp_path, capsys):
    f = tmp_path / "x.yaml"
    f.write_text(EXEMPLE.read_text(encoding="utf-8").replace("{source: ceseda}", "{source: inconnue}"), encoding="utf-8")
    assert fiche.main(["verifier", str(f)]) == 1
    assert "« inconnue », qui n'est pas une source de l'assistant" in capsys.readouterr().err


class Service:
    """Le service simulé : note les requêtes, rend ce qu'on lui dit."""

    def __init__(self, statut: int = 200):
        self.requetes: list[httpx.Request] = []
        self.statut = statut

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        self.requetes.append(requete)
        if requete.method == "GET":
            return httpx.Response(self.statut, text="# contrat: 1\nassistant: abc\n")
        if requete.url.path.endswith("/publier"):
            return httpx.Response(200, json={"version": 2, "nouvelle": True, "empreinte": "e" * 64})
        if self.statut != 200:
            return httpx.Response(self.statut, json={"detail": {"message": "Le fichier n'est pas valide.", "erreurs": [{"champ": "titre", "message": "vide"}]}})
        return httpx.Response(200, json={"empreinte": "d" * 64, "avertissements": ["« reference » ignorée"]})


def test_appliquer_envoie_le_fichier_avec_le_jeton_de_l_environnement(monkeypatch, capsys):
    monkeypatch.setenv("JETON_ESSAI", "valeur-de-test")
    s = Service()
    code = fiche.main(["appliquer", str(EXEMPLE), "--cible", CIBLE + "/", "--jeton-env", "JETON_ESSAI", "--publier"], transport=httpx.MockTransport(s))
    assert code == 0
    put, pub = s.requetes
    assert put.method == "PUT" and str(put.url) == f"{CIBLE}/api/assistants/sejour-des-etrangers/fiche.yaml"
    assert put.headers["authorization"] == "Bearer valeur-de-test" and put.headers["content-type"].startswith("text/yaml")
    assert put.content == EXEMPLE.read_bytes()
    assert str(pub.url).endswith("/publier") and pub.headers["authorization"] == "Bearer valeur-de-test"
    sortie = capsys.readouterr()
    assert "version 2 (nouvelle)" in sortie.out and "avertissement" in sortie.err


def test_appliquer_un_refus_du_service(monkeypatch, capsys):
    s = Service(statut=422)
    assert fiche.main(["appliquer", str(EXEMPLE), "--cible", CIBLE], transport=httpx.MockTransport(s)) == 1
    assert "titre : vide" in capsys.readouterr().err


def test_appliquer_un_fichier_invalide_n_appelle_pas_le_service(tmp_path):
    f = tmp_path / "x.yaml"
    f.write_text("assistant: abc\n", encoding="utf-8")
    s = Service()
    assert fiche.main(["appliquer", str(f), "--cible", CIBLE], transport=httpx.MockTransport(s)) == 1
    assert s.requetes == []


def test_exporter_ecrit_le_fichier(tmp_path, monkeypatch):
    monkeypatch.setenv("JETON_ESSAI", "valeur-de-test")
    s = Service()
    sortie = tmp_path / "abc.yaml"
    assert fiche.main(["exporter", "abc", "--cible", CIBLE, "--jeton-env", "JETON_ESSAI", "--sortie", str(sortie)], transport=httpx.MockTransport(s)) == 0
    assert sortie.read_text(encoding="utf-8").startswith("# contrat: 1")
    assert s.requetes[0].url.path == "/api/assistants/abc/fiche.yaml"


@pytest.mark.parametrize(
    "args",
    [
        ["exporter", "abc", "--cible", "http://mycollections.fake-domain.name"],
        ["exporter", "abc", "--cible", CIBLE, "--jeton-env", "JETON_ABSENT_DE_L_ENVIRONNEMENT"],
    ],
    ids=["http-hors-du-poste", "variable-vide"],
)
def test_usage_refuse_sans_appeler(args, monkeypatch, capsys):
    monkeypatch.delenv("JETON_ABSENT_DE_L_ENVIRONNEMENT", raising=False)
    s = Service()
    assert fiche.main(args, transport=httpx.MockTransport(s)) == 2
    assert s.requetes == [] and "erreur" in capsys.readouterr().err
