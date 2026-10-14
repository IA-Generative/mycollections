"""Le moteur : des passages et des personas en entrée, des paires question/réponse en sortie.

`generer()` est SYNCHRONE et s'appelle par `asyncio.to_thread` : ragas lance ses propres
`asyncio.run`, et patcherait la boucle du service (nest_asyncio) s'il en trouvait une.

On enchaîne soi-même les trois étapes de `TestsetGenerator.generate_with_chunks` (nœuds CHUNK,
`apply_transforms`, `generate`) pour avoir la main entre l'extraction et la génération : poser la
phase, et arrêter avec un message clair si aucun passage ne porte d'entité. `persona_list` est
toujours fourni : sans lui, ragas inventerait des personas à partir de résumés et d'embeddings que
nos transformations ne produisent pas.

Une paire échouée (le modèle n'a pas rendu un JSON lisible malgré les réessais) est comptée, jamais
masquée. `generer()` ne lève jamais : elle rend un résultat « erreur » motivé, sans texte de passage.
"""

from __future__ import annotations

import logging
import math
import time
import unicodedata
from pathlib import Path
from typing import Callable

from ragas.dataset_schema import SingleTurnSample
from ragas.run_config import RunConfig
from ragas.testset import TestsetGenerator
from ragas.testset.graph import KnowledgeGraph, Node, NodeType
from ragas.testset.persona import Persona, PersonaList
from ragas.testset.synthesizers.single_hop.specific import SingleHopSpecificQuerySynthesizer
from ragas.testset.transforms import apply_transforms
from ragas.testset.transforms.extractors.llm_based import KeyphrasesExtractor, NERExtractor

from app.generation.morceaux import Morceau, en_documents
from app.generation.resultats import PaireGeneree, PersonaDemande, ResultatGeneration, message_sur  # noqa: F401

logger = logging.getLogger("myrag.generation")

PROMPTS_DIR = Path(__file__).parent / "prompts"
LANGUE = "french"

#: Consigne ajoutée à chaque génération de paire, quels que soient les prompts chargés.
CONSIGNE = ("Rédigez la question et la réponse en français. La question est celle que poserait la "
            "personne décrite, dans sa situation ; la réponse s'appuie uniquement sur le passage fourni.")

#: Ce qu'on sait demander : la clé de la distribution → (propriété des nœuds, extracteur, nom du synthétiseur).
SYNTHESES = {
    "entites": ("entities", NERExtractor, "paire_simple_entites"),
    "mots_cles": ("keyphrases", KeyphrasesExtractor, "paire_simple_mots_cles"),
}


def _plier(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower().strip()


class SynthetiseurSimple(SingleHopSpecificQuerySynthesizer):
    """Le synthétiseur « une question, un passage » de ragas, avec deux ajouts :

    - la paire garde les identifiants de son passage (`reference_context_ids`, que ragas ne
      remplit pas) : lus dans les métadonnées du nœud, posées par `en_documents` ;
    - les noms de personas renvoyés par le modèle sont rapprochés des nôtres (casse, accents)
      au lieu de faire échouer tout le nœud sur un nom légèrement réécrit.
    """

    def __post_init__(self):
        super().__post_init__()
        self.produits: dict[int, str] = {}

    def prepare_combinations(self, node, terms, personas, persona_concepts):
        connus = {_plier(p.name): p.name for p in personas}
        rapproches: dict[str, list[str]] = {}
        for nom, concepts in (persona_concepts or {}).items():
            vrai = connus.get(_plier(nom))
            if vrai:
                rapproches.setdefault(vrai, []).extend(concepts or [])
        return super().prepare_combinations(node, terms, personas, rapproches)

    async def _generate_sample(self, scenario, callbacks):
        sample = await super()._generate_sample(scenario, callbacks)
        meta = scenario.nodes[0].properties.get("document_metadata") or {}
        if meta.get("chunk_id"):
            sample.reference_context_ids = [str(meta["chunk_id"])]
        self.produits[id(sample)] = self.name
        return sample


def construire_graphe(documents) -> KnowledgeGraph:
    """Le même graphe que `generate_with_chunks` : un nœud CHUNK par passage, métadonnées comprises."""
    return KnowledgeGraph(nodes=[
        Node(type=NodeType.CHUNK, properties={"page_content": d.page_content, "document_metadata": d.metadata})
        for d in documents if (d.page_content or "").strip()
    ])


def normaliser_distribution(distribution: dict[str, float] | None) -> dict[str, float]:
    poids = {k: float(v) for k, v in (distribution or {"entites": 1.0}).items() if k in SYNTHESES and float(v) > 0}
    if not poids:
        raise ValueError("Distribution vide : choisissez au moins « entites » ou « mots_cles ».")
    total = sum(poids.values())
    return {k: v / total for k, v in poids.items()}


def construire(llm, distribution: dict[str, float]) -> tuple[list, list[tuple]]:
    """(transformations, distribution ragas) : un extracteur et un synthétiseur par propriété."""
    transforms, dist = [], []
    for cle, poids in distribution.items():
        propriete, extracteur, nom = SYNTHESES[cle]
        transforms.append(extracteur(llm=llm))
        dist.append((SynthetiseurSimple(name=nom, llm=llm, property_name=propriete, llm_context=CONSIGNE), poids))
    return transforms, dist


def charger_prompts(objets: list, dossier: Path = PROMPTS_DIR, langue: str = LANGUE) -> int:
    """Charge les prompts versionnés (`{nom}_{prompt}_{langue}.json`) ; ceux qui manquent restent
    en anglais (la consigne garde les paires en français). Rend le nombre d'objets francisés."""
    francises = 0
    for objet in objets:
        try:
            objet.set_prompts(**objet.load_prompts(str(dossier), langue))
            francises += 1
        except Exception as e:  # noqa: BLE001 — un fichier absent n'empêche pas de générer
            logger.warning("prompts %s de %s non chargés (%s) : anglais", langue, getattr(objet, "name", objet), type(e).__name__)
    return francises


def paires_depuis_resultats(resultats: list, morceaux: list[Morceau], produits: dict[int, str]) -> tuple[list[PaireGeneree], int]:
    """(paires, nombre d'échecs). Le passage se retrouve par son identifiant, à défaut par son texte."""
    par_id = {m.chunk_id: m for m in morceaux}
    par_texte = {m.texte: m for m in morceaux}
    paires, echecs = [], 0
    for r in resultats:
        if not isinstance(r, SingleTurnSample) or not (r.user_input or "").strip() or not (r.reference or "").strip():
            echecs += 1
            continue
        trouves = [par_id[str(i)] for i in (r.reference_context_ids or []) if str(i) in par_id]
        if not trouves:
            trouves = [par_texte[t] for t in (r.reference_contexts or []) if t in par_texte]
        contextes = [{**m.identifiants(), "texte": m.texte} for m in trouves]
        paires.append(PaireGeneree(
            question=r.user_input.strip(), reponse=r.reference.strip(), contextes=contextes,
            persona_nom=r.persona_name or "", synthetiseur=produits.get(id(r), ""),
            style=r.query_style or "", longueur=r.query_length or "",
        ))
    return paires, echecs


def generer(morceaux: list[Morceau], personas: list[PersonaDemande], taille: int, llm, embeddings, *,
            distribution: dict[str, float] | None = None, run_config: RunConfig | None = None,
            progression: Callable[[str], None] | None = None, dossier_prompts: Path = PROMPTS_DIR) -> ResultatGeneration:
    debut = time.monotonic()
    phase = progression or (lambda _p: None)
    resultat = ResultatGeneration(etat="erreur")
    try:
        if not personas:
            raise ValueError("Choisissez au moins un persona.")
        documents = en_documents(morceaux)
        kg = construire_graphe(documents)
        resultat.morceaux_envoyes = len(kg.nodes)
        if not kg.nodes:
            raise ValueError("Aucun passage lisible dans cette collection.")
        poids = normaliser_distribution(distribution)
        transforms, dist = construire(llm, poids)
        charger_prompts([*transforms, *(s for s, _ in dist)], dossier_prompts)
        run_config = run_config or RunConfig()
        # ragas ne pose le RunConfig sur le modèle qu'au moment de `generate()` : pendant
        # l'extraction, le modèle garderait le défaut (10 réessais, jusqu'à 60 s d'attente chacun)
        # et une passerelle en panne immobiliserait le run une dizaine de minutes en silence.
        llm.set_run_config(run_config)
        if embeddings is not None:
            embeddings.set_run_config(run_config)

        phase("extraction")
        apply_transforms(kg, transforms, run_config=run_config)
        proprietes = {SYNTHESES[c][0] for c in poids}
        resultat.noeuds_avec_proprietes = sum(1 for n in kg.nodes if any(n.properties.get(p) for p in proprietes))
        if resultat.noeuds_avec_proprietes == 0:
            raise ValueError("Le modèle n'a extrait aucune entité ni mot-clé des passages : rien à questionner.")

        phase("generation")
        generateur = TestsetGenerator(
            llm=llm, embedding_model=embeddings, knowledge_graph=kg,
            persona_list=[Persona(name=p.nom, role_description=p.description_role) for p in personas],
        )
        executeur = generateur.generate(
            testset_size=taille, query_distribution=dist, num_personas=len(personas),
            run_config=run_config, raise_exceptions=False, return_executor=True,
        )
        bruts = executeur.results()
        produits = {k: v for s, _ in dist for k, v in s.produits.items()}
        resultat.paires, resultat.paires_echouees = paires_depuis_resultats(bruts, morceaux, produits)
        resultat.etat = "termine"
    except TypeError as e:
        # ragas itère sur les scénarios d'un synthétiseur : s'ils ont échoué (raise_exceptions=False),
        # il reçoit NaN au lieu d'une liste. C'est un échec de la phase scénarios, dit comme tel.
        if "float" in str(e) and "iterable" in str(e):
            c = getattr(getattr(llm, "compteurs", None), "instantane", dict)()
            if c.get("refus_debit"):
                resultat.erreur = ("La passerelle MirAI a refusé des appels faute de quota (429) pendant la préparation "
                                   "des questions. Réessayez plus tard, ou baissez MYCOLLECTIONS_GENERATION_APPELS_PAR_MINUTE.")
            elif c.get("erreurs_llm"):
                resultat.erreur = (f"Le modèle de langage a échoué {c['erreurs_llm']} fois pendant la préparation des "
                                   "questions : aucun scénario n'a pu être préparé. Réessayez dans un instant.")
            else:
                resultat.erreur = ("Aucun scénario n'a pu être préparé : le modèle n'a pas su associer les personas "
                                   "aux thèmes des passages. Vérifiez les descriptions des personas.")
        else:
            resultat.erreur = message_sur(e)
        logger.warning("génération en échec : %s", type(e).__name__)
    except Exception as e:  # noqa: BLE001 — le fil rend toujours un résultat
        resultat.erreur = message_sur(e)
        logger.warning("génération en échec : %s", type(e).__name__)
    resultat.duree_s = round(time.monotonic() - debut, 1)
    if resultat.etat == "termine" and not resultat.paires:
        resultat.etat, resultat.erreur = "erreur", "Aucune paire n'a pu être produite (toutes ont échoué)."
    return resultat


def run_config_par_defaut(parallelisme: int, delai_s: int, graine: int = 42) -> RunConfig:
    return RunConfig(max_workers=max(1, parallelisme), timeout=delai_s, max_retries=3, max_wait=20, seed=graine)


def _estimer(taille: int, morceaux: int, n_dist: int) -> int:
    """Ordre de grandeur des appels : une extraction par passage et par propriété, un appariement
    par nœud consulté, une génération par paire."""
    return morceaux * n_dist + min(morceaux, taille) + taille + math.ceil(0.1 * taille)
