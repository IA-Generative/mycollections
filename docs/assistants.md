# Les assistants de recherche

Un assistant interroge plusieurs sources — des collections et des connecteurs — selon des
consignes, et sert d'abord les réponses fiables. Décision : [ADR-0003](adr/ADR-0003-assistants-de-recherche.md).
Contrat : `myrag/app/harnais/contrat.py`. Drapeau : `assistants` (capacites.json).


## La fiche (lot 0)

`GET /api/assistants`, `GET|PUT /api/assistants/{id}`, `POST /api/assistants/{id}/publier`,
`GET /api/assistants/{id}/versions`. Publier fige une version (texte canonique + sha256) ; une
collection publiée a son assistant miroir à une source.


## Le harnais (lot A)

À écrire par le lot A.


## Le banc (lot A)

À écrire par le lot A.


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

```bash
cd myrag
MYCOLLECTIONS_DOUBLURE_ASSISTANTS=true \
MYCOLLECTIONS_CAPACITES_SURCHARGE='{"assistants": true}' \
AUTH_ENABLED=false MYRAG_PSEUDO_SEL=dev-sel uv run uvicorn app.main:app --port 8200
```

`POST /api/v1/assistants/{id}/plan` et `/executer` rendent alors le plan et le résultat de
`myrag/app/doublure/assistants/` (conformes au contrat, vérifiés par les tests). Jamais en production.
