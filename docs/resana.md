# Importer un dossier Résana

Une personne choisit un dossier d'un de ses espaces Résana et l'importe dans une collection, sous-dossiers
compris. Elle interroge ensuite la collection comme les autres. « Synchroniser » relit le dossier et
réindexe ce qui a changé. Aucune synchronisation n'est planifiée.

**La collection naît privée à la personne qui a importé le dossier**, et elle seule peut la
synchroniser. Qui la gère peut ensuite l'ouvrir, dans le chat MirAI, à un groupe de son choix : c'est
elle qui pilote (voir « Partager une collection Résana »).

## Comment Mes collections lit Résana

Le service `owuitools-resana` sert quatre routes en lecture sous `/export/v1`
(contrat : `docs/export-v1.md` de ce dépôt-là, qui fait foi). Il les sert **avec la session Résana de la
personne** : il l'ouvre lui-même à partir des identifiants qu'elle a rangés dans son coffre, double facteur
compris.

Résana a deux portes, et le service passe par les deux avec la même session :

- **les routes du site** (celles qu'appelle la page web) : la liste des espaces, l'arborescence et la
  liste des documents d'un dossier. Elles donnent les numéros (espace, dossier, document) qui
  nomment nos collections et ouvrent les liens « consulter » cités comme sources ;
- **l'API documentaire** d'Interstis, l'éditeur de Résana. Elle n'est pas publique, mais accepte le
  jeton de la session web, et Interstis a accepté que nous l'utilisions. Les **téléchargements**
  passent par elle quand le service connaît l'identifiant du document dans l'API (relevé avec la
  liste) ; sinon, ou si elle ne répond pas, par le site. Le site, saturé, rendait des fichiers vides
  (voir plus bas) ; l'API, mesurée le 2026-10-26, non. Les octets sont les mêmes (vérifié).

Ce que nous savons de cette API vient de [drive-migrator](https://github.com/suitenumerique/drive-migrator),
l'outil de migration Résana → Fichiers de La Suite, et d'un test avec une vraie session le
2026-10-26. Côté service, une veille hebdomadaire signale les changements de drive-migrator
(`resana_client/amont/` d'owuitools-resana).

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
| `GET /espaces/{id}/documents?dossier=&recursif=true` | la liste **complète** du dossier, page par page (`suivant`) ; un curseur expiré (410) relance la lecture une fois ; un grand dossier répond d'abord `202 en_preparation` (voir plus bas) |
| `GET /documents/{id}/fichier?espace=` | les octets d'origine, lus en flux, 100 Mo au plus |

Le moteur d'import et de mise à jour décrit ici sert aussi la source Fichiers (Drive de La Suite
numérique), sous un autre profil : voir `docs/fichiers.md`. Pour Résana, rien ne change.

## Routes de Mes collections

Toutes sont sous `/api/sources/resana` et gardées par la capacité `resana`. Elle est éteinte par défaut :
sans elle, chaque route répond 404 et l'écran ne propose pas Résana.

| Route | Qui | Effet |
|---|---|---|
| `GET /espaces` | toute personne connectée | ses espaces, triés par nom |
| `GET /espaces/{id}/dossiers?recherche=` | toute personne connectée | les dossiers de l'espace |
| `GET /espaces/{id}/apercu?dossier=` | toute personne connectée | le nombre de documents et leur taille approchée ; `202 {en_preparation, dossiers_lus, dossiers}` tant que le service prépare la liste |
| `GET /espaces/{id}/inventaire?dossier=` | toute personne connectée | les sous-dossiers du dossier, avec le nombre de documents de chacun et de son sous-arbre ; 202 pendant la préparation |
| `GET /existant?espace=` | toute personne connectée | ses propres collections Résana déjà ancrées sur cet espace |
| `GET /proposition?espace=&suffixe=` | toute personne connectée | l'identifiant que recevra la collection, et s'il est libre |
| `POST /collections` | toute personne connectée | crée la collection ancrée sur l'espace (identifiant posé par le serveur, privée) et lance l'import, en un appel |
| `POST /add` | la personne qui a **créé** la collection | relie une collection déjà créée à un dossier et lance l'import (ancienne voie, remplacée par `POST /collections`) |
| `POST /sync/{collection}` | la personne qui a importé | relit les dossiers et réindexe ce qui a changé ; avec `{"dossiers": […]}` (et `exclus`), change d'abord la sélection ; `{"complet": true}` retélécharge tout |
| `GET /status/{collection}` | qui peut lire la collection | le dossier relié, la couverture, l'avancement, l'invitation à mettre à jour, `est_importeur` (et, pour lui, la sélection) |

Les erreurs du service sont rendues telles quelles : `{code, message, reessayable}`, plus `url_connexion`
quand la session est absente. Deux exceptions :

- un 401 du service (jeton refusé, ou Mes collections inconnu du service) devient un **502** ; l'écran ne
  déconnecte pas la personne pour une affaire entre deux services ;
- le lien de connexion n'est transmis que s'il est en `https://`.
- **« Se connecter à Résana »** (`composables/useConnexionResana.ts`) : la page de connexion s'ouvre
  dans une fenêtre que Mes collections garde en main ; toutes les 4 s, et dès qu'on revient sur
  l'onglet, la session est testée (`GET /espaces`) ; quand elle répond, la fenêtre est refermée,
  « Connexion à Résana établie » s'affiche, et ce que la personne voulait faire repart tout seul
  (recharger les espaces à l'étape 1, relancer la mise à jour sur la carte). Résana lui-même ne sait
  ni refermer sa fenêtre ni prévenir ; dix minutes sans session et l'attente s'arrête.

## Privée à qui importe, partageable à un groupe

Importer, c'est lire Résana avec ses propres droits. Si la collection s'ouvrait à d'autres, ceux-ci
liraient ce que Résana leur refuse peut-être. La collection naît donc privée, et ne s'ouvre qu'à un
groupe choisi, avec une confirmation explicite :

- **Import** : seulement par la personne qui a créé la collection (`created_by`), dans une collection
  **privée, sans groupe lecteur, vide et non publiée**. L'assistant de création la crée ainsi : à
  l'étape 2, « Qui peut l'interroger ? » est fixé à « Moi seulement ». L'import pose de nouveau la portée
  `private` avant de télécharger quoi que ce soit.
- **Synchronisation** : seulement par la personne qui a importé, avec sa propre session Résana. Un
  administrateur du service ne peut pas le faire à sa place (403 `reserve_a_l_importeur`).
- **Fiche** : `PATCH /api/collections/{nom}` refuse (409) de changer `scope`, `scope_groups`,
  `source_type`, `source_url` ou `source_config_json` d'une collection Résana. Renvoyer la même valeur
  passe. Aucune collection ne devient Résana par sa fiche.
- **Publication** : voir ci-dessous. Un brouillon reste permis sans condition.

### Partager une collection Résana

Décision du 2026-10-24 : les droits viennent du SSO, et le groupe est déclaré par qui gère la
collection. C'est cette personne qui choisit qui la voit ; elle s'assure que chaque membre du groupe a
les bons droits dans Résana : c'est elle qui pilote.

- **Dans le chat MirAI, à un ou plusieurs groupes** (`POST /api/collections/{nom}/publish`,
  `visibility: group` et au moins un groupe ; l'écran les prend un par ligne) ; jamais à tout le
  monde (409).
- **Avec une confirmation** : `droits_resana_confirmes: true`, sinon 409. L'écran la demande par une
  case à cocher, dans « Partager » et à l'étape 5 de l'assistant (`CONFIRMATION_DROITS_RESANA`
  dans `frontend/utils/resana.ts`). Elle explique la conséquence concrète : un membre sans accès
  dans Résana verrait les réponses, mais les liens vers les documents cités ne s'ouvriraient pas
  pour lui.
- **Une trace** : la confirmation est gardée dans l'historique de la publication et dans le journal
  de la collection (`publication.publiee`, avec les groupes).
- **Choisir les groupes** (`components/ChoixGroupes.vue`, à l'étape 5 et dans « Partager ») : ses
  propres groupes cherchés dans une barre de recherche, comme à l'étape 2 (claim `groups` du jeton,
  chemins `/g/…` — `optionsGroupes`), le groupe choisi rangé dessous en puce ; un nom hors liste
  s'ajoute tel quel, et le pont vers **Communauté** (`MYCOLLECTIONS_COMMUNAUTE_URL`, lien
  `/?q=<nom>&creer=1&retour=<page courante>` — keycloak-comu #116 : l'origine de Mes collections doit
  être dans sa liste blanche `ALLOWED_RETURN_ORIGINS`) pour en créer un, puis « Actualiser mes groupes » (renouvellement silencieux du jeton,
  `useAuth().renewToken()`) ou « Se reconnecter ».
- **Ce qui ne change pas** : la fiche et le bac à sable restent privés (portée verrouillée),
  et seule la personne qui a importé synchronise, avec sa session Résana.

Ce qui reste ouvert, comme pour toute collection privée : les administrateurs du service et les membres
du groupe `<racine>/<nom>-admin` la lisent.

## Import et synchronisation

1. La route demande la liste complète du dossier, sans `depuis` : c'est elle qui révèle les suppressions.
   Les erreurs immédiates (session absente, dossier trop gros, service en panne) reviennent à l'écran.
   - **Grand dossier.** Au-delà de 40 sous-dossiers, le service prépare la liste en arrière-plan : un
     appel Résana par dossier, à 5 par seconde. Sur un dossier réel de 1 361 sous-dossiers, la
     préparation a pris 4 min 30. Le service répond `202 en_preparation` avec `dossiers_lus`, `dossiers`
     et `Retry-After`.
     - L'aperçu le rend tel quel, et l'écran rappelle toutes les 5 s en affichant « n dossiers lus
       sur N ».
     - L'import et la synchronisation n'attendent pas : la tâche de fond rappelle la même adresse au
       rythme de `Retry-After`, 20 minutes au plus, puis télécharge.
     - Une fois prête, la liste reste 10 minutes en cache chez le service.
   - **Synchronisation sur un dossier vide.** Elle est refusée (409 `dossier_vide`) : rien n'est
     retiré sur la foi d'une liste vide.
2. **Mes collections ne garde aucune copie des documents Résana.** Pour chaque document, il garde
   une fiche de quelques centaines d'octets :
   - son empreinte sha256 ;
   - la date de modification et la version annoncées par Résana (`modifie_le`, `version_fichier`) ;
   - son adresse de consultation ;
   - **son identifiant chez OpenRAG**.

   L'original reste dans Résana, le texte indexé chez OpenRAG.
3. **Ce que la liste suffit à dire.** Sans rien télécharger, chaque document est classé ainsi :
   - **nouveau** : à télécharger ;
   - **date ou version annoncée différente** : à télécharger, puis à comparer par empreinte ;
   - **même date, même version** : inchangé, rien n'est téléchargé ;
   - **absent de la liste** : disparu.

   Une mise à jour où dix documents ont bougé télécharge ces dix-là, pas tout le dossier. Le
   service ne garantit pas que la version change à chaque modification. Pour le cas rare d'un
   contenu changé sans nouvelle date, **« Vérification complète »** (`{"complet": true}`)
   retélécharge tout et compare les empreintes.
4. **Le téléchargement**, en tâche de fond, quatre documents à la fois. Le jeton de la personne reste
   en mémoire le temps de la tâche et n'est jamais écrit. L'écran suit l'avancement par `/status`.
   - **Le jeton reste frais tant que la page est ouverte.** Le jeton de départ vit 15 minutes, mais
     la page de l'importeur lit l'état toutes les 3 secondes avec son jeton renouvelé, et la route
     `/status` le transmet à la tâche en cours (`relayer_jeton`). Un téléchargement peut donc durer
     des heures, pourvu que la page reste ouverte. Seul l'importeur relaie son jeton, et le jeton
     n'est ni écrit ni journalisé.
   - Page fermée : la tâche continue jusqu'à l'expiration de son dernier jeton, puis s'arrête en
     « partiel » ; « Mettre à jour » reprend là où elle s'est arrêtée.
   - Un contenu relu à l'identique est jeté aussitôt.
   - Un contenu nouveau ou changé attend dans un **dossier d'attente sur le disque**
     (`<DATA_DIR>/_resana_attente/<collection>`), jamais en mémoire, le temps de partir chez
     OpenRAG. Il est effacé dès son envoi, et le dossier est vidé au début et à la fin de chaque
     passe.
   - Pas de plafond par passe. Seule garde : laisser au moins 1 Go libre sur le volume.
5. **Le tri** :
   - un format non pris en charge est écarté ;
   - **un fichier reçu vide n'est pas un document** : Résana saturé répond 200 sans corps (mesuré le
     2026-10-25 : par à-coups au-delà de ~6 téléchargements par seconde, puis deux minutes où tout
     arrivait vide, d'où 341 documents écartés à tort sur 783). Le fichier est redemandé après 5 puis
     20 s (`PAUSES_FICHIER_VIDE`) ; toujours vide, il est signalé (`fichier_vide`) sans être mémorisé,
     donc redemandé à la passe suivante ; s'il était déjà indexé, il **garde sa version** (le
     2026-10-25, une mise à jour complète pendant la saturation en a retiré 328 de l'index). Huit vides d'affilée (`VIDES_DE_SUITE_MAX`) : Résana est
     saturé, la passe s'arrête en « partiel » (`resana_sature`) au lieu d'écarter tout le reste du
     dossier, et « Mettre à jour » la reprend ;
   - un document refusé par Résana (`hors_droits`, `introuvable`, `trop_volumineux`) est écarté, et
     retiré s'il avait été importé ;
   - **les doublons** : voir ci-dessous.

   **Doublons dans une collection.** Personne n'est bloqué : un contenu identique n'est simplement
   indexé qu'une fois. Ce qui ne l'est pas : les doublons entre collections, et les quasi-doublons
   (une v1 et une v2, un Word et son PDF). L'empreinte (sha256) ne voit que l'identique.
   - **Qui garde la place** : le premier document gardé porte le contenu. Les autres sont écartés,
     avec la raison « même contenu que « … » », et restent visibles dans « Documents écartés ».
   - **Stabilité** : face à un nouveau doublon, le document déjà indexé garde sa place, même si
     Résana rend la liste dans un autre ordre. Rien n'est retiré puis renvoyé pour rien.
   - **Mémoire des écartés** (`source_config_json.ecartes`) : un doublon ou un format refusé est noté
     avec la version annoncée par Résana, et n'est **pas retéléchargé** tant qu'elle ne change pas.
     Un refus de Résana (`hors_droits`, `introuvable`, `trop_volumineux`) n'est pas mémorisé : il est
     retenté à chaque passe (un refus coûte une requête, et des droits accordés sont repris d'eux-mêmes).
     Un écart noté avec l'empreinte d'un contenu vide (avant ce correctif, il passait pour un « format
     non pris en charge » ou un « document vide ») est retéléchargé : c'était un téléchargement raté.
   - **Ce qu'un écart dit** : un `code` stable (`hors_droits`, `introuvable`, `trop_volumineux`,
     `fichier_vide`, `format`, `conversion`, `illisible`, `vide`, `doublon`, `autre` — `app/services/resana_ecarts.py`,
     miroir dans `frontend/utils/resana.ts`), la raison en texte, le dossier Résana et l'adresse de
     consultation. La carte regroupe les écartés par code, avec l'explication et « quoi faire », et chaque
     titre ouvre le document dans Résana. Elle n'en reçoit que les `ECARTES_MAX` (50) premiers ;
     `GET /api/sources/resana/ecartes/{c}?format=csv|json` (lecture de la collection) donne la liste
     entière : les écarts mémorisés plus les refus de la dernière passe, avec, pour un doublon, le titre de
     l'original. Le CSV est fait pour un tableur (UTF-8 avec BOM, `;`, cellules neutralisées).
   - **Relais** : si l'original change ou disparaît, son doublon est relu, et il porte alors le
     contenu : rien ne sort de l'index.
   - **Fin du doublon** : un doublon qui change redevient un document à part entière.
   - **Erreurs de lecture d'OpenRAG** :
     - passagères (délai dépassé, service indisponible) : le document est renvoyé à la passe
       suivante, l'essai raté étant retiré d'abord — sauf si l'indexeur l'a lu entre-temps (une
       file longue le lit après les 30 minutes de suivi) : la passe suivante le lui demande
       d'abord (`qualites`) et le garde tel quel, sans le remettre au bout de la file ;
     - définitives (« n'a pas pu lire » : PDF sans texte) : le document n'est retenté que s'il
       change.
6. **OpenRAG, document par document** (par l'interface de l'indexeur, `docs/indexeur.md`). La partition n'est jamais vidée, et la recherche continue
   pendant la mise à jour.
   - L'ancienne version d'un document modifié et les documents disparus sont retirés un par un
     (`DELETE /indexer/partition/<p>/file/<id>`).
   - Les nouveaux documents et les nouvelles versions sont envoyés entiers : OpenRAG les lit et les
     découpe. Métadonnées jointes : le titre Résana (`title`), la langue (`language: fr`, pour que
     le contexte de chaque passage soit rédigé en français), l'adresse Résana (`url`), l'espace, le
     dossier et la sensibilité.
   - Les envois partent **quatre à la fois** par défaut, chacun suivi jusqu'au bout (un travail par
     document) : des centaines de PDF envoyés d'un coup dépassaient le délai de lecture d'OpenRAG.
     Le nombre se règle (`MYCOLLECTIONS_RESANA_ENVOIS_PARALLELES`, de 1 à 16).
   - **Le débit est mesuré** dans l'état du travail : `indexation_s`, `debit_docs_min`,
     `envois_paralleles`. Repère sur un import réel de 2 093 documents à 4 envois : ≈ 10 documents
     par minute sur l'ensemble (17 au début). L'essentiel du temps se passe chez l'indexeur
     (extraction, contexte de chaque passage et description des images par des modèles, vecteurs).
   - **Ne pas monter les envois tant que la passerelle de modèles refuse** : sur cet import, 93 % des
     passages ont perdu leur contexte, refusé par le quota de la passerelle (429), que l'indexeur
     partage avec le chat. Plus d'envois simultanés, c'est plus de refus, pas plus de débit utile.
     Voir le chantier #143.
   - **La lecture de chaque document est suivie** chaque seconde pendant 15 s, puis toutes les 2 s
     jusqu'à une minute, puis toutes les 3 s (`ingest.pause_de_suivi`). Un envoi ne reste plus
     inoccupé après la fin d'un document.
   - **Identifiant stable** : l'identifiant OpenRAG d'un document se déduit du document Résana et de
     son empreinte (`resana-<id>-<sha>`). Un renvoi après une coupure retombe sur le même fichier
     (OpenRAG répond 409, compté comme reçu), au lieu d'en créer un second.
   - Si rien n'a changé, la synchronisation le dit (« à jour ») et ne touche pas à l'index.
7. **Arrêt en route.** Une erreur bloquante arrête le téléchargement : session perdue, jeton expiré
   (le jeton d'accès vit quelques minutes), service indisponible, ou disque presque plein
   (`disque_plein`).
   - **Aucun document reçu** : l'état passe à « échec », avec le message et, s'il y a lieu, le lien de
     connexion.
   - **Des documents reçus** : l'état passe à « partiel ».
     - Ce qui est arrivé est indexé.
     - **Rien n'est retiré.** Les documents non relus gardent leur fiche, donc leur ancienne date :
       la passe suivante les relira.
     - La date de dernière lecture ne bouge pas.
     - Les nouveaux documents sont téléchargés en premier.

**Réindexer** (changer le découpage) ne s'applique pas à une collection Résana : il n'y a pas de copie
à redécouper (409). On passe par « Vérification complète », qui relit Résana. Pour les PDF et les
documents bureautiques, c'est de toute façon OpenRAG qui découpe.

Les noms de fichiers viennent du service (`Content-Disposition`). Deux documents de même nom sont
distingués par l'identifiant Résana : `note (1234).pdf`. Un nom donné à l'import ne change plus, sauf
pour réparer des accents mal décodés en route (« RÃ©ponse » devient « Réponse » :
`reparer_accents`, owuitools-resana#7).

`source_config_json` garde :

- l'espace et le dossier (identifiant et libellé) ;
- pour chaque document : son sha256, son nom de fichier, son adresse de consultation, sa date et sa
  version annoncées, son identifiant OpenRAG (et l'erreur de lecture d'OpenRAG s'il y en a eu une) ;
- la date de la dernière lecture ;
- l'état du dernier travail.

Cette configuration ne sort que par `/status`, et sans la liste des documents.

L'adresse de consultation Résana (`url_consultation`, donnée par le service, jamais construite ici) est
gardée comme adresse d'origine de chaque fichier, et envoyée à OpenRAG en métadonnée `url`. OpenRAG
fait déjà pointer ses liens de source vers cette adresse quand elle existe. Les citations du bac à
sable de Mes collections passent encore par l'extrait OpenRAG.

### Ce que vaut l'index, et « Ré-indexer les documents incomplets »

Chaque document garde sa **qualité** (`documents[id].qualite`, voir `docs/indexeur.md`), et `/status`
la compte : `qualite.par_etat` (`complet`, `sans_contexte`, `degrade`, `sans_texte`, `echec`,
`inconnue` pour un document indexé avant ce suivi), `qualite.a_reprendre`, et le nombre de passages
sans contexte quand l'indexeur le donne. La carte de la collection l'écrit en phrases. Pour les
scans, elle conseille de déposer plutôt la version électronique, de préférence non signée.

`POST /sync/{collection}` avec `{"incomplets": true}` renvoie les documents `sans_contexte`,
`degrade` et `sans_texte` **même inchangés dans Résana** : après une panne de quota, ou quand l'OCR
arrive pour les scans. Les autres documents restent en place. Le travail s'appelle alors
`reindexation`. Un format refusé (`echec`) n'est pas renvoyé : il échouerait à l'identique.

`POST /qualite/{collection}` (bouton « Relire le bilan auprès du moteur », pour qui gère la
collection) **relit la qualité auprès de l'indexeur**, sans rien renvoyer ni passer par Résana :
après une ré-indexation faite côté indexeur, ou pour une collection importée avant ce suivi. Un
scan noté sans texte le reste tant que l'indexeur ne dit pas l'avoir lu par OCR.

### Ce que Résana dit, et ce qu'il ne faut pas en conclure

- **La taille** d'un document n'est connue qu'arrondie : en Mo à deux décimales sur le site
  (`taille_approx_mo`), au centième de Mio dans l'API. Un fichier de moins de 5 Ko environ est
  annoncé à 0. Elle ne sert jamais à juger un fichier vide ni un téléchargement complet : c'est le
  contenu reçu (et son sha256) qui décide.
- **Les espaces figés** (archivés) manquent à la liste habituelle des espaces. Le service les
  ajoute, marqués `archive: true`, et ils s'importent comme les autres.
- **Les dossiers à accès restreint** existent : l'API donne, pour chaque dossier, s'il est ouvert à
  tous les membres ou réservé à une liste de personnes ou de groupes (`lockStatus`). Une collection
  qui inclut de tels dossiers contient des documents que tous les membres de l'espace ne voient pas.
  C'est à garder en tête au moment de la partager à un groupe ; l'écran ne le signale pas encore.

## Une collection ancrée sur un espace

Une collection Résana est ancrée sur **un espace**. Les dossiers à indexer sont un **réglage
d'indexation** (le périmètre), modifiable à tout moment. Ajouter ou retirer un dossier ne change
ni le nom ni le titre de la collection.

### L'identifiant : `resana-<numéro de l'espace>`

- **Le serveur seul le pose** (`POST /collections`). L'écran l'affiche en lecture seule, avec sa
  raison.
- **Le numéro de l'espace est la seule clé unique dans Résana.** Le nom ne l'est pas : chaque
  entité peut avoir ses « Instances de gouvernance régionale ».
- **Une seconde collection sur le même espace** demande un suffixe d'usage :
  `resana-206379-car`. L'écran le demande quand l'identifiant est pris.
- **Le préfixe `resana-` est réservé.** Une création manuelle le refuse (422, motif `resana`), même
  pour adopter une partition existante. Il reste ainsi un marqueur fiable, jusque dans les
  partitions de l'indexeur.
- **En preview**, l'identifiant suit le préfixe imposé : `<préfixe>resana-<numéro>`.

### La fiche d'identité de l'espace

Le service d'export donne, quand il les a, `description`, `objet`, `cree_le` et `parent_id`
(l'espace parent). Mes collections les garde dans `source_config_json.espace`, avec :

- **l'entité administrative**, saisie par la personne. Résana ne la donne pas. Le champ est
  facultatif, avec un exemple grisé (« ex. Préfecture de la région Bretagne »). Elle sert à
  distinguer plus tard des espaces de même nom d'une entité à l'autre ;
- **une description par défaut**, posée si la personne n'en écrit pas : « Espace Résana « nom »
  (n° 206379), entité. ».

À la fin d'un import ou d'une mise à jour, **l'adresse commune des documents** (préfixe de leurs
`url_consultation`, `sources_url.prefixe_commun`) devient la **source de la collection**
(`source_url`, affichée sur la fiche, verrouillée dans les réglages) et un **site déclaré** pour MirAI
Assistant pour navigateur (`docs/clients.md`), ajouté sans toucher aux motifs saisis à la main.
Les collections importées avant sont rattrapées au démarrage (`migration_sites_resana`), une fois,
sans écraser une source saisie ni un site déclaré à la main.

Chaque document envoyé à l'indexeur porte aussi son origine : `source: resana`, l'espace, le
chemin de son dossier et l'adresse de consultation, ainsi que la sensibilité de la collection
(`sensitivity`).

### La sensibilité : « Interne » d'emblée

Un espace Résana est un espace de travail entre agents : sa collection naît **« Interne »**
(`POST /collections`). La page « Gérer les documents » la montre et la change ; le changement
s'enregistre aussitôt dans la fiche et vaut pour les documents envoyés à partir de la mise à jour
suivante (ceux déjà indexés gardent la leur jusqu'à leur prochain envoi).

Les collections Résana créées avant ce défaut étaient en « public » : le démarrage les passe à
« internal », **une seule fois** (`database._resana_interne`). L'événement
`sensibilite.resana_interne`, écrit au journal de la collection, empêche de rejouer : un « Public —
internet » choisi ensuite par qui la gère est respecté.

La liste vaut pour toutes les collections (`Sensitivity` dans `app/services/chunker.py`, libellés
dans `frontend/utils/libelles.ts`) :

| Valeur | Libellé |
|---|---|
| `public` | Public — internet |
| `internal` | Interne |
| `personal` | Données personnelles |
| `personal_sensitive` | Données personnelles sensibles |
| `controlled` | Diffusion contrôlée |
| `restricted` | Diffusion restreinte |

- **Les anciennes valeurs** `confidential` et `secret` deviennent `restricted`, le niveau le plus
  protecteur : un document n'est jamais rangé moins protégé qu'avant. Le démarrage les réécrit
  dans les collections et les travaux d'indexation ; l'API les accepte encore en entrée.
- **Une valeur inconnue est refusée** (422) à la création et dans la fiche.
- **Tout document indexé porte une sensibilité** : celle de la collection, par défaut. La changer
  document par document, et faire suivre le changement à l'indexeur, est l'objet de #139.
- **La sensibilité ne change encore aucun droit.** Ce qu'un niveau interdit (publication dans
  le chat MirAI, partage hors de la collection) reste à décider.

## Écrans

1. **L'espace**, dans une **liste déroulante riche** (`components/ListeDeroulanteRiche.vue`).
   - On tape une partie du nom, de l'objet ou de la description ; les accents et la casse sont
     ignorés, et chaque mot doit figurer.
   - Chaque espace montre son objet en gris, ce qui départage des homonymes.
   - Le composant suit la maquette DSFR « Liste déroulante riche », en bêta et pas encore publiée
     en code, et le motif « combobox » du W3C. Clavier : les flèches pour parcourir, Entrée pour
     choisir, Échap pour fermer, Tab pour quitter.
   - À remplacer par le composant du DSFR le jour où il existe en code.
   - Si une de vos collections est déjà ancrée sur cet espace, l'écran le dit et propose d'y
     ajouter des dossiers plutôt que d'en créer une autre (`GET /existant?espace=`). Seules vos
     collections apparaissent : une collection Résana est privée.
2. **Les dossiers** (composant `DepotDossiersResana`) : l'arbre de l'espace, avec une case par
   dossier et une recherche qui garde le chemin des dossiers trouvés.
   - Un dossier coché emporte ses sous-dossiers, qui apparaissent cochés et grisés.
   - Sous l'arbre, les dossiers choisis, chacun avec son nombre de documents, ou « préparation
     chez Résana… » pour un grand dossier ; puis le total.
   - Un texte rappelle de n'indexer que ce qui sert.
   - Une alerte, dès l'étape 1, rappelle que Mes collections lit Résana avec les droits de la personne :
     seuls les documents qu'elle peut ouvrir sont indexés, les autres sont écartés et listés.
3. **La fiche** :
   - le titre (le nom de l'espace, modifiable) ;
   - l'entité administrative ;
   - la description (aperçu de celle par défaut) ;
   - l'identifiant expliqué, et le suffixe s'il est pris ;
   - les étiquettes Résana et Privée.

   « Créer et indexer » fait **un seul appel** (`POST /collections`) : identifiant, collection
   privée, import.
4. **Suivre l'indexation** (étape 3 de l'assistant, `admin/create/resana?collection=<id>`) : la
   carte de la collection et sa sensibilité. L'indexation continue en arrière-plan ; « Étape
   suivante » mène à la vérification des réponses (étape 4), puis à l'étape 5 : un récapitulatif
   (ce qui a été fait, ce qui reste à faire — `resumeCreation`), un **guide de démarrage** à garder
   (`/c/<id>/guide-de-demarrage`, page imprimable), et le partage à un ou plusieurs groupes avec la
   confirmation des droits Résana. Les étapes 4 et 5 gardent
   `source=resana` dans l'adresse (`lienEtape` dans `frontend/utils/wizard.ts`). L'adresse porte
   la collection : un rechargement ou un retour depuis l'étape 4 rouvre l'étape 3.

**Page « Gérer les documents »** (`/c/<id>/upload`) : la carte ci-dessous et la sensibilité,
sans dépôt de fichiers ni choix du découpage. Une collection Résana se remplit par sa sélection
de dossiers, et c'est l'indexeur qui découpe ; un fichier déposé à la main se mêlerait à l'index
Résana sans source ni mise à jour.

**Page de la collection** (`DepotEtatResana`) :
- l'espace, son entité et les dossiers inclus ;
- les documents écartés, groupés par raison, avec « quoi faire », un lien vers chaque document dans
  Résana et « Exporter la liste (CSV) » ;
- la couverture, l'avancement et l'invitation à mettre à jour ;
- les gestes, en deux zones titrées, chacune avec une aide visible : **« Tenir l'index à jour »**
  (« Mettre à jour », « Ré-indexer les documents incomplets (N) », « Relire le bilan auprès du
  moteur », « Tout revérifier » — l'ancienne « Vérification complète ») et **« Changer ce qui est
  indexé »** (« Modifier la sélection »). À l'étape 3 de l'assistant (`compact`), juste après
  l'import, seule la seconde zone s'affiche ;
- **« Modifier la sélection »**, qui rouvre l'arbre avec les dossiers déjà choisis dépliés.
  L'enregistrer remplace la liste des dossiers (`POST /sync/{c}` avec `dossiers`) : un dossier
  ajouté s'indexe, un dossier retiré sort de l'index. Le journal de la collection garde le
  changement (`perimetre.modifie`, avec les dossiers ajoutés et retirés).

**Mes collections** : l'étiquette « Résana · index complet / partiel ».

## Périmètre et couverture

- **Le périmètre** (`source_config_json.perimetre`) :
  - `dossiers` : les dossiers inclus (identifiant, chemin), chacun avec son sous-arbre ;
  - `exclus` : des sous-dossiers exclus. L'écran ne les pose plus (il coche ce qu'il faut inclure),
    mais une collection d'avant les garde, et ils restent appliqués.
- **La liste des documents** se lit dossier par dossier, puisque le service n'indexe pas un espace
  entier. Les documents sont réunis sans doublon.
- **Les configurations d'avant** (un seul `dossier_id`) se lisent comme une liste d'un dossier.

La **couverture** (`source_resume` dans la fiche, et dans `/status`) :

| Champ | Sens |
|---|---|
| `couverture` | `totale` ou `partielle` |
| `raisons` | `selection` (des sous-dossiers exclus), `interrompue` (passe arrêtée en route), `a_faire` (rien d'indexé), `erreurs_de_lecture` (le moteur n'a pas su lire certains documents) |
| `espace_nom`, `entite`, `nb_dossiers` | de quoi situer la collection dans une liste |
| `documents_indexes`, `documents_perimetre`, `documents_disponibles` | comptes |
| `derniere_lecture` | date de la dernière passe complète |

## Inviter à mettre à jour

Pas de synchronisation planifiée (elle demanderait d'agir sans la personne : issue « qui peut relancer
l'indexation »). À la place, l'outil **propose** une mise à jour là où la personne se trouve, quand
c'est utile :

- index lu il y a plus de `MYCOLLECTIONS_RESANA_FRAICHEUR_JOURS` jours (7 par défaut) : « L'index
  Résana de « Notes fictives » semble ancien (dernière lecture il y a 12 jours). Souhaitez-vous le
  mettre à jour ? » ;
- dernière passe arrêtée en route ou en échec (premier import raté compris) : « L'index Résana de
  « Notes fictives » est incomplet : la dernière mise à jour n'est pas allée au bout. Souhaitez-vous
  la reprendre ? ».

Seulement pour la personne qui a importé (elle seule peut mettre à jour), et jamais pendant une
passe. L'invitation apparaît :

- **sous une réponse du bac à sable** (champ `avis` de `POST /api/playground/{c}/chat`) ;
- **dans la recherche** (`GET /api/v1/search`) : clé `notices`, absente s'il n'y en a pas, lue par
  MirAI Assistant pour navigateur (docs/clients.md) ;
- **sur la page de la collection**.

Le lien d'action ouvre la page de la collection (`/c/<nom>/upload?synchroniser=1`), où le bouton
« Mettre à jour » reçoit le focus : rien ne se lance sans un clic.

## Configuration

| Variable | Défaut | Rôle |
|---|---|---|
| `MYCOLLECTIONS_RESANA_EXPORT_URL` | `` | adresse interne du service d'export (sans `/export/v1`) ; vide ⇒ 503 |
| `MYCOLLECTIONS_RESANA_EXPORT_SECRET` | `` | secret propre à Mes collections, attendu par le service dans `X-Internal-Token` ; vide ⇒ 503 |
| `MYCOLLECTIONS_RESANA_FRAICHEUR_JOURS` | `7` | au-delà, l'index « semble ancien » et l'outil propose de le mettre à jour |
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
  - la carte qui suit la capacité ;
  - la page « Gérer les documents », sans dépôt manuel.
- `myrag/tests/unit/test_sensibilite.py` teste la liste des sensibilités, la reprise des anciennes
  valeurs et le refus d'une valeur inconnue ; `test_resana_perimetre.py`, la sensibilité
  « Interne » d'une collection Résana et sa métadonnée.
