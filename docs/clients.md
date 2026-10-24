# Les clients des assistants

Le socle (Open WebUI) et la fenêtre de recherche à insérer dans une application interrogent le
même harnais, avec le jeton de la personne. Décision : [ADR-0003](adr/ADR-0003-assistants-de-recherche.md).

À écrire par le lot C.

## Sites déclarés : la bulle « + IA » de MirAI Assistant pour navigateur

L'extension MirAI Assistant pour navigateur propose une bulle « + IA » sur les pages que les gestionnaires ont
déclarées pertinentes pour une collection ou un assistant (rubrique Publication de l'un et de
l'autre). L'extension télécharge la liste et compare elle-même l'adresse de la page : aucune
adresse visitée n'est envoyée au service.

**L'installer** : l'extension s'installe depuis la page du device management. Quand
`MYCOLLECTIONS_NAVIGATEUR_INSTALLATION_URL` donne son adresse (https seulement), la rubrique « Dans
le navigateur » propose le lien « Installer MirAI Assistant pour navigateur » ; vide, pas de lien.

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
`GET /api/v1/search?q=…&scope=a,b`. Liens cités signés, valables 12 h. Avec `?assistant=`, un résultat peut venir d'un référentiel
(source `connecteur`, `docs/assistants.md`) : `context.collection` porte l'identifiant et le titre du connecteur,
`context.right` vaut `reader`, `url` et `hits[].url` sont `null` (aucun lien à signer). 429 porte `Retry-After`
(recherche v1).



## Recherche : les invitations à mettre à jour (`notices`)

`GET /api/v1/search` peut porter, en plus du contrat de recherche, une clé **`notices`** (absente
s'il n'y en a pas). Aujourd'hui, une seule sorte : l'index d'une collection Résana ancien ou
incomplet, pour la personne qui peut le mettre à jour (docs/resana.md).

```json
"notices": [
  {
    "collection": "notes-fictives",
    "titre": "Notes fictives",
    "code": "resana_ancien",
    "message": "L'index Résana de « Notes fictives » semble ancien (dernière lecture il y a 12 jours). Souhaitez-vous le mettre à jour ?",
    "action": {"libelle": "Mettre à jour", "url": "https://mescollections.fake-domain.name/c/notes-fictives/upload?synchroniser=1"},
    "jours": 12
  }
]
```

- `collection` est l'identifiant de la collection, le même que l'`id` d'une cible collection de
  `/api/v1/sites` ; `titre` est son titre, déjà repris dans `message`.
- `code` vaut `resana_ancien` (index lu il y a plus de N jours ; `jours` le précise) ou
  `resana_incomplet` (dernière passe arrêtée en route ou en échec). Un code inconnu s'affiche par
  son `message`.
- `action.url` est une **page du front**, sur l'origine publique de Mes collections
  (`MYCOLLECTIONS_PUBLIC_URL`), pas sur celle des liens signés de la recherche. Un client vérifie
  que son origine (`new URL(url).origin`, comparaison exacte) est celle de Mes collections qu'il
  connaît, et l'ignore sinon. Front et API partagent aujourd'hui la même origine ; un déploiement
  qui les séparerait devra le dire aux clients.

Un client l'affiche sous les résultats, avec un lien qui ouvre `action.url` dans un nouvel onglet.
Il n'appelle rien lui-même : la mise à jour se lance d'un clic sur la page de la collection.

## Serveur MCP

Un client MCP (un agent conversationnel) cherche dans les assistants de recherche avec les droits de la personne,
sans modèle de langage côté Mes collections : le client choisit l'assistant, lit les passages et rédige lui-même.

- **Adresse** : `POST /mcp`, transport Streamable HTTP, sans état (une requête, une session).
- **Jeton** : le jeton Bearer de la personne (`Authorization: Bearer …`). Mêmes contrôles que la recherche v1 :
  signature, émetteur, groupe exigé, et **audience** (`MYCOLLECTIONS_RECHERCHE_AUDIENCE`). Sans jeton : 401 ; audience
  d'un autre service : 403. L'identité relayée aux outils est celle du jeton, jamais un argument.
- **Drapeau** : `assistants` à faux dans capacites.json ⇒ 404. Sans le paquet `mcp` (extra `mcp`), `/mcp` n'est pas monté.
- **Débit** : le plafond par personne de `plan` et `executer` (`MYCOLLECTIONS_ASSISTANTS_PAR_MINUTE`), partagé.

| Outil | Rôle |
|-------|------|
| `lister_sources()` | Les assistants publiés que la personne lit, et leurs collections lisibles (id, titre, description). |
| `proposer_sources(question, assistant)` | Le plan (sources retenues, poids, consigne) sans lancer la recherche. |
| `rechercher(question, assistant, sources?)` | Les passages (titre, texte, lien signé, collection) et le plan. `sources` impose les collections ; une réponse de référence fiable est rendue telle quelle dans `reponse`. |

Exemple de configuration d'un client (adresse d'exemple) :

```json
{
  "mcpServers": {
    "mes-collections": {
      "type": "http",
      "url": "https://mescollections.fake-domain.name/mcp",
      "headers": { "Authorization": "Bearer <jeton-de-la-personne>" }
    }
  }
}
```

La route compatible OpenAI (`routers/openai_compat.py`) n'est pas concernée : elle attend une décision produit sur la rédaction des réponses.
