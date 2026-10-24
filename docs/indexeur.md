# L'indexeur : le moteur qui reçoit les documents

Mes collections confie les documents entiers (PDF, Word, tableurs…) à un **indexeur**. L'indexeur
les lit, les découpe et les rend cherchables. Aujourd'hui, c'est OpenRAG. Les sources ne parlent
qu'à l'interface `app/services/indexeur.py`, jamais à OpenRAG directement : le dépôt d'un document
et l'import Résana (`docs/resana.md`). Changer de moteur, c'est écrire un autre indexeur. Ce n'est
pas réécrire les sources.

## Ce que Mes collections attend d'un indexeur

| Geste | Sens |
|---|---|
| `preparer(collection)` | l'espace qui accueille les documents de la collection existe |
| `envoyer(collection, nom, contenu, mime=, metadata=, identifiant=)` | confier un document entier, sous un identifiant choisi par Mes collections ; rend `Envoi(identifiant, tache)` |
| `suivre(tache)` | où en est la lecture : `en_cours`, `lu`, ou `echec` avec sa raison ; une fois lu, `qualite` dit ce que vaut l'indexation (voir plus bas) |
| `retirer(collection, identifiant)` | le document sort de l'index ; un document absent n'est pas une erreur |
| `vider(collection)` | toute la collection sort de l'index |

Deux exceptions :

- `DejaPresent` : l'identifiant est déjà indexé, après un renvoi qui suit une coupure. Le dépôt le
  compte comme réussi.
- `Refuse(statut)` : le moteur refuse le document, pour une question de format ou de taille.

Les métadonnées envoyées sont :

- le titre (`title`) : le nom du fichier, ou, pour Résana, le titre du document dans Résana ;
- la langue (`language`, `fr` par défaut). L'indexeur rédige dans cette langue le contexte de chaque
  passage ; sans elle, OpenRAG l'écrit en anglais ;
- pour Résana, l'adresse du document d'origine (`url`), l'espace, le dossier et la sensibilité.

## La qualité d'un document indexé

Lu ne veut pas dire bien indexé. Sur un import réel (2026-10-24), 93 % des passages ont perdu leur
contexte (quota de la passerelle de modèles) et 21 % des PDF étaient des scans sans texte, sans
que rien ne le signale. `suivre` rend donc aussi la **qualité** (`indexeur.qualite_lecture`) :

| État | Sens |
|---|---|
| `complet` | lu, chaque passage a son contexte |
| `sans_contexte` | lu, mais une part des passages n'a pas le contexte écrit par le modèle |
| `degrade` | lu, mais une étape d'enrichissement a échoué (description des images…) |
| `sans_texte` | rien à indexer : un scan, le plus souvent (`NO_INDEXABLE_CONTENT`) |
| `echec` | non lu, pour une autre raison (format refusé…) |

OpenRAG 2.3 le dit dans le statut de tâche : `degraded_stages`, et, depuis la 2.3.2-2,
`contextualization` (`total`, `failed`) ; avec le repli OCR (#152), `parse_backend`, `ocr` et
`ocr_failed_pages`, gardés dans la qualité (`ocr`, `pages_perdues` ; des pages perdues font un état
`degrade`, étape `parse`). Un indexeur qui ne dit rien rend `qualite = None` : on ne
sait pas. Un dépôt manuel dégradé réussit, et son travail dit ce qui manque. Une collection Résana
garde la qualité de chaque document, la compte (`/status` → `qualite`) et sait renvoyer les seuls
documents incomplets (`docs/resana.md`).

### Les scans

Un PDF sans texte lisible (moins de 30 caractères par page sur ses 10 premières pages,
`formats.est_un_scan`) est **repéré avant l'envoi et envoyé quand même**, avec la métadonnée
`scan: true` : l'indexeur le lit s'il a la reconnaissance de caractères (OCR), sinon il le refuse
(`sans_texte`). Dans ce cas, le travail ajoute le conseil de déposer la version électronique, de
préférence non signée. Une collection Résana garde `scan` par document et compte les scans repérés
et ceux que l'OCR a lus (`qualite.scans`, `qualite.scans_lus`). `scripts/marquer_scans.py` marque
les scans indexés avant ce repérage, d'après la liste que rend leur relecture.

### Les formats bureautiques que l'indexeur ne lit pas

OpenRAG ne lit ni `.odt`, `.odp`, `.ods`, ni `.ppt`, `.xls`, `.xlsx`, `.rtf`. Ce sont pourtant des
formats courants dans l'administration. Quand `MYCOLLECTIONS_CONVERSION_URL` désigne un service
**Gotenberg** (route LibreOffice, `myrag/k8s/deployment-conversion.yaml`), Mes collections les
convertit en PDF avant l'envoi (`app/services/conversion.py`) :

- le fichier part sous le nom `budget (ods).pdf`, avec la métadonnée `converti_depuis` ;
- l'empreinte gardée reste celle de l'original : c'est lui dont on suit les versions ;
- une conversion à la fois, avec un délai borné (`MYCOLLECTIONS_CONVERSION_DELAI_S`). Un échec écarte
  le document avec sa raison, sans bloquer les autres ;
- un document Résana écarté pour son format est retenté à la mise à jour suivante, dès que le
  service est là. L'écart garde désormais l'extension.

Sans service, rien ne change : ces formats restent écartés.

## Ce que Mes collections garde de son côté

Pour que le moteur soit remplaçable, la référence de ce qui est indexé est chez Mes collections, pas
chez le moteur :

- **les sources** :
  - le dossier Résana ;
  - pour un fichier déposé, sa copie dans `_sources` ;
- **pour chaque document** :
  - son empreinte (sha256) ;
  - son adresse d'origine ;
  - son identifiant dans l'index.

Pour passer à un autre moteur :

1. écrire son indexeur ;
2. le brancher dans `app.routers.ingest._indexeur`, le seul endroit où il se construit ;
3. réindexer chaque collection :
   - fichiers déposés : depuis leur copie ;
   - Résana : par « Vérification complète », avec la session de la personne qui a importé ; il n'y
     a pas de copie.

## Ce qui reste propre à OpenRAG

- **La recherche et la réponse.** Elles ont leur propre abstraction : les connecteurs du harnais des
  assistants (ADR-0003, `app/harnais/connecteurs/openrag.py`). Le bac à sable et la recherche du
  portail appellent encore OpenRAG directement.
- **Le découpage des fichiers texte par Mes collections** (`_upload_chunks_background`). Il envoie
  des morceaux, pas des documents.
- **Les droits sur les partitions**, synchronisés depuis Keycloak (`SyncService`).

## Tests

`myrag/tests/unit/test_indexeur.py` vérifie :

- la traduction des réponses d'OpenRAG ;
- un **indexeur en mémoire** qui remplace OpenRAG pour un import Résana complet, mise à jour comprise,
  sans qu'OpenRAG reçoive rien.
