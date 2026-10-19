"""Le contrat du harnais (ADR-0003) : la fiche et le plan du brief se valident et se
re-sérialisent ; les incohérences sont refusées ; l'empreinte ne dépend que du contenu ; la
projection sur le contrat v1 rend exactement la forme de la recherche ; le journal n'a aucun
champ de texte libre ; le paquet n'importe ni FastAPI ni la base."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.harnais import contrat
from app.harnais.contrat import (
    Appelant,
    Canaux,
    Contexte,
    Etape,
    FicheAssistant,
    FicheSource,
    JournalEtape,
    JournalPlan,
    Passage,
    Plan,
    Resultat,
    canonique,
    empreinte,
    vers_resultats_v1,
)
from app.harnais.interfaces import Apparieur, Connecteur, Planificateur

FICHE_SEJOUR = {
    "assistant": "sejour-des-etrangers",
    "titre": "Séjour des étrangers",
    "rubrique": "droit-etrangers",
    "description": "Le droit au séjour : accords bilatéraux, code, référentiel d'éligibilité.",
    "sources": [
        {"id": "accords-bilateraux", "type": "collection", "regime": "selon_question", "rang": 1},
        {"id": "ceseda", "type": "collection", "regime": "toujours", "rang": 2},
        {"id": "referentiel-eligibilite", "type": "connecteur", "regime": "sur_consigne"},
    ],
    "consignes": [
        {"id": "defaut", "quand": "toujours", "gabarit": "generic"},
        {
            "id": "pays-a-accord",
            "quand": "la personne est ressortissante d'un pays lié par un accord bilatéral",
            "exemples": [
                "Un Algérien marié à une Française peut-il obtenir un titre de séjour ?",
                "Quel titre pour un Tunisien salarié ?",
                "Un Marocain étudiant peut-il travailler ?",
            ],
            "chercher": [{"source": "accords-bilateraux"}, {"source": "ceseda"}, {"source": "referentiel-eligibilite", "avec": "article_trouve"}],
            "repondre": "Citer l'article de l'accord avant celui du code, puis lister les pièces du référentiel.",
        },
    ],
    "publication": {"socle": True, "portail": True, "fenetre_js": True, "api": True},
    "validation_requise": False,
}

PLAN_SEJOUR = {
    "assistant": "sejour-des-etrangers",
    "version": 3,
    "planificateur": "regles",
    "consigne": "pays-a-accord",
    "score_consigne": 0.83,
    "reponse_fiable": None,
    "etapes": [
        {"n": 1, "source": "accords-bilateraux", "question": "Un Algérien marié à une Française…", "poids": 1.0, "attend": []},
        {"n": 2, "source": "ceseda", "question": "titre de séjour conjoint de Français", "poids": 0.8, "attend": []},
        {"n": 3, "source": "referentiel-eligibilite", "question": "pièces à fournir", "poids": 0.8, "attend": [1, 2], "avec": "article_trouve"},
    ],
    "sources_ignorees": 1,
    "a_valider": False,
}


# ─── La fiche ────────────────────────────────────────────────────────────────────────────────


def test_la_fiche_du_brief_se_valide_et_se_reserialise():
    fiche = FicheAssistant.model_validate(FICHE_SEJOUR)
    assert fiche.contrat == 1 and fiche.seuil_fiable == 0.9 and fiche.reference is None
    rendu = fiche.model_dump(mode="json")
    assert rendu["sources"][2]["rang"] is None and rendu["publication"]["api"] is True
    assert FicheAssistant.model_validate(rendu) == fiche
    assert [s.id for s in fiche.sources_ordonnees()] == ["accords-bilateraux", "ceseda", "referentiel-eligibilite"]


@pytest.mark.parametrize(
    "modif, motif",
    [
        (lambda f: f["consignes"][1]["chercher"].append({"source": "inconnue"}), "n'est pas une source"),
        (lambda f: f["sources"].append(dict(f["sources"][0])), "même identifiant"),
        (lambda f: f["sources"][0].update(regime="parfois"), "regime"),
        (lambda f: f["consignes"].append({"id": "autre", "quand": "toujours"}), "une seule consigne"),
        (lambda f: f["consignes"][1]["chercher"][0].update(avec="x_y"), "première étape"),
        (lambda f: f.update(assistant="Séjour"), "assistant"),
        (lambda f: f.update(sources=[]), "sources"),
        (lambda f: f.update(inconnu=1), "inconnu"),
        (lambda f: f["consignes"][1].update(exemples=[" "]), "exemple"),
    ],
)
def test_une_fiche_incoherente_est_refusee(modif, motif):
    f = copy.deepcopy(FICHE_SEJOUR)
    modif(f)
    with pytest.raises(ValidationError) as e:
        FicheAssistant.model_validate(f)
    assert motif in str(e.value)


def test_les_chaines_sont_depouillees():
    f = copy.deepcopy(FICHE_SEJOUR)
    f["titre"] = "  Séjour des étrangers  "
    assert FicheAssistant.model_validate(f).titre == "Séjour des étrangers"


# ─── Canonicalisation et empreinte ───────────────────────────────────────────────────────────


def test_canonique_ne_depend_ni_de_l_ordre_des_cles_ni_des_espaces():
    a = FicheAssistant.model_validate(FICHE_SEJOUR)
    melange = json.loads(json.dumps(FICHE_SEJOUR))
    melange = {k: melange[k] for k in reversed(list(melange))}
    melange["titre"] = "   Séjour des étrangers "
    b = FicheAssistant.model_validate(melange)
    assert canonique(a) == canonique(b)
    assert empreinte(canonique(a)) == empreinte(canonique(b))
    assert len(empreinte(canonique(a))) == 64


def test_canonique_est_sensible_a_l_ordre_des_sources_pas_aux_canaux():
    a = FicheAssistant.model_validate(FICHE_SEJOUR)
    f = copy.deepcopy(FICHE_SEJOUR)
    f["publication"] = {"socle": False, "portail": False, "fenetre_js": False, "api": False}
    f["reference"] = {"questions": 12, "fiables": 2, "par_source": {"ceseda": 12}}
    assert canonique(FicheAssistant.model_validate(f)) == canonique(a), "les canaux et le dérivé sont hors de l'empreinte"
    f["sources"] = [f["sources"][1], f["sources"][0], f["sources"][2]]
    assert canonique(FicheAssistant.model_validate(f)) != canonique(a), "l'ordre des sources est du contenu"
    assert '"contrat":1' in canonique(a), "la version du contrat est dans l'empreinte"


def test_depuis_canonique_rend_la_fiche_avec_les_canaux_du_moment():
    a = FicheAssistant.model_validate(FICHE_SEJOUR)
    b = FicheAssistant.depuis_canonique(canonique(a), Canaux(api=True))
    assert b.publication == Canaux(api=True) and canonique(b) == canonique(a)


# ─── Le plan ─────────────────────────────────────────────────────────────────────────────────


def test_le_plan_du_brief_se_valide():
    plan = Plan.model_validate(PLAN_SEJOUR)
    assert plan.etapes[2].attend == [1, 2] and plan.etapes[2].avec == "article_trouve"
    assert Plan.model_validate(plan.model_dump(mode="json")) == plan


@pytest.mark.parametrize(
    "modif, motif",
    [
        (lambda p: p["etapes"][2].update(attend=[3]), "ne la précède pas"),
        (lambda p: p["etapes"][2].update(attend=[9]), "ne la précède pas"),
        (lambda p: p["etapes"][0].update(avec="article_trouve"), "attend au moins"),
        (lambda p: p["etapes"][1].update(n=1), "même numéro"),
        (lambda p: p.update(reponse_fiable={"id": "q1", "score": 0.95}), "dispense de toute étape"),
        (lambda p: p["etapes"][0].update(poids=0), "poids"),
        (lambda p: p.update(planificateur="magie"), "planificateur"),
    ],
)
def test_un_plan_incoherent_est_refuse(modif, motif):
    p = copy.deepcopy(PLAN_SEJOUR)
    modif(p)
    with pytest.raises(ValidationError) as e:
        Plan.model_validate(p)
    assert motif in str(e.value)


def test_une_reponse_fiable_retenue_fait_un_plan_sans_etape():
    p = Plan(assistant="a-b-c", version=1, planificateur="regles", reponse_fiable={"id": "q1", "score": 0.95})
    assert p.etapes == [] and p.reponse_fiable.score == 0.95


def test_le_contexte_et_l_appelant():
    c = Contexte(canal="portail", capacites_client={"valider"}, sources_lisibles=["ceseda"])
    assert c.model_dump(mode="json")["capacites_client"] == ["valider"] and c.top_k == 20
    a = Appelant(sub="abc", jeton="secret-123")
    assert "secret-123" not in repr(a) and "secret-123" not in json.dumps(a.model_dump(mode="json"))
    assert a.jeton.get_secret_value() == "secret-123"


# ─── Le journal ──────────────────────────────────────────────────────────────────────────────


def test_le_journal_n_a_aucun_champ_de_texte_libre():
    assert "question" not in JournalPlan.model_fields and "question" not in JournalEtape.model_fields
    j = JournalPlan(
        assistant="a-b-c",
        version=1,
        empreinte="0" * 64,
        canal="api",
        planificateur="regles",
        duree_ms=12,
        robot="banc",
        etapes=[JournalEtape(n=1, source="ceseda", poids=1.0, duree_ms=12, passages=3, erreur="delai")],
    )
    for nom, champ in JournalPlan.model_fields.items():
        if champ.annotation in (str, str | None):
            assert nom in ("assistant", "empreinte", "consigne", "auteur_hash", "robot"), f"{nom} est un texte libre"
    with pytest.raises(ValidationError):
        JournalEtape(n=1, source="x", poids=1.0, duree_ms=1, passages=0, erreur="la question était : …")
    assert j.model_dump()["etapes"][0]["erreur"] == "delai"


def test_un_journal_a_un_auteur_ou_un_robot_jamais_les_deux():
    base = dict(assistant="a-b-c", version=1, empreinte="f" * 64, canal="socle", planificateur="llm", duree_ms=1)
    with pytest.raises(ValidationError):
        JournalPlan(**base)
    with pytest.raises(ValidationError):
        JournalPlan(**base, robot="banc", auteur_hash="a" * 32)
    assert JournalPlan(**base, auteur_hash="a" * 32).reponse_fiable is False


# ─── La projection sur le contrat v1 ─────────────────────────────────────────────────────────


def test_la_projection_rend_la_forme_exacte_de_la_recherche_v1():
    """Les mêmes morceaux, par `recherche._construire` et par `vers_resultats_v1` : même sortie."""
    from app.auth import CurrentUser
    from app.routers import recherche
    from app.services.morceau import decouper_morceau
    from tests.unit.test_recherche import _doc

    user = CurrentUser(sub="alice", username="alice", groups=["/g/mirai-beta-testeurs"])
    fiches = {
        "partagee": {"name": "partagee", "titre": "Méthodes de l'équipe", "scope": "group", "scope_groups": ["/g/mirai-beta-testeurs"], "created_by": "bob"},
        "mienne": {"name": "mienne", "titre": "Mes notes", "scope": "private", "scope_groups": [], "created_by": "alice"},
    }
    from app.services.openrag_client import DocumentRecherche

    bruts = [
        _doc(
            "partagee",
            "methodes-2024",
            101,
            "# Méthodes\n\nLe budget de l'équipe est voté en janvier.",
            title="Méthodes 2024",
            created_at="2024-01-15T09:00:00+00:00",
            relevance_score=0.91,
        ),
        _doc("partagee", "methodes-2024", 102, "Le budget se révise en juin, après le bilan.", title="Méthodes 2024", created_at="2024-01-15T09:00:00+00:00", relevance_score=0.8),
        _doc("mienne", "notes-budget", 201, "Notes : budget prévisionnel, puis budget réalisé.", relevance_score=0.75, page=2),
        *[_doc("mienne", "long", 300 + i, f"passage {i} sur le budget", relevance_score=0.5 - i / 100) for i in range(5)],
    ]
    docs = [DocumentRecherche.model_validate(d) for d in bruts]
    motif = recherche._motif("budget")
    attendu = recherche._construire(docs, fiches, user, motif, None, None)

    passages = []
    for i, d in enumerate(docs, start=1):
        meta = d.metadata
        _, fichier, _ = decouper_morceau(d.content)
        ident = recherche._ident_morceau(d, meta)
        passages.append(
            Passage(
                source=meta["partition"],
                etape=1,
                rang=i,
                score=recherche._score(meta),
                ident=ident,
                document=str(meta["file_id"]),
                titre=recherche._titre_du_document(meta, fichier),
                date=recherche._date(meta),
                page=recherche._page(meta),
                texte=recherche._texte_brut(d.content),
                url=recherche._lien(ident),
            )
        )
    obtenu = vers_resultats_v1(
        passages,
        extrait=lambda t: recherche._extrait(t, motif),
        surlignages=lambda e: recherche._surlignages(e, motif),
        titres={n: f["titre"] for n, f in fiches.items()},
        droit=lambda s: recherche._droit(fiches[s], user)[0],
    )
    assert obtenu == attendu
    assert [len(r["hits"]) for r in obtenu] == [2, 1, 3], "au plus trois passages par document"


def test_un_resultat_se_serialise_avec_son_plan():
    plan = Plan.model_validate(PLAN_SEJOUR)
    p = Passage(source="ceseda", etape=2, rang=1, score=0.7, document="L423-1", texte="Le conjoint…", date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    r = Resultat(plan=plan, passages=[p], duree_ms=42, par_source={"ceseda": 1})
    rendu = r.model_dump(mode="json")
    assert rendu["passages"][0]["date"] == "2024-01-01T00:00:00Z" and rendu["plan"]["consigne"] == "pays-a-accord"
    assert Resultat.model_validate(rendu) == r


def test_fiche_source_et_constantes():
    fs = FicheSource(id="referentiel-eligibilite", type="connecteur", titre="Référentiel d'éligibilité", relais=["article_trouve"])
    assert fs.relais == ["article_trouve"]
    assert contrat.CANAUX_JOURNAL == ("socle", "portail", "fenetre_js", "api", "bac-a-sable", "banc")
    assert contrat.PLANIFICATEURS == ("toutes_les_sources", "regles", "llm")


# ─── Les interfaces et la pureté du paquet ───────────────────────────────────────────────────


def test_les_interfaces_sont_abstraites_et_implementables():
    for cls in (Planificateur, Connecteur, Apparieur):
        with pytest.raises(TypeError):
            cls()

    class Theatre(Connecteur):
        type = "collection"

        async def chercher(self, etape: Etape, identite: Appelant, *, amont=()) -> list[Passage]:
            return [Passage(source=etape.source, etape=etape.n, rang=1, document="d", texte="t")]

        async def fiche(self) -> FicheSource:
            return FicheSource(id="ceseda", type="collection", titre="CESEDA")

    import asyncio

    e = Etape(n=1, source="ceseda", question="q")
    assert asyncio.run(Theatre().chercher(e, Appelant(sub="s")))[0].source == "ceseda"


def test_le_paquet_harnais_n_importe_ni_fastapi_ni_la_base():
    code = (
        "import sys; import app.harnais.contrat, app.harnais.interfaces; "
        "interdits = {m for m in ('fastapi', 'starlette', 'sqlalchemy', 'app.database', 'app.config', 'httpx') if m in sys.modules}; "
        "assert not interdits, interdits; print('pur')"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "pur", r.stderr
