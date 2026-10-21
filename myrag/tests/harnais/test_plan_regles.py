"""Le planificateur par règles : consigne reconnue, repli sur les régimes, jamais `sur_consigne`."""

from __future__ import annotations

import httpx
import pytest

from app.harnais.apparieur import ApparieurEmbeddings, ApparieurSacDeMots, mots
from app.harnais.contrat import Contexte, FicheAssistant
from app.harnais.plan.regles import Regles

QUESTION_CEDESA = "Quel titre de séjour pour le conjoint d'un Français ?"


def _fiche(**modifs) -> FicheAssistant:
    f = {
        "assistant": "sejour-essai",
        "titre": "Séjour",
        "sources": [
            {"id": "toujours-a", "type": "collection", "regime": "toujours", "rang": 1},
            {"id": "selon-budget", "type": "collection", "regime": "selon_question", "rang": 2},
            {"id": "selon-sejour", "type": "collection", "regime": "selon_question", "rang": 3},
            {"id": "sur-consigne-x", "type": "collection", "regime": "sur_consigne", "rang": 4},
            {"id": "sur-consigne-y", "type": "collection", "regime": "sur_consigne", "rang": 5},
        ],
        "consignes": [
            {
                "id": "conjoint",
                "quand": "La question porte sur le séjour du conjoint d'un Français",
                "exemples": ["Mon mari est français, quel titre de séjour ?", "Carte de séjour pour une épouse de ressortissant"],
                "chercher": [{"source": "sur-consigne-x"}, {"source": "sur-consigne-y", "avec": "article_trouve"}, {"source": "selon-sejour"}],
                "repondre": "Citer l'article.",
            },
            {"id": "budget", "quand": "Une question sur le budget de l'équipe", "exemples": ["Quel est le budget voté ?"], "chercher": [{"source": "selon-budget"}]},
        ],
    }
    f.update(modifs)
    return FicheAssistant.model_validate(f)


def _contexte(fiche: FicheAssistant, lisibles: list[str] | None = None) -> Contexte:
    return Contexte(canal="api", sources_lisibles=[s.id for s in fiche.sources] if lisibles is None else lisibles)


DESCRIPTIONS = {
    "toujours-a": "Textes de référence de l'administration",
    "selon-budget": "Budget de l'équipe : crédits votés, dépenses, prévisions",
    "selon-sejour": "Droit des étrangers : titres de séjour, cartes, visas",
}


def _regles(**kw) -> Regles:
    return Regles(ApparieurSacDeMots(), descriptions=DESCRIPTIONS, **kw)


@pytest.mark.asyncio
async def test_l_exemple_d_une_consigne_la_fait_reconnaitre():
    fiche = _fiche()
    plan = await _regles().plan(fiche, "Mon mari est français, quel titre de séjour ?", _contexte(fiche))
    assert plan.planificateur == "regles" and plan.consigne == "conjoint"
    assert plan.score_consigne == 1.0  # l'exemple mot pour mot
    assert plan.version == 1 and plan.assistant == "sejour-essai"


@pytest.mark.asyncio
async def test_une_question_proche_du_quand_reconnait_la_consigne_avec_un_score():
    fiche = _fiche()
    plan = await _regles().plan(fiche, QUESTION_CEDESA, _contexte(fiche))
    assert plan.consigne == "conjoint" and 0.3 <= plan.score_consigne < 1.0


@pytest.mark.asyncio
async def test_les_etapes_de_la_consigne_dans_l_ordre_avec_leur_relais():
    fiche = _fiche()
    plan = await _regles().plan(fiche, QUESTION_CEDESA, _contexte(fiche))
    assert [(e.n, e.source) for e in plan.etapes[:3]] == [(1, "sur-consigne-x"), (2, "sur-consigne-y"), (3, "selon-sejour")]
    e1, e2, e3 = plan.etapes[:3]
    assert e1.attend == [] and e1.avec is None
    assert e2.attend == [1] and e2.avec == "article_trouve"  # « avec » attend l'étape précédente
    assert e3.attend == [] and e3.avec is None
    # La source `toujours` que la consigne ne cite pas s'y ajoute, à poids réduit.
    assert [(e.source, e.poids) for e in plan.etapes[3:]] == [("toujours-a", 0.5)]
    assert all(e.question == QUESTION_CEDESA for e in plan.etapes)


@pytest.mark.asyncio
async def test_les_sources_sur_consigne_sont_planifiees_quand_une_consigne_les_cite():
    fiche = _fiche()
    plan = await _regles().plan(fiche, QUESTION_CEDESA, _contexte(fiche))
    assert {"sur-consigne-x", "sur-consigne-y"} <= {e.source for e in plan.etapes}


@pytest.mark.asyncio
async def test_rien_ne_correspond_toujours_et_selon_question_ressemblantes_jamais_sur_consigne():
    fiche = _fiche()
    plan = await _regles().plan(fiche, "Les crédits et les dépenses prévus pour les déplacements", _contexte(fiche))
    assert plan.consigne is None and plan.score_consigne is None
    sources = [e.source for e in plan.etapes]
    assert sources == ["toujours-a", "selon-budget"]  # `selon-sejour` ne ressemble pas ; aucune `sur_consigne`
    assert plan.etapes[0].poids == 1.0 and 0.5 <= plan.etapes[1].poids <= 1.0


@pytest.mark.asyncio
async def test_sous_le_seuil_c_est_comme_rien():
    fiche = _fiche()
    rien = await _regles().plan(fiche, "zzz yyy xxx", _contexte(fiche))
    presque = await _regles(seuil=0.99).plan(fiche, "Quel est le budget ?", _contexte(fiche))  # proche, mais sous un seuil exigeant
    assert rien.consigne is None and presque.consigne is None
    for plan in (rien, presque):
        assert not {e.source for e in plan.etapes} & {"sur-consigne-x", "sur-consigne-y"}
        assert plan.etapes[0].source == "toujours-a"
    assert [e.source for e in rien.etapes] == ["toujours-a"]  # rien ne ressemble : les `toujours` seules


@pytest.mark.asyncio
async def test_aucune_source_retenue_toutes_les_selon_question_jamais_sur_consigne():
    fiche = _fiche(sources=[{"id": "selon-a", "type": "collection", "regime": "selon_question"}, {"id": "sur-b", "type": "collection", "regime": "sur_consigne"}], consignes=[])
    plan = await Regles(ApparieurSacDeMots()).plan(fiche, "n'importe quoi", _contexte(fiche))
    assert [e.source for e in plan.etapes] == ["selon-a"]


@pytest.mark.asyncio
async def test_une_source_illisible_n_est_jamais_planifiee_et_se_compte():
    fiche = _fiche()
    plan = await _regles().plan(fiche, QUESTION_CEDESA, _contexte(fiche, lisibles=["toujours-a", "selon-sejour", "sur-consigne-y"]))
    assert [e.source for e in plan.etapes] == ["sur-consigne-y", "selon-sejour", "toujours-a"]
    # L'étape 2 « avec » a perdu son étape amont (illisible) : plus de relais.
    assert plan.etapes[0].attend == [] and plan.etapes[0].avec is None
    assert plan.sources_ignorees == 1  # `sur-consigne-x`, sans la nommer
    plan2 = await _regles().plan(fiche, "zzz", _contexte(fiche, lisibles=["toujours-a"]))
    assert plan2.sources_ignorees == 2  # selon-budget et selon-sejour visées, illisibles


@pytest.mark.asyncio
async def test_une_consigne_toujours_avec_etapes_sert_de_defaut():
    fiche = _fiche(consignes=[{"id": "defaut", "quand": "toujours", "chercher": [{"source": "selon-budget"}, {"source": "selon-sejour"}]}])
    plan = await _regles().plan(fiche, "zzz", _contexte(fiche))
    assert plan.consigne == "defaut" and plan.score_consigne == 0.0
    assert [e.source for e in plan.etapes[:2]] == ["selon-budget", "selon-sejour"]


@pytest.mark.asyncio
async def test_la_validation_demandee_se_lit_dans_les_capacites_du_client():
    fiche = _fiche(validation_requise=True)
    sans = await _regles().plan(fiche, "zzz", _contexte(fiche))
    avec = await _regles().plan(fiche, "zzz", _contexte(fiche).model_copy(update={"capacites_client": {"valider"}}))
    assert (sans.a_valider, avec.a_valider) == (False, True)


# ─── Les apparieurs ──────────────────────────────────────────────────────────────────────────


def test_les_mots_portent_le_sens():
    assert mots("Quels sont les titres de séjour du conjoint ?") == ["titre", "sejour", "conjoint"]
    assert mots("l'ÉPOUSE et les épouses") == ["epouse", "epouse"]


@pytest.mark.asyncio
async def test_le_sac_de_mots_est_deterministe_et_ordonne():
    a = ApparieurSacDeMots()
    candidats = [("x", "budget de l'équipe"), ("y", "titre de séjour"), ("z", "")]
    r1 = await a.apparier("titre de séjour du conjoint", candidats)
    assert r1 == await a.apparier("titre de séjour du conjoint", candidats)
    assert [i for i, _ in r1] == ["y", "x", "z"] and r1[0][1] > 0.5 and r1[1][1] == 0.0
    assert (await a.apparier("titre de séjour", [("y", "titre de séjour")]))[0][1] == 1.0


@pytest.mark.asyncio
async def test_les_embeddings_sont_utilises_quand_l_api_repond(monkeypatch):
    vecteurs = {"question": [1.0, 0.0], "proche": [0.9, 0.1], "loin": [0.0, 1.0]}

    async def faux_post(self, url, json=None, headers=None, **_):
        assert url == "http://openrag.fake-domain.name/v1/embeddings" and json["model"] == "modele-essai"
        data = [{"index": i, "embedding": vecteurs[t]} for i, t in enumerate(json["input"])]
        return httpx.Response(200, json={"data": list(reversed(data))}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", faux_post)
    a = ApparieurEmbeddings("http://openrag.fake-domain.name/", "modele-essai")
    r = await a.apparier("question", [("loin", "loin"), ("proche", "proche")])
    assert [i for i, _ in r] == ["proche", "loin"] and r[0][1] > 0.99 and r[1][1] == 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize("panne", [httpx.ConnectError("coupé"), httpx.ReadTimeout("lent")])
async def test_embeddings_injoignables_repli_sur_le_sac_de_mots_sans_erreur(monkeypatch, panne):
    async def faux_post(self, *a, **k):
        raise panne

    monkeypatch.setattr(httpx.AsyncClient, "post", faux_post)
    r = await ApparieurEmbeddings("http://openrag.fake-domain.name", "m").apparier("titre de séjour", [("a", "titre de séjour"), ("b", "budget")])
    assert r == [("a", 1.0), ("b", 0.0)]


@pytest.mark.asyncio
async def test_embeddings_en_erreur_http_ou_mal_formes_repli(monkeypatch):
    for reponse in (httpx.Response(500, request=httpx.Request("POST", "http://x")), httpx.Response(200, json={"oups": 1}, request=httpx.Request("POST", "http://x"))):

        async def faux_post(self, *a, _r=reponse, **k):
            return _r

        monkeypatch.setattr(httpx.AsyncClient, "post", faux_post)
        r = await ApparieurEmbeddings("http://x", "m").apparier("budget", [("a", "budget")])
        assert r == [("a", 1.0)]
