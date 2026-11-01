# La campagne de nuit des chemins de recherche

Pour l'équipe technique. Le banc (`scripts/banc.py`, [assistants.md](assistants.md)) joue un jeu figé
sans réseau ; la campagne, elle, pose de vraies questions à une **cible réelle**, la nuit, par les
deux chemins qu'empruntent les personnes :

- **harnais** : `POST /api/v1/assistants/{id}/executer` avec `rediger: true`, chaque question sur trois
  variantes d'un même assistant d'essai (`s0` sans contrainte, `s1` régimes et rangs, `s2` consignes) ;
- **MCP** : un modèle de la passerelle qui appelle les outils du vrai `/mcp`, comme le fait Open WebUI
  (« OWUI simulé ») : rien ne lui dit où chercher.

Le code est dans `myrag/scripts/campagne/`, le jeu d'essai dans `myrag/tests/campagne/sejour-des-etrangers/`
(fiches `s*.yaml` et `questions.yaml`, inventées), les tests hors réseau dans `myrag/tests/campagne/`.

## Ce qu'il faut avant la première nuit

| Variable | Rôle |
|---|---|
| `CAMPAGNE_CIBLE` | origine de Mes collections (https), ou `--cible` |
| `CAMPAGNE_SSO_HOST` | hôte du SSO (pour reconnaître sa page pendant la connexion) |
| `KC_TEST_IN_USERNAME` / `_PASSWORD` | le compte de test qui pose les questions (un lecteur) |
| `KC_TEST_ADMIN_USERNAME` / `_PASSWORD` | le compte qui applique les fiches d'essai (`corpus.py` seulement) |
| `CAMPAGNE_CORRESPONDANCE` | le fichier privé des alias (ci-dessous) |
| `CAMPAGNE_GATEWAY_URL` / `_TOKEN` | la passerelle de modèles (`…/v1`) et la clef **dédiée** à la campagne : phase `mcp` et juge-modèle. La campagne n'emprunte jamais `MIRAI_GATEWAY_TOKEN`, dont le quota est celui des personnes |
| `CAMPAGNE_RAPPORTS` | racine des rapports ; défaut : `../mirai-apps-beta-private/private/rapports/campagne/` à côté du dépôt. Jamais dans le dépôt (refusé) |

Le jeton du compte s'obtient par la connexion de la suite de bout en bout (`tests/e2e/_sso.py`,
navigateur sans écran, fermé aussitôt), puis se renouvelle par `refresh_token`. Si la session SSO a
expiré (une demi-heure d'inactivité, par exemple en attendant l'ouverture de la fenêtre), le
renouvellement est refusé et le lanceur se reconnecte seul. Playwright est requis :
`uv run --with playwright python -m playwright install chromium` une fois.

### Les alias des sources

Les fiches et les questions du dépôt ne nomment aucune collection réelle : leurs sources sont des
alias (`guide`, `guide-md`, `faq`, `mobilite`, `jurisprudence`). Le fichier `CAMPAGNE_CORRESPONDANCE`,
privé et hors dépôt, donne l'identifiant de chacun sur la cible :

```json
{"guide": "guide-du-sejour", "guide-md": "guide-du-sejour-md", "faq": "faq-des-prefectures", "mobilite": "immigration-et-mobilite", "jurisprudence": "decisions-ta-caa"}
```

Un alias absent arrête tout avant le premier appel. Seuls les assistants préfixés `e2e-camp-` se
manipulent ; aucune collection n'est créée.

```bash
cd myrag
uv run python -m scripts.campagne.corpus resoudre      # hors réseau : fiches valides, empreintes, 40 questions
uv run --with playwright python -m scripts.campagne.corpus verifier               # la cible a-t-elle ces fiches ?
uv run --with playwright python -m scripts.campagne.corpus appliquer --publier    # sinon, les poser (idempotent)
```

## Lancer une nuit

```bash
cd myrag
uv run --with playwright python -m scripts.campagne.run \
    --juge-modele <modèle> --max-executer 300 --max-appels-modele 400 [--catalogue 10]
```

Par défaut le lanceur attend 21 h et s'arrête à 6 h (`--fenetre 21h-6h`). Pour une nuit courte, tout
de suite : `--fenetre maintenant --max-executer 30` (10 questions sur les trois variantes, puis la
phase MCP dans la limite de `--max-appels-modele`). `--phases harnais` ou `--phases mcp` pour n'en
jouer qu'une.

- **Reprise** : chaque essai s'écrit dans `<nuit>/essais.jsonl` sous la clef (phase, variante,
  question, nuit). Relancer la même commande ne rejoue rien de ce qui a été mesuré ; seule une erreur
  serveur (5xx, 429 final, cible injoignable) se rejoue.
- **Budgets par nuit** : `--max-executer` (appels à `executer`), `--max-appels-modele` (agent, juge et
  questions du catalogue). Atteint : la phase s'arrête proprement.
- **Cadence** : un seau par route, `Retry-After` respecté. `executer` et `/mcp` partagent le quota
  serveur (30 par minute et par personne) : 20 par minute au plus (`--cadence-assistants`).
- **`--catalogue N`** : pour N collections lisibles hors essai, un passage tiré par `/api/v1/search`,
  une question écrite par le modèle d'après ce passage, posée à l'agent ; le témoin est ce passage.

### Règles d'arrêt

| Évènement | Effet |
|---|---|
| un passage d'une source que le compte ne lit pas (incident de droits) | arrêt immédiat, alerte en tête du rapport |
| plus de 20 % de 5xx sur les 50 derniers appels (hors vérification des liens cités, qui se mesure seulement) | arrêt de la nuit |
| trois 429 de suite sur une route | cadence de la route divisée par deux ; une seconde rafale arrête la nuit |
| cinq échecs de suite de la passerelle | arrêt de la nuit |
| le même arrêt trois nuits de suite | la nuit suivante ne démarre pas (`--forcer` après correction) |

Codes de sortie : 0 nuit jouée (ou bornée par un budget ou la fenêtre) ; 2 réglage manquant ; 3 règle
d'arrêt ; 4 campagne arrêtée.

## Lire le rapport

Chaque nuit écrit `<CAMPAGNE_RAPPORTS>/<nuit>/synthese.md` et `mesures.json` (et `etat.json`, les
exécutions et la consommation). `python -m scripts.campagne.rapport <dossier>` les régénère.

1. **En tête** : un arrêt, un incident de droits. Un incident se traite avant toute autre lecture.
2. **Go / no-go** : chaque seuil, sa valeur, `OK`, `KO` ou `non mesuré` (sans juge-modèle, les
   mesures de conformité manquent). Les seuils sont ceux du plan, à régler après la première nuit de
   référence (`SEUILS` dans `rapport.py`).
3. **Tendance** : chaque mesure comparée à la nuit précédente qui a un rapport.
4. **Harnais**, par variante : source attendue au rang 1 et dans les cinq premiers, part des sources
   contactées, consigne retenue à raison (sur les questions qui l'attendent) et à tort (part des
   essais où une consigne non attendue l'a été), « ne répond pas » à raison et à tort, renvois `[n]`
   valides, contraintes de la règle « répondre », relais exécutés, juge, p95.

   Deux juges-modèle. La **fidélité** (go / no-go) juge la réponse au regard des seuls passages reçus :
   rien d'inventé, rien de refusé que les passages permettaient de répondre. La **conformité à la
   référence** compare à la réponse écrite dans `questions.yaml` ; elle reste indicative, car ces
   références citent parfois des textes que le corpus d'essai n'a pas (nuit du 2026-11-01 : 11 à 48 %
   « conforme », pour des réponses le plus souvent fidèles à leurs passages).
5. **MCP** : bonne collection parmi celles cherchées (et au premier essai), `rechercher` appelé quand
   il le faut, rappel@5, hors catalogue sans source citée (un agent conversationnel répond de
   lui-même à « une recette de crêpes » ; il ne doit pas l'attribuer à Mes collections), liens inventés (cités mais jamais rendus), injections
   réussies (le canari de la question dans la réponse), taille de `lister_sources`.
6. **Échecs typiques** : la question, les motifs, les premiers passages ; le détail de chaque essai
   (plan, passages sans leur texte, réponse, conversation de l'agent avec les textes lus par le juge) est dans `essais.jsonl`.

Les rapports contiennent des réponses et des titres de documents réels : ils restent dans le dossier
privé, jamais dans ce dépôt.
