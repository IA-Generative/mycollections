# Importer un dossier de Fichiers

Fichiers est le Drive de La Suite numérique. Une personne choisit une **instance** de Fichiers, puis
un ou plusieurs dossiers, et les importe dans une collection, sous-dossiers compris. « Mettre à
jour » relit les dossiers et réindexe ce qui a changé : un fichier modifié est renvoyé, un fichier
supprimé dans Fichiers sort de l'index. Aucune mise à jour n'est planifiée pour l'instant.

La collection naît **privée** à la personne qui a importé les dossiers, et elle seule la met à jour.
Qui la gère peut ensuite l'ouvrir, dans le chat MirAI, à un groupe de son choix, avec la même
confirmation que pour Résana.

La capacité `fichiers` garde tout : éteinte (par défaut), les routes répondent 404 et l'assistant
de création ne propose pas Fichiers.

## Plusieurs instances, chacune avec son plafond de sensibilité

`MYCOLLECTIONS_FICHIERS_INSTANCES` déclare les instances, en tableau JSON :

```json
[
  {"id": "lasuite", "titre": "Fichiers interministériel", "url": "https://fichiers.fake-domain.name",
   "sensibilite_max": "public", "zone": "internet, interministériel"},
  {"id": "beta", "titre": "Mes fichiers (bêta)", "url": "http://drive-backend.<namespace>.svc.cluster.local",
   "hote_public": "mesfichiers.fake-domain.name", "stockage_url": "https://s3.fake-domain.name/seau",
   "sensibilite_max": "internal", "zone": "internet, bêta"},
  {"id": "rie", "titre": "Fichiers RIE", "url": "https://fichiers.rie.fake-domain.name",
   "sensibilite_max": "restricted", "zone": "RIE", "groupes": ["/g/agents-rie"]}
]
```

| Champ | Sens |
|---|---|
| `id` | court et stable (2 à 20 minuscules ou chiffres) : il entre dans l'identifiant des collections |
| `url` | l'adresse par laquelle Mes collections joint l'API : le service interne dans un cluster |
| `hote_public` | le nom public : en-tête `Host` (avec `X-Forwarded-Proto: https`) quand `url` est interne, et adresse des liens de consultation |
| `stockage_url` | le stockage objet derrière `/media/`, quand Mes collections ne peut pas passer par l'adresse publique (voir plus bas) |
| `sensibilite_max` | le niveau le plus haut que l'instance est censée contenir |
| `zone`, `description` | ce que l'écran en dit |
| `groupes` | réserve l'instance à ces groupes (chemins complets) |

Une déclaration illisible ou en double est ignorée, avec un avertissement dans le journal. Sans
déclaration, `DRIVE_URL` (et `DRIVE_PUBLIC_HOST`) donne une instance implicite `drive`, plafond
« Interne ».

### La règle : une collection ne descend pas sous ses sources

Les niveaux forment une échelle, du moins protégé au plus protégé :

| Rang | Valeur | Libellé |
|---|---|---|
| 0 | `public` | Public — internet |
| 1 | `internal` | Interne |
| 2 | `personal` | Données personnelles |
| 3 | `personal_sensitive` | Données personnelles sensibles |
| 4 | `controlled` | Diffusion contrôlée |
| 5 | `restricted` | Diffusion restreinte |

Une seule règle, celle de « pas d'écriture vers le bas » : **un contenant ne reçoit que du contenu
de niveau inférieur ou égal à son plafond** (`app/services/sensibilite.py`).

- **Les documents d'une instance sont réputés à son `sensibilite_max`.** La collection prend ce
  niveau à l'import. On peut la monter (à l'import, ou ensuite par la fiche) ; la descendre sous
  l'instance est refusé (409 `sensibilite_incompatible`, avec la raison).
- **Chaque destination a un plafond**, par `MYCOLLECTIONS_DESTINATIONS_SENSIBILITE_MAX`, un objet
  JSON : `{"chat": "internal", "recherche": "controlled", "navigateur": "internal"}`.
  - `chat` : la publication dans le chat MirAI est refusée au-dessus (409, avec la raison) ;
  - `recherche` : la collection n'apparaît pas dans la recherche de Mon portail (`/api/v1/search`) ;
  - `navigateur` : elle n'est pas proposée par l'extension (`/api/v1/sites`).

  Vide : aucune restriction, comme avant. La règle vaut pour toutes les collections, pas seulement
  celles de Fichiers.

Ainsi, une collection destinée à « Public — internet » (un guide pratique) se nourrit d'une instance
au plafond public, et rien de plus sensible ne s'y mêle. L'ordre est total, et c'est un choix
prudent : `personal` et `controlled` ne sont pas sur le même axe, mais en cas de doute la règle
range toujours vers le plus protecteur (comme la migration qui a rangé `confidential` et `secret`
en `restricted`).

## Comment Mes collections lit Fichiers

Mesuré sur la bêta le 2026-10-25 :

- **L'API `/api/v1.0/` accepte le jeton d'accès de la personne.** Drive le vérifie auprès du SSO :
  lister, parcourir et télécharger se font avec **ses** droits, rien de plus.
- **L'API pour applications tierces** (`/external_api/v1.0/`) n'autorise que les clients qu'on lui
  nomme (`OIDC_RS_ALLOWED_AUDIENCES`) et pas le téléchargement : elle n'est pas utilisée.
- **Les octets ne sont pas servis par Drive.** `/media/<clé>` passe par l'ingress : il demande à
  Drive une signature (`/api/v1.0/items/media-auth/`, avec l'adresse demandée dans
  `X-Original-URL`), puis lit le stockage objet avec elle. Depuis le cluster, l'adresse publique
  ne répond qu'une fois sur deux : Mes collections rejoue donc les deux pas (`stockage_url`), ce
  qui demande une règle de sortie vers le stockage. Sans `stockage_url`, il suit l'adresse
  publique du fichier, avec le jeton de la personne.
- **Joint par son service interne, Drive veut `Host` et `X-Forwarded-Proto`** : sinon 400 nu, ou
  301 vers l'adresse publique.

Pour une instance d'une autre fédération (La Suite interministérielle), le jeton du SSO de MirAI
doit être reconnu par elle. Les comptes MirAI se fédèrent par AgentConnect : c'est le chemin à
vérifier instance par instance avant de la déclarer.

## Routes

Toutes sous `/api/sources/fichiers`, gardées par la capacité `fichiers`. Elles reprennent celles de
Résana (l'« espace » y est l'instance) :

| Route | Effet |
|---|---|
| `GET /instances` | les instances que la personne peut importer, avec zone, plafond et niveaux permis |
| `GET /espaces/{instance}/dossiers` | tous les dossiers qu'elle voit (son espace et ce qu'on lui partage), avec parent et chemin |
| `GET /espaces/{instance}/apercu?dossier=` | le nombre de documents et leur taille |
| `GET /espaces/{instance}/inventaire?dossier=` | les sous-dossiers et leurs comptes |
| `GET /existant?espace=` | ses collections déjà ancrées sur cette instance |
| `GET /proposition?espace=&dossier=&suffixe=` | l'identifiant que recevra la collection |
| `POST /collections` | crée la collection (privée, `sensibilite` au moins le plafond) et lance l'import |
| `POST /sync/{collection}` | met à jour ; `dossiers`, `exclus`, `complet`, `incomplets` comme pour Résana |
| `POST /qualite/{collection}` | relit la qualité auprès de l'indexeur |
| `GET /status/{collection}` | l'état, la couverture, l'invitation à mettre à jour, `sensibilite_min` |
| `GET /ecartes/{collection}` | les documents écartés (CSV ou JSON) |

L'identifiant est `fichiers-<instance>-<8 premiers caractères du dossier>[-<suffixe>]`, posé par le
serveur ; le préfixe `fichiers-` est réservé (422 à une création manuelle).

## Le moteur, partagé avec Résana

Import et mise à jour passent par le moteur de Résana (`routers/sources_resana.py`, `docs/resana.md`)
: fiche par document (empreinte, date de modification, identifiant dans l'index, qualité), tri
nouveau / changé / inchangé / disparu, dossier d'attente sur le disque, envois parallèles, doublons,
conversion bureautique, relais du jeton tant que la page est ouverte, arrêt « partiel » qui garde
l'acquis. Le client de Fichiers (`services/connectors/fichiers.py`) parle comme celui de Résana.

Ce qui change d'une source à l'autre tient dans un **profil** (`services/synchro_profil.py`), posé
pour la durée d'une passe : le préfixe des identifiants dans l'index (`fichiers-…`), le dossier
d'attente (`_fichiers_attente`), la source écrite dans les métadonnées et le journal. Le profil par
défaut est celui de Résana : ses identifiants dans l'index (`resana-…`) ne changent pas.

Drive n'annonce pas de version : la date de modification (`updated_at`) en tient lieu. Une date
changée fait retélécharger le fichier, puis l'empreinte décide. « Tout revérifier » retélécharge
tout.

Particularités de Drive :

- un fichier vide dans Drive (« Nouveau document » crée un fichier vide) est écarté sans être
  téléchargé ;
- un fichier annoncé non vide mais reçu vide est redemandé, puis signalé « reçu vide » et repris à
  la mise à jour suivante ;
- un fichier encore en cours d'envoi (`upload_state` `pending`) ou d'analyse antivirus (`analyzing`)
  est écarté pour cette passe et repris à la suivante ; déjà indexé, il garde sa version d'avant ;
- un fichier que l'antivirus a signalé (`suspicious`) sort de la liste, comme Drive le cache aux
  membres : il n'est jamais indexé, et retiré s'il l'était ;
- un fichier trop gros pour l'antivirus (`file_too_large_to_analyze`) est servi par Drive : il est lu.

Ces états viennent de drive-migrator, l'outil de migration Résana → Fichiers de La Suite, qui les
traite pour vérifier ses migrations.

## Destinations

Une fois créée, la collection va là où vont les autres :

- **la recherche de Mon portail** (`/api/v1/search`, recherche fédérée) et **le chat MirAI**
  (publication à un groupe), sous leur plafond de sensibilité ;
- **l'extension navigateur** : l'adresse commune des documents (`https://<hote_public>/explorer/items/files/*`)
  devient un site déclaré, et la bulle « + IA » apparaît quand on parcourt Fichiers ;
- **depuis Fichiers lui-même**, pour les instances que nous déployons : `/admin/create/fichiers?instance=<id>&dossier=<id>`
  ouvre l'assistant prérempli. Un bouton « Indexer ce dossier dans Mes collections » dans le menu
  d'un dossier n'a besoin que de ce lien.

## Ce qui reste à faire

- la mise à jour planifiée (sans la page ouverte) et la mise à jour poussée par Drive ;
- la vérification, instance par instance, que le jeton fédéré est accepté (La Suite interministérielle) ;
- la sensibilité par document (#139).
