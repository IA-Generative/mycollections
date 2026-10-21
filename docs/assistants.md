# Les assistants de recherche

Un assistant interroge plusieurs sources — des collections et des connecteurs — selon des
consignes, et sert d'abord les réponses fiables. Décision : [ADR-0003](adr/ADR-0003-assistants-de-recherche.md).
Contrat : `myrag/app/harnais/contrat.py`. Drapeau : `assistants` (capacites.json).


## La fiche (lot 0)

`GET /api/assistants`, `GET|PUT /api/assistants/{id}`, `POST /api/assistants/{id}/publier`,
`GET /api/assistants/{id}/versions`. Publier fige une version (texte canonique + sha256) ; une
collection publiée a son assistant miroir à une source.


## Le harnais (lot A)

`myrag/app/harnais/` (sans FastAPI ni base, sauf `journal.py`) : un planificateur produit un plan, `execution.py`
l'exécute (étapes en parallèle, relais `avec`, source en panne ignorée et comptée), `fusion.py` fusionne (RRF, k = 60,
poids par étape, quota des sources `toujours`), `perimetre.py` ne garde que ce que la personne lit. Planificateurs :
`toutes_les_sources` (recherche `GET /api/v1/search?assistant=<id>`) et `regles` (consigne reconnue par ressemblance au
« quand » et aux exemples ; sinon régimes des sources, jamais `sur_consigne`). Routes `POST /api/v1/assistants/{id}/plan`
et `/executer` : la version enregistrée pour qui peut modifier, la publiée pour les autres. Le journal (`plans_journal`)
ne garde aucun texte. Avec `MYCOLLECTIONS_DOUBLURE_ASSISTANTS`, la doublure répond (en-tête `X-Mycollections-Doublure: 1`).

## Un référentiel comme source (lot A6)

Une source de type `connecteur` n'est pas une collection : elle interroge un service HTTP interne. Le premier est le
référentiel d'éligibilité (`harnais/connecteurs/eligibilite.py`, type `eligibilite` : titres de séjour → situations →
pièces). Il se déclare par `MYCOLLECTIONS_CONNECTEURS` (tableau JSON `{id, type, url, titre, description, tables, exemples}`) ;
vide, rien ne change. Un connecteur déclaré est lisible de toute personne qui passe la garde de l'application ; non
déclaré, il n'est jamais lu (le périmètre et le filet `restreindre_passages` le vérifient). Le service ne connaît personne :
le connecteur n'envoie ni `Authorization` ni identifiant. Il tire de la question quelques mots significatifs (trois appels
de `/tables/{t}/search` au plus par table), classe les lignes par mots retrouvés ; une étape `avec` (relais `reference`)
cherche la référence courte du meilleur passage amont. Panne, délai (`MYCOLLECTIONS_RECHERCHE_DELAI_S`) ou JSON illisible :
liste vide, jamais d'exception. `/query` n'est pas utilisé. L'écran « Ajouter une source » les propose (`GET /api/assistants/connecteurs`,
sans l'adresse du service) avec l'étiquette « Référentiel » ; assembler demande de gérer les seules **collections**.
En production, Mes collections doit pouvoir joindre le service (règle réseau à poser côté infrastructure).


## Le banc (lot A)

`scripts/banc.py` joue un jeu figé (`tests/harnais/fixtures/banc/`) sans HTTP ni réseau et compare les planificateurs :
rappel du passage témoin (`rappel@1`, `rappel@5`), part des sources contactées, score, incidents de droits (un passage
d'une source que la personne ne lit pas), durée p95 (non bloquante). Le juge « doublure » est déterministe (conforme si le
témoin attendu est rendu, partiel si c'est celui d'une autre source) ; le juge « réel » n'est pas branché. Seuils : `seuils.json`.

    cd myrag && uv run python -m scripts.banc tests/harnais/fixtures/banc/sejour-des-etrangers.json --juge doublure --planificateur regles --rapport json
    cd myrag && uv run pytest tests -q -m banc


## L'interface (lot B)

Sous le drapeau `assistants`, l'entrée « Assistants » du menu mène à `/assistants` (liste,
création). Un assistant a ses rubriques (`frontend/pages/assistants/[id]/`) :

- **Sources** et **Publication** (B1) : quelles collections, quand les interroger, dans quel
  ordre ; canaux, versions.
- **Consignes** (B2) : quand (une phrase ou « pour toute question »), exemples, étapes de
  recherche, consigne de rédaction ; enregistrées par `PUT /api/assistants/{id}` (la fiche
  entière). « Tester » appelle `POST /api/v1/assistants/{id}/executer`.
- **Bac à sable** (B4) : les briques du bac à sable d'une collection (`components/playground/`)
  pointées sur `executer` ; sous chaque réponse, « Comment l'assistant a cherché » (consigne
  retenue, étapes, sources non interrogées, sources écartées comptées sans être nommées).

Les calculs d'écran sont des fonctions pures de `frontend/utils/assistants.ts` (`validerConsigne`,
`ordonnerEtapes`, `traceDuPlan`…), testées dans `frontend/tests/unit/assistants*.test.ts`.


## Travailler sans le harnais

Le moteur répond sur la bêta depuis la fusion des lots A1 et A3. La doublure reste utile pour
montrer les écrans sans OpenRAG, en local ou sur une prévisualisation :

```bash
cd myrag
MYCOLLECTIONS_DOUBLURE_ASSISTANTS=true \
MYCOLLECTIONS_CAPACITES_SURCHARGE='{"assistants": true}' \
AUTH_ENABLED=false MYRAG_PSEUDO_SEL=dev-sel uv run uvicorn app.main:app --port 8200
```

`POST /api/v1/assistants/{id}/plan` et `/executer` rendent alors le plan et le résultat de
`myrag/app/doublure/assistants/`, avec l'en-tête `X-Mycollections-Doublure: 1` ; l'interface
l'annonce par un encadré « Réponse d'exemple ». Jamais sur la bêta ni en production.

Les deux routes du moteur sont limitées par personne : `MYCOLLECTIONS_ASSISTANTS_PAR_MINUTE`
(30 par défaut, par processus) ; au-delà, 429 avec `Retry-After`. Un moteur entièrement en panne
rend 503 avec `Retry-After: 10`.
