# Les clients des assistants

Le socle (Open WebUI) et la fenêtre de recherche à insérer dans une application interrogent le
même harnais, avec le jeton de la personne. Décision : [ADR-0003](adr/ADR-0003-assistants-de-recherche.md).

À écrire par le lot C.

## Sites déclarés : la bulle « + IA » de l'extension du navigateur

L'extension IAssistant-Direct propose une bulle « + IA » sur les pages que les gestionnaires ont
déclarées pertinentes pour une collection ou un assistant (rubrique Publication de l'un et de
l'autre). L'extension télécharge la liste et compare elle-même l'adresse de la page : aucune
adresse visitée n'est envoyée au service.

**Déclarer** : `GET|PUT /api/collections/{name}/sites` et `GET|PUT /api/assistants/{id}/sites`,
corps `{"motifs": ["https://www.fake-domain.name/guides/*"]}`. Lecture par qui lit la fiche,
écriture par qui la gère ; le `PUT` remplace la liste. Motif refusé : 422
`{"reason": "motif", "message": …}`. Vingt motifs au plus par fiche.

**Règle des motifs** (celle des *match patterns* d'extension, restreinte ; `app/services/sites.py`) :
`https://` seulement ; hôte explicite, éventuellement précédé de `*.` (au moins deux niveaux :
`*.fake-domain.name`, jamais `*` ni `*.fr`) ; ni port ni identifiant ; un chemin qui commence par
`/` et peut contenir `*`. Le chemin est comparé avec la query de l'adresse ; le fragment (`#…`)
ne l'est jamais. L'hôte est mis en minuscules.

**Lire, pour l'extension** : `GET /api/v1/sites`, jeton de la personne, audience vérifiée comme
pour la recherche v1 (403 `audience_mismatch` sinon).

```json
{ "ttl_s": 3600, "anonyme": false,
  "sites": [ { "motif": "https://www.fake-domain.name/guides/*",
               "cibles": [ { "type": "assistant", "id": "exemple", "titre": "Assistant d'exemple" },
                           { "type": "collection", "id": "guide-exemple", "titre": "Guide d'exemple" } ] } ] }
```

Seules les cibles que la personne lit sont rendues : une collection illisible ou archivée, un
assistant éteint (drapeau `assistants`), jamais publié et qu'elle ne gère pas, sont absents.

**Sans jeton** : 401. Pour le débogage seulement, `MYCOLLECTIONS_SITES_ANONYMES=true` rend les
sites des collections ouvertes à tous (`scope` public), sans aucun assistant, avec
`"anonyme": true`. Coupé par défaut : une liste anonyme dit quels sites intéressent quelles
collections. Les questions (`/api/v1/search`, `/api/v1/assistants/{id}/executer`) demandent
toujours un jeton.

**Questions** : un assistant par `POST /api/v1/assistants/{id}/executer`, des collections par
`GET /api/v1/search?q=…&scope=a,b`. Liens cités signés, valables 12 h. 429 porte `Retry-After`
(recherche v1).

