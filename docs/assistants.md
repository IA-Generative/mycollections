# Les assistants de recherche

Un assistant interroge plusieurs sources — des collections et des connecteurs — selon des
consignes, et sert d'abord les réponses fiables. Décision : [ADR-0003](adr/ADR-0003-assistants-de-recherche.md).
Contrat : `myrag/app/harnais/contrat.py`. Drapeau : `assistants` (capacites.json).


## La fiche (lot 0)

`GET /api/assistants`, `GET|PUT /api/assistants/{id}`, `POST /api/assistants/{id}/publier`,
`GET /api/assistants/{id}/versions`. Publier fige une version (texte canonique + sha256) ; une
collection publiée a son assistant miroir à une source.


## Le fichier YAML

Une fiche s'écrit aussi en YAML, un fichier par assistant : une équipe l'écrit, le relit et le
versionne dans git ; un testeur l'exporte et l'importe depuis l'écran **Consignes** (« Le fichier
de la fiche »). Le YAML n'est qu'une écriture du contrat (`myrag/app/harnais/fiche_yaml.py`) : ce
qui fait foi reste la fiche validée, son texte canonique et son empreinte. Exemple complet,
données inventées : [`exemples/assistants/sejour-des-etrangers.yaml`](exemples/assistants/sejour-des-etrangers.yaml).

| Clef YAML | Champ du contrat | Note |
|-----------|------------------|------|
| `assistant`, `titre`, `rubrique`, `description` | idem | `assistant` : 3 à 64 caractères, minuscules, chiffres, `.` `_` `-` ; c'est l'`{id}` de l'adresse |
| `seuil_fiable` | idem (0 à 1, défaut 0.9) | au-dessus, une réponse fiable est servie sans recherche |
| `validation_requise` | idem (défaut `false`) | |
| `sources: [{id, type, regime, rang}]` | `Source` | `type` : `collection` ou `connecteur` ; `regime` : `toujours`, `selon_question` (défaut), `sur_consigne` ; `rang` facultatif, 1 = en premier |
| `consignes: [{id, quand, exemples, chercher, repondre, gabarit}]` | `Consigne` | `quand: toujours` vaut pour toute question (une seule consigne) ; `exemples` : 10 au plus |
| `chercher: [{source, avec}]` | `EtapeConsigne` | `source` : une des `sources` ; les étapes s'enchaînent dans l'ordre |
| `contrat` | idem | facultatif : seule la version 1 existe ; l'en-tête la rappelle en commentaire |
| `publication`, `reference` | — | ignorées à l'import, avec un avertissement : les canaux se règlent dans l'écran Publication (ceux du brouillon restent), `reference` est calculée |

`avec` nomme un **relais** (`article_trouve`, `reference`… : minuscules, chiffres et `_`) : l'étape
reçoit ce que les étapes précédentes ont trouvé, et l'effet dépend de la source qui le reçoit.
Une collection : la question est précisée par le meilleur passage amont. Un référentiel
(connecteur) : on y cherche la référence courte de ce passage (l'article, le titre). Jamais sur la
première étape, où rien n'a encore été trouvé.

L'export écrit, en commentaires, `# contrat: 1 · empreinte: sha256:<…>` — l'empreinte que prendra
la version publiée de ce contenu (`GET /api/assistants/{id}/versions` permet de comparer) — et le
résumé de `reference` (questions, fiables). L'ordre des clefs est fixe (identité et réglages, puis
sources et consignes ; dans un objet, l'ordre du contrat), une source ou une étape tient sur une
ligne, les valeurs par défaut des champs facultatifs ne s'écrivent pas : réexporter une fiche
inchangée rend le même fichier, et le diff d'une revue ne montre que ce qui change.

La lecture est sûre : `yaml.safe_load` seulement (une balise `!!python/…` est refusée), ni alias
(`*nom`), ni clef en double, 64 Kio au plus. Une erreur dit le champ et la règle, en français :
`consignes[2] (accord-bilateral) › chercher[1] › source : …` (rangs comptés à partir de 1).

- `GET /api/assistants/{id}/fiche.yaml` : le brouillon (`text/yaml`, `<id>.yaml`), mêmes droits
  que `GET /api/assistants/{id}`. Qui ne gère pas l'assistant reçoit ce qu'il lit : les
  collections qu'il ne lit pas sont absentes, et l'en-tête le dit.
- `PUT /api/assistants/{id}/fiche.yaml` (corps : le fichier) : remplace le brouillon, avec les
  droits et les règles de `PUT /api/assistants/{id}` ; 400 si `assistant:` diffère de `{id}`,
  422 `{detail: {message, erreurs: [{champ, message}]}}` si le fichier est invalide, 413 au-delà
  de 64 Kio. Rend la fiche enregistrée, `avertissements` et `empreinte`. Publier reste un geste à
  part (`POST …/publier`).

En ligne de commande (depuis `myrag/`, hors de l'image) :

    uv run python -m scripts.fiche verifier ../docs/exemples/assistants/sejour-des-etrangers.yaml
    uv run python -m scripts.fiche exporter <id> --cible https://mycollections.fake-domain.name --jeton-env JETON --sortie <id>.yaml
    uv run python -m scripts.fiche appliquer <id>.yaml --cible https://mycollections.fake-domain.name --jeton-env JETON [--publier]

`verifier` ne touche pas le réseau : il valide le fichier et affiche son empreinte (de quoi le
contrôler en CI). `exporter` et `appliquer` agissent avec les droits de la personne dont le jeton
d'accès est lu dans la variable nommée par `--jeton-env` — jamais passé en argument ; `--cible`
en https (http seulement vers `localhost`). Codes de sortie : 0 réussi, 1 refusé, 2 usage ou
service injoignable.


## Le harnais (lot A)

`myrag/app/harnais/` (sans FastAPI ni base, sauf `journal.py`) : un planificateur produit un plan, `execution.py`
l'exécute (étapes en parallèle, relais `avec`, source en panne ignorée et comptée), `fusion.py` fusionne (RRF, k = 60,
poids par étape, quota des sources `toujours`), `perimetre.py` ne garde que ce que la personne lit. Planificateurs :
`toutes_les_sources` (banc de comparaison) et `regles` (consigne reconnue par ressemblance au
« quand » et aux exemples ; sinon régimes des sources, jamais `sur_consigne`). La recherche
`GET /api/v1/search?assistant=<id>` suit la fiche comme les routes ci-dessous et le serveur MCP (`regles`), mais sans
réponse fiable : le contrat v1 n'a pas de champ pour la rendre. Routes `POST /api/v1/assistants/{id}/plan`
et `/executer` : la version enregistrée pour qui peut modifier, la publiée pour les autres. Le journal (`plans_journal`)
ne garde aucun texte. Avec `MYCOLLECTIONS_DOUBLURE_ASSISTANTS`, la doublure répond (en-tête `X-Mycollections-Doublure: 1`).

## La rédaction

`POST /api/v1/assistants/{id}/executer` avec `"rediger": true` (le bac à sable et « Tester » l'envoient) : après la
fusion et le filtre des droits, `harnais/redaction.py` rédige une réponse à partir des 12 premiers passages (`PASSAGES_MAX` ;
la fusion alterne les sources, les bons passages arrivent parfois loin), numérotés [1]…[n] et encadrés comme données.
Prompt système : le gabarit connu des consignes, les règles « répondre » de la consigne `toujours` puis de la retenue, puis
« uniquement à partir des passages ». Des passages hors sujet font répondre « Les documents trouvés ne répondent pas à cette
question. » (il n'y a pas de seuil de pertinence). Un renvoi qui ne désigne aucun passage est retiré ; `citations` donne
`{n, passage, document, source}`, `redaction` vaut `faite`, `aucun_passage` (modèle non appelé) ou `indisponible` (panne,
délai de 60 s, débit plein, fournisseur non configuré : la route rend quand même 200 et les passages). Le modèle est celui
de la génération (`MYCOLLECTIONS_GENERATION_LLM_*`, sinon le `/v1` d'OpenRAG), sous le débit partagé avec le juge. Sans
`rediger` (le MCP, la recherche v1), rien ne change : ni `citations` ni `redaction` dans le JSON.

## Un référentiel comme source (lot A6)

Une source de type `connecteur` n'est pas une collection : elle interroge un service HTTP interne. Le premier est le
référentiel d'éligibilité (`harnais/connecteurs/eligibilite.py`, type `eligibilite` : titres de séjour → situations →
pièces). Il se déclare par `MYCOLLECTIONS_CONNECTEURS` (tableau JSON `{id, type, url, titre, description, tables, exemples, groupes}`, `groupes` facultatif : chemins complets qui réservent le connecteur à ces groupes, sinon ouvert à tous) ;
vide, rien ne change. Un connecteur déclaré est lisible de toute personne qui passe la garde de l'application ; non
déclaré, il n'est jamais lu (le périmètre et le filet `restreindre_passages` le vérifient). Le service ne connaît personne :
le connecteur n'envoie ni `Authorization` ni identifiant. Il tire de la question quelques mots significatifs (trois appels
de `/tables/{t}/search` au plus par table), classe les lignes par mots retrouvés ; une étape `avec` (relais `reference`)
cherche la référence courte du meilleur passage amont. Panne, délai (`MYCOLLECTIONS_RECHERCHE_DELAI_S`) ou JSON illisible :
liste vide, jamais d'exception. `/query` n'est pas utilisé. L'écran « Ajouter une source » les propose (`GET /api/assistants/connecteurs`,
sans l'adresse du service) avec l'étiquette « Référentiel » ; assembler demande de gérer les seules **collections**.
En production, Mes collections doit pouvoir joindre le service (règle réseau à poser côté infrastructure).


## Le banc (lot A)

`scripts/banc.py` joue un jeu figé (`tests/harnais/fixtures/banc/`) sans HTTP ni réseau et compare les planificateurs :
rappel du passage témoin (`rappel@1`, `rappel@5`), part des sources contactées, score, incidents de droits (un passage
d'une source que la personne ne lit pas), durée p95 (non bloquante). Le juge « doublure » est déterministe (conforme si le
témoin attendu est rendu, partiel si c'est celui d'une autre source) ; le juge « réel » n'est pas branché. Seuils : `seuils.json`.

    cd myrag && uv run python -m scripts.banc tests/harnais/fixtures/banc/sejour-des-etrangers.json --juge doublure --planificateur regles --rapport json
    cd myrag && uv run pytest tests -q -m banc


## L'interface (lot B)

Sous le drapeau `assistants`, l'entrée « Assistants » du menu mène à `/assistants` (liste,
création). Un assistant a ses rubriques (`frontend/pages/assistants/[id]/`) :

- **Sources** et **Publication** (B1) : quelles collections, quand les interroger, dans quel
  ordre ; canaux, versions.
- **Consignes** (B2) : quand (une phrase ou « pour toute question »), exemples, étapes de
  recherche, consigne de rédaction ; enregistrées par `PUT /api/assistants/{id}` (la fiche
  entière). « Tester » appelle `POST /api/v1/assistants/{id}/executer`.
- **Bac à sable** (B4) : les briques du bac à sable d'une collection (`components/playground/`)
  pointées sur `executer` ; sous chaque réponse, « Comment l'assistant a cherché » (consigne
  retenue, étapes, sources non interrogées, sources écartées comptées sans être nommées).

Les calculs d'écran sont des fonctions pures de `frontend/utils/assistants.ts` (`validerConsigne`,
`ordonnerEtapes`, `traceDuPlan`…), testées dans `frontend/tests/unit/assistants*.test.ts`.


## Travailler sans le harnais

Le moteur répond sur la bêta depuis la fusion des lots A1 et A3. La doublure reste utile pour
montrer les écrans sans OpenRAG, en local ou sur une prévisualisation :

```bash
cd myrag
MYCOLLECTIONS_DOUBLURE_ASSISTANTS=true \
MYCOLLECTIONS_CAPACITES_SURCHARGE='{"assistants": true}' \
AUTH_ENABLED=false MYRAG_PSEUDO_SEL=dev-sel uv run uvicorn app.main:app --port 8200
```

`POST /api/v1/assistants/{id}/plan` et `/executer` rendent alors le plan et le résultat de
`myrag/app/doublure/assistants/`, avec l'en-tête `X-Mycollections-Doublure: 1` ; l'interface
l'annonce par un encadré « Réponse d'exemple ». Jamais sur la bêta ni en production.

Les deux routes du moteur sont limitées par personne : `MYCOLLECTIONS_ASSISTANTS_PAR_MINUTE`
(30 par défaut, par processus) ; au-delà, 429 avec `Retry-After`. Un moteur entièrement en panne
rend 503 avec `Retry-After: 10`.
