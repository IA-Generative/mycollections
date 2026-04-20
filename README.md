# Mes collections (beta)

Front augmenté DSFR pour OpenRAG. Module qui s'intercale entre l'utilisateur et OpenRAG pour offrir un découpage intelligent de documents, un graph de références croisées, une administration des collections en DSFR, et une intégration riche dans Open WebUI.

**Lien pour expérimenter** : [https://mycollections.fake-domain.name](https://mycollections.fake-domain.name) (alias : `mycorpus.fake-domain.name`).

## Raison d'être

**Mes collections** existe :
- pour qu'un **administrateur de données** puisse mettre à disposition des agents des corpus d'intérêt général ;
- pour que les **métiers** puissent mettre à disposition leurs codes et leur doctrine ;
- pour qu'un **agent public** puisse, au quotidien, transformer ses propres documents de travail en assistants conversationnels utiles à ses collègues — sans passer par une DSI, sans écrire de code, sans comprendre ce qu'est un embedding.

Dans l'usage courant, ça ressemble à ça :
- un référent métier rassemble une doc qu'il maîtrise (notes internes, guides, textes juridiques, dossiers Drive partagés) et la publie en quelques clics comme un **assistant disponible dans Open WebUI** pour son équipe ou son groupe ;
- il choisit à qui ça s'adresse, vérifie lui-même que les réponses tiennent la route, corrige ce qui dérape, et fait évoluer son corpus au fil de l'eau ;
- les utilisateurs finaux s'en servent comme d'un collègue qui aurait lu toute la doc, **laissent un pouce / un commentaire** quand une réponse est bonne ou mauvaise, et ces retours remontent directement à la personne qui maintient l'assistant.

C'est aussi, et assumé comme tel, un **playground pour recueillir de vraies évaluations usagers** : chaque collection publiée devient un terrain d'observation où l'on mesure ce qui marche, ce qui ne marche pas, et ce qui doit être retravaillé — côté corpus comme côté modèle. L'outil sert autant à produire des assistants qu'à apprendre, ensemble et en continu, comment un RAG se comporte face à de vrais besoins métier.

La diffusion d'une collection se fait à travers plusieurs canaux, à différents niveaux d'intégration dans les applications métier :
- **agent conversationnel mirai chat** (collection publiée en tant que modèle, alias de modèle, ou outil — notamment pour les graphes de références) ;
- **appel depuis un autre agent conversationnel** qui délègue la recherche à la collection ;
- **plug-in navigateur** qui écoute les URL consultées et propose un menu contextualisé par-dessus l'application ;
- **snippet HTML/JS** pour une intégration légère (« une ligne de code ») dans une application existante ;
- **API** pour une intégration serveur dans une application tierce.

## Sommaire

1. [Ce que fait l'application](#ce-que-fait-lapplication)
2. [Architecture](#architecture)
3. [Sources d'indexation supportées](#sources-dindexation-supportées)
4. [Démarrage local](#démarrage-local)
5. [Déploiement Scaleway](#déploiement-scaleway)
6. [Documentation](#documentation)

## Ce que fait l'application

- **Catalog DSFR** des collections de documents (parcours `/admin/catalog`).
- **Wizard 5 étapes** de création d'une collection : source, métadonnées, ingestion, évaluation, publication.
- **Connecteurs de source** : fichiers locaux (PDF/MD/DOCX…), URL distante, Légifrance (API PISTE), **Drive (Suite Numérique)** — indexation à la demande d'un dossier Drive partagé.
- **Chunking intelligent** (4 stratégies : auto, article, chunk, directory) avec stockage du fichier source sur PVC pour permettre la réindexation.
- **Archivage / purge réversible** d'une collection : archiver = dépublier OWUI + cacher du catalog (data conservée). Purger = hard-delete (OpenRAG partition + fichiers + DB en cascade). Modale de confirmation stricte avec re-saisie du nom.
- **Publication vers Open WebUI** : la collection devient un modèle `openrag-<nom>` utilisable comme outil ou alias dans OWUI, avec visibilité par groupe Keycloak.
- **Feedback OWUI** : ingestion des retours utilisateurs (👍/👎) via `POST /api/feedback/ingest`, review/promote vers `QRCache` (réponses curées servies directement) ou vers un `EvalDataset`. Un service de **pull automatique** depuis la DB OWUI ([myrag/app/services/owui_feedback_sync.py](myrag/app/services/owui_feedback_sync.py), CronJob K8s toutes les 15 min) mirror les feedbacks sur modèles `openrag-*` côté MyRAG, idempotent sur `owui_message_id`.
- **Playground RAG** ([myrag/frontend/pages/c/[id]/playground.vue](myrag/frontend/pages/c/[id]/playground.vue)) : page chat + **banque de questions de test** (colonne droite) qui agrège 4 sources via `GET /api/playground/{col}/bank` :
  - 🤖 auto-générées (seed au premier chargement si banque vide),
  - 📄 importées (JSON du wizard step-4 persisté en `EvalDataset`),
  - 👎 retours négatifs (`Feedback.rating < 0`),
  - 👍 promues (`QRCache` avec `source="feedback"`).

  Click sur une carte → la question part dans le chat. Vote 👍 → `QRCache` (réponse curée). Vote 👎 → nouveau `Feedback(rating=-1, status="pending")`. Bouton **« Lancer toute la banque »** → exécute toutes les questions en série et affiche un tableau synthétique en pied de colonne. Sources rendues comme puces cliquables sous chaque réponse, avec **popover au survol** (preview ~500 chars du chunk) et lien « Document complet » pour ouvrir l'original. Debug (prompt/chunks/modèle/temps) en accordéon replié sous chaque message. Le backend relaie `/extract/{id}`, `/file/{id}` et `/static/{path}` d'OpenRAG via `/api/openrag/*` avec le token admin côté serveur — les liens ouverts en nouvel onglet contournent ainsi le 401 de l'API OpenRAG.
- **Graph de références croisées** (NetworkX + Cytoscape.js) pour les collections le supportant.
- **Sync Keycloak ↔ OpenRAG** : propagation des groupes `rag-query/<collection>` vers les partitions.

## Architecture

```
[Frontend Nuxt 4 + DSFR — port 8201 en dev, 3000 en prod via ingress]
     │
     ▼
[MyRAG FastAPI — port 8200]
     │
     ├── OpenRAG         (RAG backend, sur VM Scaleway en prod, Docker compose en local)
     ├── Keycloak        (OIDC realm openwebui)
     ├── Drive           (Suite Numérique, via /external_api/v1.0/)
     ├── Open WebUI      (publication des collections comme modèles)
     └── PostgreSQL      (DB myrag, partagée avec keycloak/myvault en prod)
```

Stack :
- **Backend** : Python 3.12, FastAPI, SQLAlchemy async (SQLite dev / PostgreSQL prod), httpx, NetworkX.
- **Frontend** : Nuxt 4, `@gouvfr/dsfr`, `oidc-client-ts` (PKCE).
- **Auth** : Keycloak OIDC PKCE (realm `openwebui`, client `myrag-front` public + client `mycollections-drive` confidential pour service-to-service Drive).
- **Tests** : pytest + pytest-asyncio.
- **Images** : Docker multi-stage, déployées en K8s (Scaleway Kapsule) via manifests dans `myrag/k8s/`.

Schéma détaillé + ports + variables d'environnement → [CLAUDE.md](CLAUDE.md).

## Sources d'indexation supportées

| Source | Statut | Flux |
|-------|:-----:|------|
| Fichier local (upload) | ✅ | POST `/api/ingest/{collection}` multipart |
| URL distante | ✅ | POST `/api/ingest/{collection}/from-url` |
| Légifrance (PISTE) | ✅ | `/api/sources/legifrance/*` |
| **Drive (Suite Numérique)** | ✅ | `/api/sources/drive/*` |
| Nextcloud | 🟡 UI présente, backend TODO | — |
| Resana | 🟡 UI présente, backend TODO | — |

### Drive : comment ça marche

MyRAG s'authentifie à Drive via **`client_credentials`** sur le client Keycloak confidentiel `mycollections-drive`, puis appelle l'API OIDC-RS de Drive (`/external_api/v1.0/items/*`) avec un Bearer. Drive accepte les requêtes au nom d'un **user "bot" local** (`mycollections-drive@bot.local`) dont le `sub` matche celui du service account.

Pour qu'un dossier Drive soit indexable :
1. L'admin/propriétaire du dossier le **partage au bot** `mycollections-drive@bot.local` (viewer) via l'UI Drive — c'est le même geste que partager à un collègue.
2. Dans le wizard `/admin/create` → Drive → étape 3 affiche le picker des dossiers visibles par le bot.
3. Clic **"Indexer ce dossier"** → POST `/api/sources/drive/add` → import async : chaque fichier devient un `ingest_job` trackable dans `/admin`.
4. Re-sync incrémentale via `POST /api/sources/drive/sync/{collection}` (bouton "Rafraîchir").

Détail technique du provisioning bot + Helm Drive → [myrag/DEPLOYMENT.md](myrag/DEPLOYMENT.md) section 1.5.

### Sécurité : qui voit quoi ?

Partager un dossier Drive au bot ≠ rendre son contenu public. Il y a **deux couches d'ACL** empilées :

1. **Drive ACL** (côté source) — le bot voit uniquement ce qu'on lui partage. Les autres humains ne sont pas affectés.
2. **MyRAG / OWUI ACL** (côté indexé) — une fois ingéré, le contenu appartient à une collection MyRAG. Cloisonnement via :
   - `scope = group` à la création → visible uniquement aux membres du groupe Keycloak.
   - `visibility_groups` à la publication OWUI → modèle proposé aux groupes listés uniquement.
   - `POST /api/sync` → propagation des groupes Keycloak vers OpenRAG pour filtrer les réponses RAG.

**Par défaut, sans précautions, une collection `scope=all` indexée depuis Drive est interrogeable par tout utilisateur MyRAG.** Choisir explicitement `scope=group` à l'étape 2 du wizard pour cloisonner.

Points à durcir (cf. `continue-keen-hamming.md` priorité 3) : `/admin/catalog` et `/c/{id}/playground` ne sont pas encore filtrés par rôle — tout user authentifié peut lister et interroger.

### Filtrage du picker Drive par utilisateur (impersonation)

**Problème résolu** : en v1 naïve, le picker appelait Drive avec un service account (`mycollections-drive`) → tous les dossiers partagés au bot étaient listés à **tous** les admins MyRAG. Un admin A pouvait indexer le dossier partagé par l'admin B sans son consentement.

**Solution implémentée (2026-04-19, option 1a)** :
- Les routes `/api/sources/drive/folders`, `/drive/add`, `/drive/sync/*`, `/drive/status/*` **reçoivent et relaient le token OIDC de l'utilisateur connecté** (`Authorization: Bearer <user_access_token>`). Drive voit l'appel comme fait par cet utilisateur → retourne uniquement les dossiers que cet utilisateur peut voir.
- **Download synchrone avant async** : dans `/drive/add`, MyRAG télécharge tous les fichiers du dossier **pendant l'appel HTTP initial** (où le token user est encore valide), puis lance le chunking + upload OpenRAG en arrière-plan depuis les bytes déjà en mémoire. Plus aucun appel Drive après que la route a répondu.
- **Access token lifespan bumped à 15 min** pour le client Keycloak `myrag-front` (attribut `access.token.lifespan=900`), ce qui laisse largement le temps de télécharger un dossier raisonnable avant expiry.
- **Garde-fou** : refus si le dossier contient > 500 fichiers ou > 500 MB cumulés (HTTP 413) — l'utilisateur doit fractionner.

**Conséquence pratique** :
- Dans le picker, chaque user voit **ses propres dossiers + ceux qu'on lui a partagés** (via l'UI Drive). Pas ceux de ses collègues.
- L'audit Drive montre le vrai user comme auteur de la lecture massive (plus traçable qu'un bot).
- Plus besoin de provisionner un user bot dans Drive pour le flow nominal (le user bot reste uniquement utilisé par `/api/sources/drive/sync/*` en ligne de commande d'admin, où aucun user n'est connecté).

**Limite connue** : si le téléchargement prend > 15 min (gros dossiers, Drive lent), le token expire pendant l'appel et `/drive/add` retourne 502. Dans ce cas : fractionner, ou implémenter l'offline_access + refresh token (V2).

**Pré-requis utilisateur** : Drive auto-provisionne son `core.User` local à la **première connexion interactive** sur `https://mesfichiers.fake-domain.name`. Tant que ce n'est pas fait, le resource server de Drive répond `403 Forbidden` (on voit dans MyRAG : *"Votre compte n'est pas encore connu de Drive. Connectez-vous une fois sur https://mesfichiers.fake-domain.name puis revenez ici."*). Un seul login suffit, ensuite tout fonctionne.

### Gestion des sessions et expirations

Trois timeouts en cascade :

| Couche | Valeur actuelle | Ce qui expire | Conséquence |
|--------|----------------|---------------|-------------|
| Access token (client `myrag-front`) | **15 min** | Bearer utilisé dans `Authorization` | À chaque appel API, le Bearer peut être rejeté en 401 → besoin d'un renew |
| SSO session idle (realm `openwebui`) | **4 h** (bump 2026-04-19) | La session Keycloak si l'user est inactif | Au-delà, le refresh token stocké par le browser ne peut plus obtenir un nouveau access token |
| SSO session max | **10 h** | La session Keycloak absolue | Forced re-login au-delà, quoi qu'il arrive |

Côté frontend, le flow est :
1. `oidc-client-ts` démarre un `automaticSilentRenew` (best-effort, ~60 s avant expiry, via iframe caché).
2. Quand un fetch MyRAG répond 401, `useApi` déclenche un **`mgr.signinSilent()` explicite** (utilise le refresh token) et **retry le fetch une fois**.
3. Si le retry est aussi 401, on propage l'erreur — le layout ou le caller décide (typiquement : redirect login interactif).

Ce pattern absorbe les cas fréquents où `automaticSilentRenew` échoue silencieusement (3rd-party cookies, Safari ITP, iframe bloqué). Les flows async serveur-side (comme l'ingestion Drive) ne dépendent **pas** du token user une fois lancés : MyRAG télécharge les bytes pendant le call HTTP (token encore valide), puis ingest depuis la mémoire (plus aucun appel Drive).

Pour les vrais flows long-running (>15 min, réindexation massive), la V2 utilisera un **pattern hybride user + bot** : l'user autorise une fois, puis l'import passe par le service account `mycollections-drive` qui a un access token renouvelable à l'infini via `client_credentials`.

## Démarrage local

Prérequis : Docker Desktop, Node 22, Python 3.12, le repo `openrag` et `owuicore-main` clonés à côté.

```bash
# 1. Démarrer les dépendances
cd ../owuicore-main      && docker compose up -d   # Keycloak + OWUI + Pipelines + Tika
cd ../openrag            && docker compose --profile cpu up -d

# 2. Démarrer MyRAG backend (image Docker locale)
cd ../mycollections
docker build -t myrag:beta myrag/
docker run -d --name myrag-test \
  -p 8200:8200 --dns 8.8.8.8 --dns 8.8.4.4 \
  --add-host=host.docker.internal:host-gateway \
  -v myrag-data:/app/data \
  -e OPENRAG_URL=http://openrag-openrag-cpu-1:8080 \
  -e OPENRAG_ADMIN_TOKEN=or-admin-openrag-2026 \
  -e KEYCLOAK_URL=http://host.docker.internal:8082 \
  -e KEYCLOAK_REALM=openwebui \
  --network openrag_default myrag:beta

# 3. Démarrer le frontend en dev
cd myrag/frontend
npm install
AUTH_ENABLED=false npx nuxt dev --port 8201

# 4. Vérifier
curl http://localhost:8200/health            # backend
curl http://localhost:8201/                  # frontend
```

## Déploiement Scaleway

Cible : Kapsule **`k8s-par-brave-bassi`**, namespace **`miraiku`**. OpenRAG tourne sur une VM Scaleway séparée (`api.openrag.fake-domain.name`). DB PostgreSQL partagée dans `miraiku` (DB dédiée `myrag`, user `app`).

```bash
# Build + push images (TOUJOURS linux/amd64 — Mac ARM64 par défaut = exec format error)
TAG=$(git rev-parse --short HEAD)
scw registry login
docker buildx build --platform linux/amd64 --push \
  -t rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/myrag-backend:$TAG \
  -t rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/myrag-backend:latest myrag/
docker buildx build --platform linux/amd64 --push \
  -t rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/myrag-frontend:$TAG \
  -t rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/myrag-frontend:latest myrag/frontend/

# Apply (secret.yaml à remplir localement depuis secret.yaml.template)
cp myrag/k8s/secret.yaml.template myrag/k8s/secret.yaml  # puis éditer
kubectl apply -f myrag/k8s/secret.yaml -f myrag/k8s/configmap.yaml -f myrag/k8s/pvc.yaml \
              -f myrag/k8s/service-backend.yaml -f myrag/k8s/service-frontend.yaml \
              -f myrag/k8s/deployment-backend.yaml -f myrag/k8s/deployment-frontend.yaml \
              -f myrag/k8s/ingress.yaml
kubectl -n miraiku rollout status deploy/myrag-backend
```

Procédure complète (création DB, provisioning bot user Drive, troubleshooting amd64 / naive UTC datetimes / nginx redirects / redirect_uri Keycloak) → [myrag/DEPLOYMENT.md](myrag/DEPLOYMENT.md).

## Documentation

- [CLAUDE.md](CLAUDE.md) — architecture interne, variables d'environnement, problèmes connus, procédure de démarrage du stack complet local.
- [myrag/DEPLOYMENT.md](myrag/DEPLOYMENT.md) — procédure de déploiement Scaleway pas-à-pas + troubleshooting.
- [openwebui/README.md](openwebui/README.md) — plugin Open WebUI pour consommer les collections publiées.

## Licence

(À définir.)
