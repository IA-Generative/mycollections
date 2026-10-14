# ADR-0002 — Générer des paires question / réponse par persona avec ragas

- **Statut** : Proposed (branche d'expérimentation `exp/ragas`)
- **Date** : 2026-10-14
- **Décideurs** : PO bêta
- **Sujet** : produire, à partir des documents d'une collection, des paires question / réponse de
  référence du point de vue de personas, pour évaluer les réponses de l'assistant.

## Contexte

Le bac à sable sait faire rédiger quelques questions par le RAG lui-même, sans réponse de
référence fiable ni lien vers les passages. Il faut un jeu d'évaluation relu, rattaché aux
passages, et dont le coût se mesure. Quatre faits du code ont pesé :

1. Mes collections n'a **aucun client de modèle de langage** : tout passe par OpenRAG, qui
   n'expose pas d'embeddings. Le « même chemin d'accès » supposé par le brief n'existait pas.
2. Il n'y a **pas de table de passages** : un passage est un fichier OpenRAG, lisible par
   `/partition/<p>/chunks` (ou `file_detail` + `extract`).
3. Les traitements longs sont des **tâches asyncio** avec l'état en base ; pas de file, pas de broker.
4. ragas 0.4.3 lance ses propres `asyncio.run` (avec `nest_asyncio` s'il trouve une boucle).

## Options considérées

| Option | Pour | Contre |
|---|---|---|
| A. Passer par le chemin direct d'OpenRAG (`model` vide), sans embeddings | Aucune configuration nouvelle | Pas d'embeddings : ni personas automatiques ni multi-hop, jamais |
| **B. Configuration dédiée vers la passerelle MirAI** | Toutes les fonctions de ragas à terme ; même passerelle qu'OpenRAG | Une configuration et un secret de plus |
| C. Celery pour exécuter les runs | Annulation franche, isolation mémoire | Un broker et un déploiement de plus pour quelques runs par jour |

## Décision

- **B**, avec ragas en **extra optionnel** (`ragas==0.4.3`, `langchain-community<0.4.2`), flux
  pré-découpé, single-hop, personas saisis.
- Exécution : tâche asyncio + **fil** (`asyncio.to_thread`) ; un run à la fois par processus, un
  run actif par collection. Le découpage `morceaux` / `moteur` / `execution` permet de passer à un
  sous-processus (annulation, isolation) sans toucher au reste.
- Enveloppe LangChain (`ChatOpenAI` en appels synchrones dans des fils), qui compte appels et jetons
  à chaque appel, et limite le débit tous fils confondus.
- Prompts traduits une fois, relus, versionnés.

## Conséquences

- L'image du backend passe de 256 Mo à 796 Mo ; environ 200 Mo de plus pendant un run.
- La passerelle compte son quota **par jeton** : il faut un jeton propre à Mes collections (le
  jeton d'OpenRAG est limité à 60 appels par minute pour tout l'assistant).
- Les paires gardent le texte de leur passage : l'identifiant OpenRAG change à la réindexation.

## Points ouverts

- Jeton et quota dédiés auprès de l'équipe MirAI.
- Modèle retenu (`chat` : rapide et JSON fiable à l'essai ; `chat-pro` raisonne, dix fois plus
  de jetons de sortie).
- Personas automatiques et multi-hop, après mesure du coût sur la bêta.
