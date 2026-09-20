# Mes collections (beta)

Front augmenté DSFR pour OpenRAG. Module qui s'intercale entre l'utilisateur et OpenRAG pour offrir un découpage intelligent de documents, un graph de références croisées, une administration des collections en DSFR, et une intégration riche dans Open WebUI.

![Page d'accueil de Mes collections : ce que vos collections ont rendu possible, les trois gestes — découvrir, explorer, créer —, la demande d'un jeu de données et les portes par catégorie](docs/images/accueil.png)

*L'accueil, avec des données d'exemple. Il invite à découvrir, puis à partager : un exemple de question prêt à poser, le catalogue, l'assistant de création, et la marche à suivre quand une donnée manque.*

> Les adresses en `fake-domain.name` de ce document sont des **exemples** : remplacez-les par celles de votre déploiement.

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
5. [Déploiement sur Kubernetes](#déploiement-sur-kubernetes)
6. [Documentation](#documentation)

## Ce que fait l'application

- **Un accueil qui invite à découvrir, puis à partager** ([pages/index.vue](myrag/frontend/pages/index.vue)) : une question d'exemple tirée du jeu d'évaluation d'une collection publiée à tous, prête à poser dans le bac à sable ; les chiffres de ce qui existe ; et, pour qui partage déjà, ce que ses collections ont rendu possible.
- **Catalogue DSFR** des collections, rangées par **catégorie** (parcours `/admin/catalog`) ; chaque collection porte un titre lisible, distinct de son identifiant technique.
- **Le collectif** : quand une donnée manque, on la **demande** ; une demande qui rassemble assez de collègues et un garant devient un chantier, amorcé depuis ce qui existe (open data, Légifrance, fichiers du service), vérifié, puis publié. Modèle, états et routes → [docs/collectif.md](docs/collectif.md) ; le guide en six étapes est servi par l'application (`/guide`, sources dans [myrag/app/guide/](myrag/app/guide/)).
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

  Click sur une carte → la question part dans le chat. Vote 👍 → `QRCache` (réponse curée). Vote 👎 → nouveau `Feedback(rating=-1, status="pending")`. Bouton **« Lancer toute la banque »** → exécute toutes les questions en série et affiche un tableau synthétique en pied de colonne. Debug (prompt/chunks/modèle/temps) en accordéon replié sous chaque message, les morceaux y sont rendus en Markdown.

  ![Bulle au survol d'une puce de source](docs/images/source-bulle.png)

  **Les sources d'une réponse** — écrans et règles à ne pas défaire dans [docs/sources.md](docs/sources.md) — s'affichent en puces sous le message ([SourceChip.vue](myrag/frontend/components/playground/SourceChip.vue)) :
  - **au survol** (ou au focus clavier), une bulle montre le début du morceau et deux boutons, « Lire l'extrait » et « Document complet ». La bulle est posée sur la fenêtre (`Teleport`, position fixe) : la zone de messages défile et la rognerait. Elle reste ouverte le temps que la souris la rejoigne, et se ferme au défilement ou sur Échap ;
  - **au clic**, une fenêtre de lecture s'ouvre sans quitter la page ([SourceViewer.vue](myrag/frontend/components/playground/SourceViewer.vue)) : texte rendu en Markdown assaini, résumé du document en encart, **export Word et PDF** (sans aller-retour serveur), « Ouvrir dans un onglet ». Ctrl/Cmd-clic garde le comportement d'un lien. Si la relecture du morceau échoue, la fenêtre montre le texte déjà reçu avec la réponse ;
  - **les balises techniques d'OpenRAG** (`[CONTEXT]`, `* filename:`, `[CHUNK_START]`, `[CHUNK_END]`) ne sont jamais montrées : `decouperMorceau` ([utils/extrait.ts](myrag/frontend/utils/extrait.ts)) sépare le résumé, le nom de fichier et le texte ; `_decouper_morceau` fait la même découpe côté backend.

  Le backend relaie `/extract/{id}`, `/file/{id}` et `/static/{path}` d'OpenRAG via `/api/openrag/*` avec le token admin côté serveur — un lien ouvert dans un onglet contourne ainsi le 401 de l'API OpenRAG. `/api/openrag/extract/{id}` rend une page HTML autonome et lisible (paragraphes, adresses cliquables, **pas de lien « Retour »** : un onglet neuf n'a pas d'historique) ; `?raw=1` rend le JSON d'OpenRAG tel quel, balises comprises — c'est ce que lit la fenêtre de lecture. `/static/{path}` propage `?raw=1` quand il se replie sur le morceau.
- **Graph de références croisées** (NetworkX + Cytoscape.js) pour les collections le supportant.
- **Sync Keycloak ↔ OpenRAG** : propagation des groupes `rag-query/<collection>` vers les partitions.

## Architecture

```
[Frontend Nuxt 4 + DSFR — port 8201 en dev, 3000 en prod via ingress]
     │
     ▼
[MyRAG FastAPI — port 8200]
     │
     ├── OpenRAG         (backend RAG ; Docker compose en local)
     ├── Keycloak        (OIDC realm openwebui)
     ├── Drive           (Suite Numérique, via /external_api/v1.0/)
     ├── Open WebUI      (publication des collections comme modèles)
     └── PostgreSQL      (base `myrag` ; SQLite en développement)
```

Stack :
- **Backend** : Python 3.12, FastAPI, SQLAlchemy async (SQLite dev / PostgreSQL prod), httpx, NetworkX.
- **Frontend** : Nuxt 4, `@gouvfr/dsfr`, `oidc-client-ts` (PKCE).
- **Auth** : Keycloak OIDC PKCE (realm `openwebui`, client `myrag-front` public + client `mycollections-drive` confidential pour service-to-service Drive).
- **Tests** : pytest + pytest-asyncio (`myrag/tests/`), vitest (`myrag/frontend/tests/`).
- **Images** : Docker multi-stage, déployées sur Kubernetes via les manifestes de `myrag/k8s/`.

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

Point à durcir : `/admin/catalog` et `/c/{id}/playground` ne sont pas encore filtrés par rôle — tout utilisateur authentifié peut lister et interroger.

### Filtrage du picker Drive par utilisateur (impersonation)

**Problème résolu** : en v1 naïve, le picker appelait Drive avec un service account (`mycollections-drive`) → tous les dossiers partagés au bot étaient listés à **tous** les admins MyRAG. Un admin A pouvait indexer le dossier partagé par l'admin B sans son consentement.

**Solution implémentée** :
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
| SSO session idle (realm `openwebui`) | **4 h** | La session Keycloak si l'user est inactif | Au-delà, le refresh token stocké par le browser ne peut plus obtenir un nouveau access token |
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
  -e OPENRAG_ADMIN_TOKEN=<jeton-admin-openrag> \
  -e KEYCLOAK_URL=http://host.docker.internal:8082 \
  -e KEYCLOAK_REALM=openwebui \
  --network openrag_default myrag:beta

# 3. Démarrer le frontend en dev
cd myrag/frontend
npm install
AUTH_ENABLED=false npx nuxt dev --port 8201

# Tests
(cd .. && python3 -m pytest tests/unit -q)   # backend
npx vitest run                               # frontend

# 4. Vérifier
curl http://localhost:8200/health            # backend
curl http://localhost:8201/                  # frontend
```

## Déploiement sur Kubernetes

Les manifestes sont dans `myrag/k8s/`. Trois paramètres dépendent de votre environnement et
n'ont pas de valeur par défaut ici : le **registre** d'images (`<REGISTRE>`), le **namespace**
(`<NAMESPACE>`) et les **adresses** publiques. OpenRAG peut tourner ailleurs que dans le
cluster ; la base PostgreSQL `myrag` doit exister avant le premier démarrage.

> **Les adresses du SSO sont cuites dans l'image du frontend** : Nuxt en mode statique lit
> `KEYCLOAK_URL`, `KEYCLOAK_REALM` et `KEYCLOAK_CLIENT_ID` à la construction, pas au démarrage.
> Les changer impose de reconstruire l'image — modifier un ConfigMap n'y fait rien.

```bash
# Construire et pousser (TOUJOURS linux/amd64 : un Mac ARM64 produit sinon « exec format error »)
TAG=$(git rev-parse --short HEAD)
docker buildx build --platform linux/amd64 --push -t <REGISTRE>/myrag-backend:$TAG  myrag/
docker buildx build --platform linux/amd64 --push -t <REGISTRE>/myrag-frontend:$TAG \
  --build-arg KEYCLOAK_URL=https://<votre-sso> myrag/frontend/

# Appliquer (secret.yaml se remplit localement depuis secret.yaml.template, et ne se commite pas)
cp myrag/k8s/secret.yaml.template myrag/k8s/secret.yaml  # puis éditer
kubectl apply -f myrag/k8s/secret.yaml -f myrag/k8s/configmap.yaml -f myrag/k8s/pvc.yaml \
              -f myrag/k8s/service-backend.yaml -f myrag/k8s/service-frontend.yaml \
              -f myrag/k8s/deployment-backend.yaml -f myrag/k8s/deployment-frontend.yaml \
              -f myrag/k8s/ingress.yaml
kubectl -n <NAMESPACE> rollout status deploy/myrag-backend
```

Préférez un tag d'image **immuable** à `latest` : c'est ce qui permet de dire quelle version
tourne, et de revenir en arrière.

### Branchement OWUI ↔ OpenRAG (one-shot, à faire une fois par cluster)

Le bouton **« Publier »** côté MyRAG crée un wrapper de modèle dans OWUI qui aliase un modèle `openrag-<collection>`. Pour qu'OWUI sache router l'inférence vers ces modèles, il faut **deux étapes admin one-shot**, après quoi chaque future publication MyRAG marche sans action supplémentaire :

**1. Déclarer OpenRAG comme provider OpenAI dans OWUI** (les `openrag-*` deviennent auto-découvrables) :

```bash
# Ajoute OpenRAG comme fournisseur compatible OpenAI, à côté de ceux déjà déclarés.
# Le rollout est automatique sur set env. Les trois listes se lisent dans le même ordre.
kubectl -n <NAMESPACE> set env deploy/openwebui \
  OPENAI_API_BASE_URLS="<vos fournisseurs existants>;https://api.openrag.fake-domain.name/v1" \
  OPENAI_API_KEYS="<leurs clés, dans le même ordre>;<OPENRAG_ADMIN_TOKEN>" \
  OPENAI_API_CONFIGS='[<une entrée par fournisseur existant>,{"prefix":"openrag-","name":"OpenRAG"}]'
```

**2. Donner à MyRAG la clé API admin OWUI** (pour appeler `/api/v1/models/create`) :

```bash
# Génère une clé dans OWUI : Paramètres > Compte > Clés API (compte avec rôle admin).
kubectl -n <NAMESPACE> patch secret myrag-secrets --type=merge \
  -p "{\"stringData\":{\"OWUI_ADMIN_API_KEY\":\"sk-...\"}}"
kubectl -n <NAMESPACE> rollout restart deploy/myrag-backend
```

**Vérification** :

```bash
# Doit lister les modèles openrag-* avec connection_type=external (pas preset)
curl -sS https://mychat.fake-domain.name/api/models \
  -H "Authorization: Bearer $(kubectl -n <NAMESPACE> get secret myrag-secrets -o jsonpath='{.data.OWUI_ADMIN_API_KEY}' | base64 -d)" \
  | python3 -c "import sys,json; print('\n'.join(sorted([m['id'] for m in json.load(sys.stdin)['data'] if 'openrag' in m['id']])))"

# Diagnostic complet de la chaîne OWUI (clé valide ? admin ? base models discoverables ?)
curl -sS https://mycollections.fake-domain.name/api/owui/probe | python3 -m json.tool
```

Pour que ces réglages survivent au prochain redéploiement d'Open WebUI, reportez-les dans sa configuration versionnée (variables `OPENAI_API_BASE_URLS`, `OPENAI_API_KEYS`, `OPENAI_API_CONFIGS`).

Procédure détaillée (création de la base, compte de service Drive, dépannage) → [myrag/DEPLOYMENT.md](myrag/DEPLOYMENT.md).

## Documentation

- [docs/sources.md](docs/sources.md) — lire les sources d'une réponse : écrans, et règles à ne pas défaire.
- [docs/collectif.md](docs/collectif.md) — le collectif : modèle, états, routes, fil d'avancement ; décision dans [ADR-0001](docs/adr/ADR-0001-collections-collaboratives-modele-et-etats.md).
- [myrag/app/guide/](myrag/app/guide/) — le guide « Soyez acteurs vous-mêmes », en six étapes, servi par l'application.
- [docs/drive-find-architecture.md](docs/drive-find-architecture.md) — comment Drive et son moteur de recherche s'articulent.
- [CLAUDE.md](CLAUDE.md) — repères pour travailler dans le dépôt : dépendances, architecture interne, fichiers clés, variables d'environnement, problèmes connus.
- [myrag/DEPLOYMENT.md](myrag/DEPLOYMENT.md) — déploiement pas à pas et dépannage.
- [openwebui/README.md](openwebui/README.md) — plugin Open WebUI pour consommer les collections publiées.
- [TODO.md](TODO.md) — ce qui reste à faire, et les défauts connus.

## Licence

(À définir.)
