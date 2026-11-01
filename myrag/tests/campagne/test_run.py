"""Le lanceur, contre une fausse cible et un faux modèle : reprise, budgets, fenêtre, règles d'arrêt."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from datetime import time as heure
from pathlib import Path

import httpx
import pytest

from scripts.campagne import run
from scripts.campagne.cible import Arret, Cible, Usage
from tests.campagne.conftest import BASE, FauxSso, Horloge

LIEN = f"{BASE}/api/openrag/extract/m1?exp=1&sig=s"


class FausseCible:
    """Le serveur : scopes, executer, /mcp, liens signés. `executer` se règle par essai."""

    def __init__(self, statut_executer=200, source="essai-guide"):
        self.statut_executer, self.source = statut_executer, source
        self.executer: list[tuple[str, str]] = []
        self.mcp: list[str] = []
        self.recherches = 0

    def __call__(self, req: httpx.Request) -> httpx.Response:
        chemin = req.url.path
        if chemin == "/api/v1/search/scopes":
            return httpx.Response(
                200,
                json={"scopes": [{"id": f"essai-{a}", "title": a} for a in ("guide", "guide-md", "faq", "mobilite", "jurisprudence")] + [{"id": "catalogue-un", "title": "Un"}]},
            )
        if chemin == "/api/v1/search":
            self.recherches += 1
            return httpx.Response(200, json={"results": [{"url": LIEN, "hits": [{"snippet": "Le duplicata demande une déclaration de perte.", "url": LIEN}]}]})
        if chemin.endswith("/executer"):
            assistant = chemin.split("/")[-2]
            question = json.loads(req.content)["question"]
            self.executer.append((assistant, question))
            if self.statut_executer != 200:
                return httpx.Response(self.statut_executer, headers={"Retry-After": "1"}, json={"detail": "non"})
            return httpx.Response(200, json=self._resultat(assistant, question))
        if chemin == "/mcp":
            corps = json.loads(req.content)
            self.mcp.append(corps["method"])
            if corps["method"] == "tools/list":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": corps["id"], "result": {"tools": [{"name": "lister_sources", "inputSchema": {"type": "object"}}]}})
            texte = json.dumps({"assistants": [{"id": "e2e-camp-sejour-s2", "collections": [{"id": "essai-guide"}]}]})
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": corps["id"], "result": {"content": [{"type": "text", "text": texte}]}})
        if chemin.startswith("/api/openrag/extract/"):
            return httpx.Response(200, text="morceau")
        return httpx.Response(404)

    def _resultat(self, assistant: str, question: str) -> dict:
        consigne = "algeriens" if assistant.endswith("s2") and "lgérien" in question else None
        return {
            "plan": {"assistant": assistant, "version": 1, "planificateur": "regles", "consigne": consigne, "etapes": [{"n": 1, "source": self.source, "question": question}]},
            "passages": [{"source": self.source, "etape": 1, "rang": 1, "document": "d1", "ident": "m1", "titre": "Fiche", "texte": "…", "url": LIEN}],
            "reponse": "Selon l'accord franco-algérien [1], puis le CESEDA.",
            "citations": [{"n": 1, "passage": "m1", "source": self.source}],
            "redaction": "faite",
            "par_source": {self.source: 1},
            "duree_ms": 1200,
        }


class FauxModele:
    """La passerelle : une conversation = lister_sources puis une réponse ; un juge = un verdict."""

    def __init__(self, max_appels=1000):
        self.max_appels, self.appels, self.deja = max_appels, 0, 0

    @property
    def restants(self):
        return max(0, self.max_appels - self.deja - self.appels)

    def completer(self, corps):
        from scripts.campagne.cible import BudgetEpuise

        if self.restants <= 0:
            raise BudgetEpuise("budget")
        self.appels += 1
        if "tools" not in corps:
            contenu = corps["messages"][0]["content"]
            if "évalues" in contenu:
                return {"choices": [{"message": {"content": '{"verdict": "conforme", "justification": "ok"}'}}]}
            return {"choices": [{"message": {"content": "Quelles pièces pour un duplicata ?"}}]}
        if not any(m["role"] == "tool" for m in corps["messages"]):
            appel = {"id": "t1", "type": "function", "function": {"name": "lister_sources", "arguments": "{}"}}
            return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [appel]}}]}
        return {"choices": [{"message": {"role": "assistant", "content": "Je n'ai pas trouvé de document qui réponde."}}]}


def _monter(tmp_path, horloge, serveur, *, debut=datetime(2026, 11, 1, 22, 0), passerelle=None, **reglages):
    cible = Cible(BASE, FauxSso(horloge), client=httpx.Client(transport=httpx.MockTransport(serveur)), horloge=horloge, dormir=horloge.dormir)
    t0 = horloge.t

    def maintenant():
        return debut + timedelta(seconds=horloge.t - t0)

    r = run.Reglages(nuit="2026-11-01", dossier=tmp_path / "2026-11-01", **reglages)
    return cible, r, maintenant


def _campagne(tmp_path, horloge, serveur, variantes, questions, passerelle=None, **reglages):
    cible, r, maintenant = _monter(tmp_path, horloge, serveur, **reglages)
    return run.Campagne(r, cible, variantes, questions, passerelle=passerelle, maintenant=maintenant, dire=lambda s: None)


def test_une_nuit_complete_puis_reprise_sans_rien_rejouer(tmp_path, variantes, questions):
    serveur = FausseCible()
    e = _campagne(tmp_path, Horloge(), serveur, variantes, questions, phases=("harnais",)).jouer()
    assert e["arret"] is None and e["phases"] == {"harnais": "complet"}
    assert len(serveur.executer) == len(questions) * 3
    # Question d'abord : s0, s1, s2 d'une même question se suivent.
    assert [a for a, _ in serveur.executer[:3]] == ["e2e-camp-sejour-s0", "e2e-camp-sejour-s1", "e2e-camp-sejour-s2"]
    lignes = [json.loads(li) for li in (tmp_path / "2026-11-01" / "essais.jsonl").read_text().splitlines()]
    assert lignes[0]["cle"] == f"harnais|s0|{questions[0].id}|2026-11-01"
    deuxieme = FausseCible()
    e2 = _campagne(tmp_path, Horloge(), deuxieme, variantes, questions, phases=("harnais",)).jouer()
    assert deuxieme.executer == [] and e2["phases"] == {"harnais": "complet"}
    etat = json.loads((tmp_path / "2026-11-01" / "etat.json").read_text())
    assert len(etat["executions"]) == 2


def test_le_budget_executer_vaut_pour_la_nuit(tmp_path, variantes, questions):
    serveur = FausseCible()
    e = _campagne(tmp_path, Horloge(), serveur, variantes, questions, phases=("harnais",), max_executer=5).jouer()
    assert len(serveur.executer) == 5 and e["phases"]["harnais"] == "budget-executer"
    encore = FausseCible()
    _campagne(tmp_path, Horloge(), encore, variantes, questions, phases=("harnais",), max_executer=5).jouer()
    assert encore.executer == []  # le budget de la nuit est déjà consommé


def test_une_erreur_serveur_se_rejoue_a_la_reprise(tmp_path, variantes, questions):
    _campagne(tmp_path, Horloge(), FausseCible(statut_executer=503), variantes, questions, phases=("harnais",), max_executer=2).jouer()
    serveur = FausseCible()
    _campagne(tmp_path, Horloge(), serveur, variantes, questions, phases=("harnais",), max_executer=4).jouer()
    assert len(serveur.executer) == 2
    assert serveur.executer[0] == ("e2e-camp-sejour-s0", questions[0].texte)


def test_un_incident_de_droits_arrete_tout(tmp_path, variantes, questions):
    serveur = FausseCible(source="essai-secrete")
    e = _campagne(tmp_path, Horloge(), serveur, variantes, questions, phases=("harnais", "mcp")).jouer()
    assert e["arret"]["motif"] == "incident-droits" and e["arret"]["immediat"]
    assert len(serveur.executer) == 1 and serveur.mcp == []
    ligne = json.loads((tmp_path / "2026-11-01" / "essais.jsonl").read_text().splitlines()[0])
    assert ligne["verdicts"]["incidents"] == ["essai-secrete/d1"]  # l'essai est écrit avant l'arrêt


def test_trop_de_5xx_arrete_la_nuit(tmp_path, variantes, questions):
    serveur = FausseCible(statut_executer=500)
    e = _campagne(tmp_path, Horloge(), serveur, variantes, questions, phases=("harnais",)).jouer()
    assert e["arret"]["motif"] == "5xx" and not e["arret"]["immediat"]
    assert len(serveur.executer) == 49  # le scopes réussi compte aussi : 49 échecs sur 50 appels


def test_une_rafale_de_429_ralentit_puis_arrete(tmp_path, variantes, questions):
    serveur = FausseCible(statut_executer=429)
    e = _campagne(tmp_path, Horloge(), serveur, variantes, questions, phases=("harnais",)).jouer()
    assert e["arret"]["motif"] == "rafale-429"
    assert e["cadences"]["assistants"] == 10.0  # divisée par deux avant l'arrêt


def test_hors_fenetre_on_attend_l_ouverture(tmp_path, variantes, questions):
    horloge = Horloge()
    serveur = FausseCible()
    c = _campagne(
        tmp_path, horloge, serveur, variantes, questions, debut=datetime(2026, 11, 1, 20, 0), phases=("harnais",), max_executer=1, fenetre=run.Fenetre(heure(21), heure(6))
    )
    c.jouer()
    assert sum(horloge.sommes[:6]) == 3600 and len(serveur.executer) == 1


def test_a_la_fermeture_de_la_fenetre_on_s_arrete(tmp_path, variantes, questions):
    serveur = FausseCible()
    c = _campagne(tmp_path, Horloge(), serveur, variantes, questions, debut=datetime(2026, 11, 2, 5, 59, 50), phases=("harnais",), fenetre=run.Fenetre(heure(21), heure(6)))
    e = c.jouer()
    assert e["phases"]["harnais"] == "fenetre" and 0 < len(serveur.executer) < 10


def test_la_phase_mcp_compte_son_budget_de_modele(tmp_path, variantes, questions):
    serveur = FausseCible()
    modele = FauxModele(max_appels=2 * run.MAX_TOURS)
    e = _campagne(tmp_path, Horloge(), serveur, variantes, questions, passerelle=modele, phases=("mcp",)).jouer()
    assert e["phases"]["mcp"] == "budget-modele"
    lignes = [json.loads(li) for li in (tmp_path / "2026-11-01" / "essais.jsonl").read_text().splitlines()]
    assert [d["cle"].split("|")[:2] for d in lignes] == [["mcp", "agent"]] * 4  # 12 appels, 2 par conversation, 6 de marge exigés avant chacune
    assert lignes[0]["verdicts"]["outils"] == ["lister_sources"] and lignes[0]["appels_modele"] == 2


def test_le_catalogue_tire_un_passage_et_fait_ecrire_la_question(tmp_path, variantes, questions):
    serveur = FausseCible()
    modele = FauxModele()
    c = _campagne(tmp_path, Horloge(), serveur, variantes, questions[:1], passerelle=modele, phases=("mcp",), catalogue=1, juge_modele="juge")
    assert c.jouer()["phases"]["mcp"] == "complet"
    lignes = [json.loads(li) for li in (tmp_path / "2026-11-01" / "essais.jsonl").read_text().splitlines()]
    catalogue = lignes[-1]
    assert catalogue["variante"] == "catalogue" and catalogue["question"] == "catalogue-un"  # les collections d'essai sont écartées
    assert catalogue["texte"] == "Quelles pièces pour un duplicata ?" and catalogue["temoin"] == "/api/openrag/extract/m1"
    assert lignes[0]["juge"] == {"verdict": "conforme", "justification": "ok"}


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [("21h-6h", (heure(21), heure(6))), ("21:30-05:45", (heure(21, 30), heure(5, 45))), ("9h-17h", (heure(9), heure(17)))],
)
def test_lire_fenetre(texte, attendu):
    f = run.lire_fenetre(texte)
    assert f is not None and (f.debut, f.fin) == attendu
    assert run.lire_fenetre("maintenant") is None
    with pytest.raises(Usage):
        run.lire_fenetre("ce soir")


def test_la_nuit_est_celle_du_soir_ou_la_fenetre_s_ouvre():
    f = run.Fenetre(heure(21), heure(6))
    assert f.nuit_de(datetime(2026, 11, 2, 2, 0)).isoformat() == "2026-11-01"
    assert f.nuit_de(datetime(2026, 11, 1, 23, 0)).isoformat() == "2026-11-01"
    assert f.attente_s(datetime(2026, 11, 1, 20, 0)) == 3600 and f.attente_s(datetime(2026, 11, 1, 22, 0)) == 0
    assert f.attente_s(datetime(2026, 11, 2, 7, 0)) == 14 * 3600


def test_les_rapports_ne_s_ecrivent_jamais_dans_le_depot(tmp_path):
    with pytest.raises(Usage):
        run.dossier_rapports(str(run.RACINE / "rapports"))
    assert run.dossier_rapports(str(tmp_path)) == tmp_path.resolve()


# ─── De bout en bout, par main() ─────────────────────────────────────────────────────────────


def _fabrique(serveur, modele=None):
    horloge = Horloge()

    def fabrique(a):
        return Cible(a.cible, FauxSso(horloge), client=httpx.Client(transport=httpx.MockTransport(serveur)), cadences=a.cadences, horloge=horloge, dormir=horloge.dormir), modele

    return fabrique


def _main(tmp_path, serveur, *args, modele=None):
    argv = ["--cible", BASE, "--rapports", str(tmp_path), "--nuit", "2026-11-01", *args]
    return run.main(argv, fabrique=_fabrique(serveur, modele))


def test_une_nuit_courte_produit_le_rapport_et_se_reprend(tmp_path, correspondance):
    serveur = FausseCible()
    assert _main(tmp_path, serveur, "--fenetre", "maintenant", "--max-executer", "30", "--phases", "harnais") == 0
    assert len(serveur.executer) == 30
    nuit = tmp_path / "2026-11-01"
    mesures = json.loads((nuit / "mesures.json").read_text())
    assert mesures["harnais"]["variantes"]["s2"]["essais"] == 10 and mesures["consommation"]["executer"] == 30
    assert (nuit / "synthese.md").read_text().startswith("# Campagne de recherche — nuit du 2026-11-01")
    encore = FausseCible()
    assert _main(tmp_path, encore, "--fenetre", "maintenant", "--max-executer", "30", "--phases", "harnais") == 0
    assert encore.executer == []


def test_une_regle_d_arret_rend_le_code_3(tmp_path, correspondance):
    assert _main(tmp_path, FausseCible(source="essai-secrete"), "--fenetre", "maintenant", "--phases", "harnais") == 3
    assert "ALERTE : 1 incident(s) de droits" in (tmp_path / "2026-11-01" / "synthese.md").read_text()


def test_trois_nuits_du_meme_arret_arretent_la_campagne(tmp_path, correspondance):
    for jour in ("2026-10-29", "2026-10-30", "2026-10-31"):
        d = tmp_path / jour
        d.mkdir()
        (d / "etat.json").write_text(json.dumps({"executions": [{"arret": {"motif": "5xx"}}]}))
    serveur = FausseCible()
    assert _main(tmp_path, serveur, "--fenetre", "maintenant", "--phases", "harnais", "--max-executer", "1") == 4
    assert serveur.executer == []
    assert _main(tmp_path, serveur, "--fenetre", "maintenant", "--phases", "harnais", "--max-executer", "1", "--forcer") == 0


def test_la_phase_mcp_sans_passerelle_est_refusee(tmp_path, correspondance):
    assert _main(tmp_path, FausseCible(), "--fenetre", "maintenant") == 2


def test_la_cadence_ne_depasse_pas_le_quota(tmp_path, correspondance):
    assert _main(tmp_path, FausseCible(), "--cadence-assistants", "30", "--phases", "harnais") == 2
    assert not Path(tmp_path / "2026-11-01").exists()


def test_arret_est_une_exception_de_regle():
    assert issubclass(run.Arret, Exception) and Arret("x").motif == "x"
