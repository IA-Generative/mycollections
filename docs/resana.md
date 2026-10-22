# Importer un dossier Résana

Une personne choisit un dossier d'un de ses espaces Résana et l'importe dans une collection, sous-dossiers
compris. Elle interroge ensuite la collection comme les autres. « Synchroniser » relit le dossier et
réindexe ce qui a changé. Aucune synchronisation n'est planifiée.

Ce n'est pas encore un partage : en v1, **la collection reste privée à la personne qui a importé le
dossier**, et elle seule peut la synchroniser.

## Comment Mes collections lit Résana

Résana n'a pas d'API publique. Le service `owuitools-resana` sert quatre routes en lecture sous `/export/v1`
(contrat : `docs/export-v1.md` de ce dépôt-là, qui fait foi). Il les sert **avec la session Résana de la
personne** : il l'ouvre lui-même à partir des identifiants qu'elle a rangés dans son coffre, double facteur
compris.

Mes collections s'y présente avec deux en-têtes, tous deux obligatoires :

| En-tête | Valeur |
|---|---|
| `X-Internal-Token` | le secret propre à Mes collections (`MYCOLLECTIONS_RESANA_EXPORT_SECRET`) |
| `Authorization` | `Bearer <jeton d'accès de la personne>`, tel que reçu du navigateur |

Le service vérifie lui-même le jeton et en tire l'adresse de la personne. Mes collections ne met jamais
d'adresse dans une requête, n'utilise pas de compte de service et ne demande jamais de mot de passe. Les
droits appliqués sont ceux de la personne dans Résana.

| Route du service | Usage dans Mes collections |
|---|---|
| `GET /espaces` | la liste des espaces ; peut ouvrir la session de la personne (jusqu'à 90 s) |
| `GET /espaces/{id}/dossiers?search=` | le choix du dossier |
| `GET /espaces/{id}/documents?dossier=&recursif=true` | la liste **complète** du dossier, page par page (`suivant`) ; un curseur expiré (410) relance la lecture une fois |
| `GET /documents/{id}/fichier?espace=` | les octets d'origine, lus en flux, 100 Mo au plus |

## Routes de Mes collections

Toutes sont sous `/api/sources/resana` et gardées par la capacité `resana`. Elle est éteinte par défaut :
sans elle, chaque route répond 404 et l'écran ne propose pas Résana.

| Route | Qui | Effet |
|---|---|---|
| `GET /espaces` | toute personne connectée | ses espaces, triés par nom |
| `GET /espaces/{id}/dossiers?recherche=` | toute personne connectée | les dossiers de l'espace |
| `GET /espaces/{id}/apercu?dossier=` | toute personne connectée | le nombre de documents et leur taille approchée |
| `POST /add` | la personne qui a **créé** la collection | relie la collection au dossier et lance l'import |
| `POST /sync/{collection}` | la personne qui a importé | relit le dossier et réindexe s'il a changé |
| `GET /status/{collection}` | qui peut lire la collection | le dossier relié, l'avancement, et `est_importeur` |

Les erreurs du service sont rendues telles quelles : `{code, message, reessayable}`, plus `url_connexion`
quand la session est absente. Deux exceptions :

- un 401 du service (jeton refusé, ou Mes collections inconnu du service) devient un **502** ; l'écran ne
  déconnecte pas la personne pour une affaire entre deux services ;
- le lien de connexion n'est transmis que s'il est en `https://`.

## La règle de la v1 : privée à qui importe

Importer, c'est lire Résana avec ses propres droits. Si la collection s'ouvrait à d'autres, ceux-ci
liraient ce que Résana leur refuse peut-être. Tant qu'aucune décision n'ouvre ce partage (avec une
confirmation explicite), une collection Résana reste privée :

- **Import** : seulement par la personne qui a créé la collection (`created_by`), dans une collection
  **privée, sans groupe lecteur, vide et non publiée**. L'assistant de création la crée ainsi : à
  l'étape 2, « Qui peut l'interroger ? » est fixé à « Moi seulement ». L'import pose de nouveau la portée
  `private` avant de télécharger quoi que ce soit.
- **Synchronisation** : seulement par la personne qui a importé, avec sa propre session Résana. Un
  administrateur du service ne peut pas le faire à sa place (403 `reserve_a_l_importeur`).
- **Fiche** : `PATCH /api/collections/{nom}` refuse (409) de changer `scope`, `scope_groups`,
  `source_type`, `source_url` ou `source_config_json` d'une collection Résana. Renvoyer la même valeur
  passe. Aucune collection ne devient Résana par sa fiche.
- **Publication** : une collection Résana ne se publie pas dans l'assistant (409). Un brouillon reste
  permis.

Ce qui reste ouvert, comme pour toute collection privée : les administrateurs du service et les membres
du groupe `<racine>/<nom>-admin` la lisent.

## Import et synchronisation

1. La route relit la liste complète du dossier, sans `depuis` : c'est elle qui révèle les suppressions.
   Les erreurs immédiates (session absente, dossier trop gros, service en panne) reviennent à l'écran.
2. Le téléchargement se fait en tâche de fond, quatre documents à la fois. Le jeton de la personne reste
   en mémoire le temps de la tâche et n'est jamais écrit. L'écran suit l'avancement par `/status`.
3. Chaque document est comparé par son **sha256**. Le service ne donne pas d'ETag, et `version_fichier`
   n'est pas garanti. Résultat :
   - un contenu déjà vu sous un autre document est écarté (doublon) ;
   - un format non pris en charge est écarté ;
   - un document refusé par Résana (`hors_droits`, `introuvable`, `trop_volumineux`) est écarté, et
     retiré s'il avait été importé.
4. Si rien n'a changé, la synchronisation le dit (« à jour ») et ne touche pas à l'index.
5. Sinon :
   - les documents disparus sont retirés (ligne et fichier gardé) ;
   - les nouveaux et les modifiés sont gardés ;
   - la partition OpenRAG est vidée puis tout est renvoyé, comme pour une réindexation : Mes collections
     ne connaît pas l'identifiant OpenRAG d'un fichier, c'est donc la seule façon de retirer une ancienne
     version.
6. Une erreur bloquante en cours de route arrête tout sans rien appliquer : session perdue, jeton
   expiré, service indisponible, plus de 500 Mo au total. L'état passe à « échec », avec le message et,
   s'il y a lieu, le lien de connexion. Il suffit de synchroniser de nouveau.

Les noms de fichiers viennent du service (`Content-Disposition`). Deux documents de même nom sont
distingués par l'identifiant Résana : `note (1234).pdf`. Un nom donné à l'import ne change plus.

`source_config_json` garde :

- l'espace et le dossier (identifiant et libellé) ;
- pour chaque document : son sha256, son nom de fichier, son adresse de consultation et sa version ;
- la date de la dernière lecture ;
- l'état du dernier travail.

Cette configuration ne sort que par `/status`, et sans la liste des documents.

L'adresse de consultation Résana (`url_consultation`, donnée par le service, jamais construite ici) est
gardée comme adresse d'origine de chaque fichier. **Les citations du bac à sable n'affichent pas encore
de lien « Ouvrir dans Résana »** : elles passent par l'extrait OpenRAG, comme pour toute collection.

## Écrans

- **Assistant de création, étape 1** : la carte « Un dossier Résana » n'apparaît que si la capacité est
  allumée. Sinon, Résana reste dans la ligne « Bientôt ».
- **Étape 2** : la portée est fixée à « Moi seulement », avec une phrase qui dit pourquoi.
- **Étape 3** : le choix se fait en quatre temps.
  1. La liste des espaces. Un message prévient que la première ouverture de session peut prendre une
     minute et demie.
  2. Le filtre des dossiers.
  3. L'aperçu : nombre de documents, taille approchée et premiers titres.
  4. « Importer le dossier », puis l'avancement.

  Sans session Résana, un avertissement donne le lien de connexion du service et un bouton « Réessayer ».
- **Ajouter des documents** (page d'une collection) : la carte « Dossier Résana » montre le dossier
  relié, le nombre de documents, la dernière lecture, l'avancement et les documents écartés.
  « Synchroniser » n'y apparaît que pour la personne qui a importé.

## Configuration

| Variable | Défaut | Rôle |
|---|---|---|
| `MYCOLLECTIONS_RESANA_EXPORT_URL` | `` | adresse interne du service d'export (sans `/export/v1`) ; vide ⇒ 503 |
| `MYCOLLECTIONS_RESANA_EXPORT_SECRET` | `` | secret propre à Mes collections, attendu par le service dans `X-Internal-Token` ; vide ⇒ 503 |
| capacité `resana` | `false` | `capacites.json` du menu commun, ou `MYCOLLECTIONS_CAPACITES_SURCHARGE='{"resana": true}'` |

En cluster, il faut aussi une règle réseau qui laisse Mes collections joindre le service Résana sur son
port d'export.

## Tests

- `myrag/tests/unit/test_resana_client.py` teste le client :
  - les en-têtes ;
  - la pagination et le curseur expiré ;
  - les plafonds ;
  - les erreurs ;
  - les noms de fichiers.
- `myrag/tests/unit/test_resana_routes.py` teste les routes :
  - la capacité ;
  - les droits ;
  - la collection privée ;
  - le dédoublonnage ;
  - la synchronisation par sha256 ;
  - l'arrêt sur session perdue.

  Un témoin de jeton y est cherché dans les réponses, les journaux et la base, où il ne doit jamais
  apparaître.
- Le faux service, `myrag/tests/unit/_faux_resana.py`, applique le contrat v1. Aucun test n'appelle
  Résana.
- `myrag/frontend/tests/unit/resana.test.ts` teste l'écran :
  - la lecture des erreurs ;
  - les phrases d'avancement ;
  - la carte qui suit la capacité.
