"""Le moteur de génération de bout en bout, avec un modèle de langage simulé.

Le faux modèle est un modèle de chat LangChain, enveloppé par le VRAI `LLMCompte` : on teste ainsi
le compteur et l'appel en fil de production. Il reconnaît chaque prompt de ragas par le schéma de
sortie que ragas y écrit (`entities`, `mapping`, `query`/`answer`), pas par l'instruction en
anglais : le test reste valable avec les prompts français.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading

import pytest

pytest.importorskip("ragas")

from langchain_core.embeddings import FakeEmbeddings  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from ragas.run_config import RunConfig  # noqa: E402

from app.generation import modele, moteur  # noqa: E402
from app.generation.morceaux import Morceau  # noqa: E402

TEXTES = [
    "Le préfet de la Gironde délivre la carte de séjour pluriannuelle à Bordeaux après avis de l'OFII.",
    "La Direction des systèmes d'information gère le parc informatique et attribue les postes Windows.",
    "Un agent du Service du numérique peut demander un accès VPN en écrivant au Support utilisateurs.",
    "La messagerie Tchap remplace WhatsApp pour les échanges professionnels au Ministère de l'Intérieur.",
    "Le badge Navigo est remboursé à moitié par la Direction des ressources humaines chaque mois.",
    "La Préfecture de police instruit les demandes de naturalisation pour les résidents de Paris.",
    "Le Comité social d'administration se réunit trois fois par an au Bâtiment Lumière.",
    "Pour réinitialiser un mot de passe Cerbère, appelez le Centre de services au 3400.",
]
PERSONAS = [
    moteur.PersonaDemande("Agent d'accueil", "Agent au guichet d'une préfecture, répond aux usagers."),
    moteur.PersonaDemande("Technicien support", "Technicien du support informatique, aide les agents."),
]


def _morceaux() -> list[Morceau]:
    return [Morceau(f"c{i}", f"f{i}", "faq-sdst", f"doc-{i}.md", None, t) for i, t in enumerate(TEXTES)]


def _entree(texte: str) -> dict:
    """Le dernier bloc « input: {...} » d'un prompt de ragas."""
    # Le prompt de réparation contient le prompt d'origine, ÉCHAPPÉ (« \\n ») : on découpe sur un
    # vrai saut de ligne pour prendre l'entrée extérieure.
    bloc = texte.rsplit("\ninput: ", 1)[-1]
    bloc = bloc.split("\nOutput", 1)[0].strip()
    return json.loads(bloc)


class ChatSimule(BaseChatModel):
    pannes_ner: int = 1  # la première extraction répond hors JSON : exerce la réparation
    question_impossible: str = ""  # un terme pour lequel la paire ne sort jamais en JSON
    appels: int = 0

    def __init__(self, **kw):
        super().__init__(**kw)
        object.__setattr__(self, "_verrou", threading.Lock())

    @property
    def _llm_type(self) -> str:
        return "simule"

    def _combine_llm_outputs(self, sorties):
        total = {"prompt_tokens": 0, "completion_tokens": 0}
        for s in sorties:
            for k in total:
                total[k] += ((s or {}).get("token_usage") or {}).get(k, 0)
        return {"token_usage": total}

    def _generate(self, messages, stop=None, run_manager=None, **kw) -> ChatResult:
        texte = messages[-1].content
        with self._verrou:
            self.appels += 1
        sortie = self._repondre(texte)
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=sortie), generation_info={"finish_reason": "stop"})],
            llm_output={"token_usage": {"prompt_tokens": len(texte) // 4, "completion_tokens": len(sortie) // 4}},
        )

    def _repondre(self, texte: str, reparation: bool = False) -> str:
        if modele.MARQUE_REPARATION in texte:
            origine = _entree(texte)["prompt_value"]
            return json.dumps({"text": self._repondre(origine, reparation=True)})
        if '"entities"' in texte:
            with self._verrou:
                panne = self.pannes_ner > 0 and not reparation
                if panne:
                    self.pannes_ner -= 1
            if panne:
                return "Voici les entités : Gironde, Bordeaux"
            mots = re.findall(r"\b[A-ZÉÈ][\w'éèêàç-]{2,}", _entree(texte)["text"])
            return json.dumps({"entities": sorted(set(mots))[:5]})
        if '"mapping"' in texte:
            e = _entree(texte)
            # Le modèle réécrit un nom (casse) : le moteur doit le rapprocher, pas échouer.
            return json.dumps({"mapping": {p["name"].upper() if i else p["name"]: e["themes"][:3] for i, p in enumerate(e["personas"])}})
        if '"keyphrases"' in texte:
            mots = re.findall(r"\b[a-zéè]{6,}", _entree(texte)["text"])
            return json.dumps({"keyphrases": sorted(set(mots))[:4]})
        if '"query"' in texte and '"answer"' in texte:
            e = _entree(texte)
            if self.question_impossible and e["term"] == self.question_impossible:
                return "je ne sais pas répondre"
            return json.dumps({"query": f"Que faut-il savoir sur {e['term']} ?", "answer": f"D'après le passage : {e['context'][:60]}"})
        raise AssertionError("prompt inattendu : " + texte[:200])


def _generer(chat: ChatSimule, taille=4, distribution=None, personas=PERSONAS, morceaux=None, tmp_path=None):
    compteurs = modele.Compteurs()
    llm = modele.LLMCompte(chat, compteurs)
    emb = modele.EmbeddingsComptes(FakeEmbeddings(size=8), compteurs)
    phases: list[str] = []
    kw = {"dossier_prompts": tmp_path} if tmp_path else {}
    r = asyncio.run(
        asyncio.to_thread(
            moteur.generer,
            morceaux if morceaux is not None else _morceaux(),
            personas,
            taille,
            llm,
            emb,
            distribution=distribution,
            run_config=RunConfig(max_workers=2, timeout=10, max_retries=1, max_wait=1),
            progression=phases.append,
            **kw,
        )
    )
    return r, compteurs, phases


def test_paires_reliees_a_leurs_passages_et_comptees():
    r, c, phases = _generer(ChatSimule())
    assert r.etat == "termine", r.erreur
    assert 1 <= len(r.paires) <= 4 and r.paires_echouees == 0
    ids = {f"c{i}": f"f{i}" for i in range(8)}
    for p in r.paires:
        assert p.chunk_ids and all(cid in ids for cid in p.chunk_ids)
        assert p.contextes[0]["file_id"] == ids[p.contextes[0]["chunk_id"]]
        assert p.contextes[0]["texte"] in TEXTES
        assert p.persona_nom in {x.nom for x in PERSONAS}
        assert p.question.endswith("?") and p.reponse
        assert p.synthetiseur == "paire_simple_entites"
        assert p.style and p.longueur
    assert phases == ["extraction", "generation"]
    assert r.morceaux_envoyes == 8 and r.noeuds_avec_proprietes == 8
    instant = c.instantane()
    assert instant["appels_llm"] >= 8 + 1 + len(r.paires)
    assert instant["reparations_json"] == 1
    assert instant["tokens_entree"] > 0 and instant["tokens_sortie"] > 0
    assert instant["appels_embeddings"] == 0


def test_deux_proprietes_deux_synthetiseurs():
    r, c, _ = _generer(ChatSimule(pannes_ner=0), taille=6, distribution={"entites": 1, "mots_cles": 1})
    assert r.etat == "termine", r.erreur
    assert {p.synthetiseur for p in r.paires} == {"paire_simple_entites", "paire_simple_mots_cles"}
    assert all(p.chunk_ids for p in r.paires)


def test_une_paire_illisible_est_comptee_pas_masquee():
    chat = ChatSimule(pannes_ner=0, question_impossible="Gironde")
    r, _, _ = _generer(chat, taille=8)
    assert r.etat == "termine"
    assert all("Gironde" not in p.question for p in r.paires)
    assert r.paires_echouees + len(r.paires) <= 8


def test_sans_persona_erreur_sans_appel():
    chat = ChatSimule()
    r, c, _ = _generer(chat, personas=[])
    assert r.etat == "erreur" and "persona" in r.erreur
    assert c.instantane()["appels_llm"] == 0


def test_sans_passage_erreur():
    r, _, _ = _generer(ChatSimule(), morceaux=[])
    assert r.etat == "erreur" and "passage" in r.erreur


def test_modele_injoignable_message_sans_texte_de_passage():
    class Panne(ChatSimule):
        def _generate(self, messages, stop=None, run_manager=None, **kw):
            import httpx

            raise httpx.ConnectError("refusé")

    import time

    debut = time.monotonic()
    r, c, _ = _generer(Panne())
    assert time.monotonic() - debut < 30, "une panne doit échouer vite, pas après dix réessais"
    assert r.etat == "erreur" and "ne répond pas" in r.erreur
    assert all(t[:30] not in (r.erreur or "") for t in TEXTES)
    assert c.instantane()["erreurs_llm"] >= 1


def test_repli_par_le_texte_quand_l_identifiant_manque():
    from ragas.dataset_schema import SingleTurnSample

    ms = _morceaux()
    s = SingleTurnSample(user_input="Q ?", reference="R", reference_contexts=[ms[2].texte], persona_name="A")
    paires, echecs = moteur.paires_depuis_resultats([s, float("nan")], ms, {})
    assert echecs == 1 and paires[0].chunk_ids == ["c2"]


def test_prompts_francais_charges_depuis_le_depot(tmp_path):
    """Ce que `save_prompts` écrit se recharge et s'applique (même mécanisme que les prompts versionnés)."""
    llm = modele.LLMCompte(ChatSimule(), modele.Compteurs())
    transforms, dist = moteur.construire(llm, {"entites": 1.0})
    for o in [*transforms, *(s for s, _ in dist)]:
        for p in o.get_prompts().values():
            p.language = "french"
        o.save_prompts(str(tmp_path))
    neufs, dist2 = moteur.construire(llm, {"entites": 1.0})
    assert moteur.charger_prompts([*neufs, *(s for s, _ in dist2)], tmp_path) == 2
    assert all(p.language == "french" for p in neufs[0].get_prompts().values())
