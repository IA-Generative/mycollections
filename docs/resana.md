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
| `GET /espaces/{id}/documents?dossier=&recursif=true` | la liste **complète** du dossier, page par page (`suivant`) ; un curseur expiré (410) relance la lecture une fois ; un grand dossier répond d'abord `202 en_preparation` (voir plus bas) |
| `GET /documents/{id}/fichier?espace=` | les octets d'origine, lus en flux, 100 Mo au plus |

## Routes de Mes collections

Toutes sont sous `/api/sources/resana` et gardées par la capacité `resana`. Elle est éteinte par défaut :
sans elle, chaque route répond 404 et l'écran ne propose pas Résana.

| Route | Qui | Effet |
|---|---|---|
| `GET /espaces` | toute personne connectée | ses espaces, triés par nom |
| `GET /espaces/{id}/dossiers?recherche=` | toute personne connectée | les dossiers de l'espace |
| `GET /espaces/{id}/apercu?dossier=` | toute personne connectée | le nombre de documents et leur taille approchée ; `202 {en_preparation, dossiers_lus, dossiers}` tant que le service prépare la liste |
| `GET /espaces/{id}/inventaire?dossier=` | toute personne connectée | les sous-dossiers du dossier, avec le nombre de documents de chacun et de son sous-arbre ; 202 pendant la préparation |
| `GET /existant?espace=&dossier=&chemin=` | toute personne connectée | ses propres collections Résana qui indexent déjà ce dossier, un parent ou un sous-dossier |
| `POST /add` | la personne qui a **créé** la collection | relie la collection au dossier (`exclus` : les sous-dossiers à ne pas indexer) et lance l'import |
| `POST /sync/{collection}` | la personne qui a importé | relit le dossier et réindexe s'il a changé ; avec `{"exclus": […]}`, change d'abord la sélection |
| `GET /status/{collection}` | qui peut lire la collection | le dossier relié, la couverture, l'avancement, l'invitation à mettre à jour, `est_importeur` (et, pour lui, la sélection) |

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
   - Un contenu relu à l'identique est jeté aussitôt.
   - Un contenu nouveau ou changé attend dans un **dossier d'attente sur le disque**
     (`<DATA_DIR>/_resana_attente/<collection>`), jamais en mémoire, le temps de partir chez
     OpenRAG. Il est effacé dès son envoi, et le dossier est vidé au début et à la fin de chaque
     passe.
   - Pas de plafond par passe. Seule garde : laisser au moins 1 Go libre sur le volume.
5. **Le tri** :
   - un contenu déjà vu sous un autre document est écarté (doublon) ;
   - un format non pris en charge est écarté ;
   - un document refusé par Résana (`hors_droits`, `introuvable`, `trop_volumineux`) est écarté, et
     retiré s'il avait été importé.
6. **OpenRAG, document par document.** La partition n'est jamais vidée, et la recherche continue
   pendant la mise à jour.
   - L'ancienne version d'un document modifié et les documents disparus sont retirés un par un
     (`DELETE /indexer/partition/<p>/file/<id>`).
   - Les nouveaux documents et les nouvelles versions sont envoyés entiers : OpenRAG les lit et les
     découpe. L'adresse Résana est jointe en métadonnée `url`.
   - Les envois partent **quatre à la fois**, chacun suivi jusqu'au bout (un travail par document) :
     des centaines de PDF envoyés d'un coup dépassaient le délai de lecture d'OpenRAG.
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
distingués par l'identifiant Résana : `note (1234).pdf`. Un nom donné à l'import ne change plus.

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

## Écrans : Résana d'abord

On part de Résana : la personne choisit ce qu'elle veut indexer, l'outil construit la collection
autour (`pages/admin/create/resana.vue`).

1. **Choisir dans Résana** (la carte « Un dossier Résana » de l'étape 1, visible si la capacité est
   allumée).
   - L'espace. La première ouverture de session peut prendre une minute et demie, et un message le dit.
     Sans session Résana, un avertissement donne le lien de connexion du service et « Réessayer ».
   - Le dossier, avec un filtre. Pour tout l'espace, on prend son dossier principal.
   - **L'existant**, vérifié aussitôt (`GET /existant`) : si une de vos collections indexe déjà ce
     dossier, un dossier qui le contient ou un de ses sous-dossiers, l'écran le dit, avec le lien
     pour la mettre à jour plutôt que d'en créer une de plus. Seulement les vôtres : une collection
     Résana est privée, celles des autres ne se révèlent pas.
   - **Que faut-il indexer ?** (`GET /inventaire`, composant `DepotArbreResana`) : les sous-dossiers en
     arbre, avec le nombre de documents (et la taille approchée) de chacun, cochés par défaut. Un
     texte rappelle de n'indexer que ce qui sert : chaque document de plus allonge l'import et les
     mises à jour, et peut mêler aux réponses des textes hors sujet. Le total de la sélection se met
     à jour à chaque case. Pendant la préparation d'un grand dossier, l'écran affiche « n dossiers
     lus sur N » ; on peut continuer sans attendre (tout le dossier sera indexé).
2. **Relire la fiche**, déjà remplie : titre (le nom du dossier), identifiant proposé, description
   (« Les documents du dossier … de l'espace Résana … »), et les étiquettes **Résana**,
   **Index complet / partiel**, **Privée**. « Créer et indexer » crée la collection (privée) et lance
   l'import, puis ouvre la page de la collection. Si l'import ne démarre pas, la collection reste et
   le bouton devient « Relancer l'indexation ».

**Page « Ajouter des documents »** d'une collection Résana (`DepotEtatResana`) :
- le badge **Résana · index complet** ou **Résana · index partiel**, et la phrase qui l'explique
  (« 412 documents indexés sur 2 141 dans le dossier Résana : index partiel (certains sous-dossiers
  sont exclus) ») ;
- l'avancement, les documents écartés, et l'invitation à mettre à jour si l'index vieillit ;
- pour la personne qui a importé : **Mettre à jour**, et **Modifier la sélection**. Ce bouton rouvre
  l'arbre avec les dossiers exclus décochés. « Enregistrer et mettre à jour » applique la sélection :
  un dossier ajouté s'indexe, un dossier retiré sort de l'index. C'est ainsi qu'on **poursuit une
  indexation partielle**.

**Mes collections** : l'étiquette « Résana · index complet / partiel » sur la carte de la collection.

## Périmètre et couverture

Le périmètre s'écrit en **exclusions** (`source_config_json.perimetre.exclus`) : le dossier choisi
est indexé, sauf les sous-dossiers exclus et tout ce qu'ils contiennent. Un sous-dossier créé plus
tard dans Résana entre donc de lui-même dans l'index, sauf s'il est rangé sous un dossier exclu. Les
documents rangés directement dans le dossier choisi sont toujours indexés.

La **couverture** (`source_resume` dans la fiche d'une collection, et dans `/status`) dit ce que
l'index couvre du dossier :

| Champ | Sens |
|---|---|
| `couverture` | `totale` ou `partielle` |
| `raisons` | `selection` (des sous-dossiers exclus), `interrompue` (la dernière passe s'est arrêtée en route), `a_faire` (rien d'indexé encore) |
| `documents_indexes` | documents dans l'index |
| `documents_perimetre` | documents de la sélection lors de la dernière passe |
| `documents_disponibles` | documents du dossier Résana (sous-dossiers exclus compris) |
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
  l'extension IAssistant-Direct (docs/clients.md) ;
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
  - la carte qui suit la capacité.
