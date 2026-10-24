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
| `suivre(tache)` | où en est la lecture : `en_cours`, `lu`, ou `echec` avec sa raison |
| `retirer(collection, identifiant)` | le document sort de l'index ; un document absent n'est pas une erreur |
| `vider(collection)` | toute la collection sort de l'index |

Deux exceptions :

- `DejaPresent` : l'identifiant est déjà indexé, après un renvoi qui suit une coupure. Le dépôt le
  compte comme réussi.
- `Refuse(statut)` : le moteur refuse le document, pour une question de format ou de taille.

Les métadonnées envoyées sont le titre (`title`) et, pour Résana, l'adresse du document d'origine
(`url`).

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
