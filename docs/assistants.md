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

À écrire par le lot B.


## Travailler sans le harnais

```bash
cd myrag
MYCOLLECTIONS_DOUBLURE_ASSISTANTS=true \
MYCOLLECTIONS_CAPACITES_SURCHARGE='{"assistants": true}' \
AUTH_ENABLED=false MYRAG_PSEUDO_SEL=dev-sel uv run uvicorn app.main:app --port 8200
```

`POST /api/v1/assistants/{id}/plan` et `/executer` rendent alors le plan et le résultat de
`myrag/app/doublure/assistants/` (conformes au contrat, vérifiés par les tests). Jamais en production.
