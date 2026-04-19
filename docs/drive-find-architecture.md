# Architecture — Drive + Find + MyRAG

Référence à froid des 3 services "fichiers/recherche" de l'écosystème Mirai, de leurs responsabilités et de la façon dont ils se parlent.

## Les trois services

| Service | Rôle | Stack | Domaine prod |
|---------|------|-------|-------------|
| **Drive** (Suite Numérique) | **Source de vérité des fichiers** : stockage, métadonnées, ACL, versioning, WOPI office | Django + PostgreSQL + MinIO/S3 + Celery + Redis | `mesfichiers.fake-domain.name` |
| **Find** | **Recherche fédérée** plein-texte + vectoriel sur plusieurs services, filtrage ACL à la query | Django + OpenSearch + `lasuite.oidc_resource_server` | (à déployer) |
| **MyRAG / Mes collections** | **RAG** : chunking intelligent + indexation OpenRAG + admin des collections + intégration OWUI | FastAPI + SQLAlchemy + Nuxt DSFR | `mycollections.fake-domain.name` |

Tous partagent le même realm Keycloak `openwebui` et le même cluster Kapsule `k8s-par-brave-bassi` namespace `miraiku`.

---

## Responsabilités (qui fait quoi)

**Drive** est le **seul endroit** où les fichiers vivent vraiment. Il maintient :
- les bytes (MinIO/S3),
- les permissions (modèle `ItemAccess` : user ou groupe, rôle viewer/editor/owner),
- la hiérarchie (dossiers récursifs),
- les notifications de changement (signals Django `post_save` sur `Item` + `ItemAccess`).

**Find** est un **index de recherche fédérée**. Il ne stocke pas de fichiers, juste des documents OpenSearch avec :
- les champs métadonnées (title, mimetype, path, size, created_at/updated_at),
- le **contenu plein-texte extrait** (via Tika côté Drive),
- une **photo des ACL** (`users: [sub…], groups: [id…], reach`, `is_active`),
- un index OpenSearch **par service** (`find-<token>`) → isolation,
- une **fédération** optionnelle : chaque `Service` a un M2M `services` qui autorise la recherche cross-index.

**MyRAG** est le **RAG pipeline** :
- découpe les fichiers en chunks intelligents,
- envoie les chunks à OpenRAG (Milvus + embeddings Scaleway),
- stocke un pointeur sur le fichier source (pour réindexation),
- gère la publication des collections dans Open WebUI.

## Qui produit quoi ?

- **Drive produit** : les bytes + les ACL + les signaux de changement.
- **Find consomme** Drive (via Search Indexer push) pour exposer une recherche plein-texte cross-app.
- **MyRAG consomme** Drive (via `/external_api/v1.0/`) pour chunker et indexer dans OpenRAG. Il **ne consomme pas Find** — OpenRAG est un index vectoriel distinct, pas un remplacement d'OpenSearch.

```
                            ┌───────────────────────┐
                            │      Drive            │
                            │  (source of truth)    │
                            │  fichiers + ACL       │
                            └─────────┬─────────────┘
                                      │
                    ┌─────────────────┴──────────────────┐
                    │ 1. Search Indexer push             │ 2. /external_api pull
                    │ (post_save → POST /documents/index)│    (MyRAG impersonation)
                    ▼                                    ▼
          ┌──────────────────┐                   ┌─────────────────┐
          │      Find        │                   │     MyRAG       │
          │  OpenSearch      │                   │   FastAPI       │
          │  fédération      │                   │   chunker       │
          │  recherche       │                   │   OpenRAG       │
          │  plein-texte/vec │                   │   partition     │
          └──────────────────┘                   └─────────────────┘
                    ▲                                    ▲
                    │                                    │
                    │                        POST RAG    │
                    │                                    │
       ┌────────────┴──────────┐              ┌──────────┴────────┐
       │  User navigateur      │              │  Open WebUI       │
       │  recherche unifiée    │              │  (chat)           │
       └───────────────────────┘              └───────────────────┘
```

---

## Flux 1 — Drive → Find (indexation plein-texte fédérée)

### Déclenchement
Côté Drive, [`core/signals.py`](../../drive/src/backend/core/signals.py) écoute `post_save` sur `Item` et `ItemAccess`. Chaque save entre dans une **Celery task débouncée** ([`core/tasks/search.py:52-64`](../../drive/src/backend/core/tasks/search.py#L52)) : pendant `SEARCH_INDEXER_COUNTDOWN` (default 1 s) les saves s'accumulent, puis **une seule** requête HTTP est émise à Find avec le batch.

### Requête
`POST https://<find>/api/v1.0/documents/index/` avec header `Authorization: Bearer <SEARCH_INDEXER_SECRET>` — ce secret est le `token` de 50 chars du `Service` Drive enregistré dans Find (modèle `core.Service`).

Payload (liste d'items) :
```json
[
  {
    "id": "uuid-drive-item",
    "title": "note interne.docx",
    "mimetype": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "description": "...",
    "content": "<texte plein extrait via Tika>",
    "path": "/dossier/sous-dossier/note interne.docx",
    "size": 34567,
    "users": ["sub-user-1", "sub-user-2"],
    "groups": ["group-uuid-A", "group-uuid-B"],
    "reach": "restricted",
    "created_at": "2026-04-19T12:00:00Z",
    "updated_at": "2026-04-19T12:34:00Z",
    "is_active": true
  }
]
```

### Côté Find
[`IndexDocumentView`](../../find/src/backend/core/views.py) authentifie via `ServiceTokenAuthentication` → retrouve le `Service` (ex. "drive") → écrit le doc dans l'index OpenSearch **propre à ce service** (`find-<token>`). Chaque service a son bac à sable, pas de collision.

**Variables Drive côté Helm values** pour activer ce push :
```
SEARCH_INDEXER_CLASS=core.services.search_indexers.SearchIndexer
SEARCH_INDEXER_URL=https://<find-host>/api/v1.0/documents/index/
SEARCH_INDEXER_SECRET=<token du Service 'drive' dans Find>
SEARCH_INDEXER_COUNTDOWN=1            # debounce (s)
SEARCH_INDEXER_BATCH_SIZE=100000
SEARCH_INDEXER_ALLOWED_MIMETYPES=text/,application/pdf,application/vnd.openxmlformats-officedocument.*
SEARCH_INDEXER_CONTENT_MAX_SIZE=2097152
```

---

## Flux 2 — User → Find (recherche filtrée par ACL)

### Requête
`GET https://<find>/api/v1.0/documents/search/?q=foo` avec `Authorization: Bearer <token OIDC du user>` (même token que celui utilisé pour se connecter sur Drive ou MyRAG).

### Extraction des droits
[`SearchDocumentView`](../../find/src/backend/core/views.py) utilise `lasuite.oidc_resource_server` pour valider le token et en extraire :
- `user_sub` = claim `sub` du JWT
- `groups` = claim `groups` du JWT (nécessite d'activer le mapper groups dans Keycloak)

### Filtrage OpenSearch ([services/search.py `get_filter`](../../find/src/backend/core/services/search.py))
Un doc match si au moins une des conditions suivantes :

1. `reach` ≠ `restricted` ET le user l'a "visité" récemment (cache cookie-like) ;
2. `users` contient `user_sub` ;
3. `groups` contient au moins un des groupes du user ;

et toujours `is_active: true`.

La query parcourt les index des services autorisés (M2M `Service.services`). Les docs non-autorisés ne remontent jamais, même si `q` matche.

**Conséquence** : les ACL sont **snapshotées à l'indexation**. Quand Drive change un accès, le signal `post_save` sur `ItemAccess` déclenche une ré-indexation (1 s de debounce) → Find se met à jour quasi temps réel.

---

## Flux 3 — MyRAG → Drive (picker + indexation RAG)

MyRAG ne passe pas par Find — OpenRAG est un index vectoriel dédié au chat RAG, pas un plein-texte. MyRAG interroge Drive directement.

### Picker (étape 3 du wizard Drive)
`GET /api/v1.0/external_api/items/?parent_id=<id>` avec `Authorization: Bearer <token OIDC du user connecté sur MyRAG>`. **Impersonation** : MyRAG relaie le token de l'user courant, Drive voit l'appel comme fait par cet user → ne retourne que ses propres dossiers / ceux qu'on lui a partagés.

### Indexation (POST `/api/sources/drive/add`)
Suite de l'étape précédente. MyRAG :
1. Télécharge **synchrone** tous les fichiers du dossier avec le token user (pendant que le token est valide, durée bumpée à 15 min sur le client `myrag-front`).
2. Lance en async le chunking + upload vers OpenRAG à partir des bytes déjà en mémoire.
3. Écrit `collection.source_type="drive"` + `source_config_json` avec le folder_id + last_sync_at.

**Pourquoi pas par Find** ? Parce que Find n'expose pas les bytes — il indexe le `content` plain-text extrait, mais pas le fichier pour rechunker. MyRAG a besoin des bytes pour découper en chunks de 512 chars overlap 50 (ou autre stratégie) avec des boundaries sémantiques. Donc MyRAG doit taper directement sur Drive pour l'indexation RAG.

---

## Relation ACL entre les 3

| Niveau | Mécanisme | Limite |
|--------|-----------|--------|
| Drive | `ItemAccess` + `Group` | Vérité, temps réel |
| Find | Snapshot `users + groups + reach` par doc dans OpenSearch | Lag = 1 s (debounce) |
| MyRAG | Pas d'ACL granulaire côté fichier : héritée de la collection (`scope`) + de la publication OWUI (`visibility_groups`) | Grain grossier — collection entière publique/privée |

### Points d'attention

- **Cohérence des identifiants groupe** : Drive stocke les groupes par UUID interne, Keycloak les émet avec un path (`/myrag/ceseda`). Il faut un mapping (attribut Keycloak / sync) pour que le filtre Find fonctionne. Idem côté MyRAG pour `visibility_groups`.
- **Le sub OIDC** est stable et sert de clé primaire inter-services. Pas de mapping à faire.
- **Le bot MyRAG** (`mycollections-drive@bot.local`, sub = service account) est une identité **distincte** des users. Son `Service` dans Find (si on en créait un) aurait un index séparé. Pour le picker Drive on préfère l'impersonation user-token (point 3 ci-dessus).

---

## Qu'est-ce que Find apporterait à MyRAG (V2+) ?

Aujourd'hui, MyRAG maintient **son propre pipeline** Drive → chunks → OpenRAG. Find n'intervient pas. Trois scénarios où Find deviendrait utile :

1. **Recherche unifiée UX** : une barre de recherche qui couvre Drive + MyRAG + autres apps — Find fédère, MyRAG s'enregistre comme Service et pousse ses chunks MyRAG (ou juste des pointeurs) dans Find.
2. **Bypass de Drive pour les notifications de changement** : au lieu que MyRAG fasse un webhook Drive dédié, il s'abonne à Find (qui reçoit déjà les signaux de Drive). Pas évident — Find n'expose pas de notification sortante, il faudrait l'ajouter.
3. **Partage de contenu cross-service** : si MyRAG expose ses chunks dans Find, un user peut chercher un extrait MyRAG en même temps qu'un doc Drive. Nouveau produit, pas une simplification.

**Pour la V1, Find n'est pas dans le chemin critique.** Priorité : faire fonctionner Drive → MyRAG → OpenRAG → OWUI. Find pourra se brancher plus tard sans re-refactoriser cette chaîne.

---

## Déploiement cible

Trois services, trois déploiements dans `miraiku` :

```
miraiku/
  ├── drive-backend + celery + frontend (chart: drive-0.16.0, Helm)
  ├── find-backend + opensearch (chart: find-X.X, Helm) ← à déployer
  └── myrag-backend + myrag-frontend (manifests kubectl dans myrag/k8s/)
```

Chacun a son propre ingress (`mesfichiers`, `<find>`, `mycollections`) et son propre client Keycloak :

| Service | Client Keycloak | Type | Usage |
|---------|----------------|------|-------|
| Drive (user login) | `drive` | confidential, auth flow | user se connecte sur Drive |
| Drive (ressource server) | `drive` (réutilisé) | confidential, introspection | Drive valide les Bearer de MyRAG |
| Find (user search) | (à créer : `find`) | public ou confidential | user se connecte sur Find |
| Find (ressource server) | (à créer : `find-rs`) | confidential, introspection | Find valide les Bearer des services |
| MyRAG (user login) | `myrag-front` | public PKCE | user se connecte sur MyRAG |
| MyRAG → Drive (service) | `mycollections-drive` | confidential, client_credentials | bot d'impersonation (fallback) |
| Drive → Find | `Service.token` de 50 chars | bearer statique | push indexation |

---

## Références

- Code Drive signals : `core/signals.py:15-22`, `core/tasks/search.py:52-64`, `core/services/search_indexers.py:370-383`
- Code Find views : `core/views.py` (IndexDocumentView + SearchDocumentView)
- Code Find search + ACL : `core/services/search.py` (`search`, `get_query`, `get_filter`)
- Code MyRAG Drive connector : [`myrag/app/services/connectors/drive.py`](../myrag/app/services/connectors/drive.py)
- Code MyRAG routes Drive : [`myrag/app/routers/sources.py`](../myrag/app/routers/sources.py)
- Pattern frontend picker : [`myrag/frontend/pages/admin/create/step-3.vue`](../myrag/frontend/pages/admin/create/step-3.vue)
