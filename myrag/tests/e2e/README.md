# Suite de bout en bout — un navigateur sans écran contre une cible réelle

Ce dossier joue **la séquence d'usage de Mes collections** telle qu'une personne la vit : se
connecter au SSO, découvrir l'accueil, interroger une collection, en créer une en cinq étapes,
la faire passer par son circuit de vérification, la publier, la retrouver dans Mon assistant
**avec le compte du testeur**, déposer une demande, lire le guide. Chaque pas est un test ; le
tout est rejouable pour chaque campagne, et produit des captures d'écran.

Rien ici ne connaît la cible : adresses et comptes viennent de l'environnement. Sans
`E2E_BASE_URL`, la suite s'ignore (`pytest tests/unit` et `pytest` tout court restent ce qu'ils
étaient).

## Lancer

```bash
cd myrag
pip install -r requirements-e2e.txt
python -m playwright install chromium

export E2E_BASE_URL=https://mescollections.fake-domain.name
export E2E_SSO_HOST=sso.fake-domain.name
export E2E_TESTEUR_USERNAME=…  E2E_TESTEUR_PASSWORD=…        # membre du groupe requis
export E2E_HORS_GROUPE_USERNAME=… E2E_HORS_GROUPE_PASSWORD=… # facultatif : compte hors groupe
export E2E_ADMIN_USERNAME=…   E2E_ADMIN_PASSWORD=…           # facultatif : superadmin (/myrag/superadmin)
export E2E_ASSISTANT_URL=https://monassistant.fake-domain.name  # facultatif : preuve dans l'assistant
export E2E_CAPTURES=/chemin/vers/captures                     # facultatif : captures d'écran

python -m pytest tests/e2e -rxXs          # toute la séquence, dans l'ordre
python -m pytest tests/e2e/test_01_acces.py  # un parcours
E2E_HEADED=1 python -m pytest tests/e2e/test_04_creation_collection.py  # voir le navigateur
```

Les comptes ne vont **jamais** dans un fichier du dépôt : exportez-les dans le shell depuis le
gestionnaire de secrets de votre plateforme.

| Variable | Rôle | Si absente |
|---|---|---|
| `E2E_BASE_URL` | la cible | toute la suite est ignorée |
| `E2E_SSO_HOST` | hôte du fournisseur d'identité (pour reconnaître sa page) | la connexion échoue |
| `E2E_TESTEUR_USERNAME` / `_PASSWORD` | compte membre du groupe requis | la suite échoue net |
| `E2E_HORS_GROUPE_USERNAME` / `_PASSWORD` | compte valide hors du groupe | le test de refus est ignoré |
| `E2E_ADMIN_USERNAME` / `_PASSWORD` | compte superadmin **et** membre du groupe | les parcours d'administration sont ignorés |
| `E2E_ASSISTANT_URL` | adresse publique de Mon assistant (Open WebUI) | la preuve dans l'assistant est ignorée |
| `E2E_CAPTURES` | dossier de sortie des captures | pas de captures (sauf à l'échec, dans le dossier temporaire) |
| `E2E_HEADED` | `1` pour voir le navigateur | sans écran |

## Ce que chaque parcours prouve

| Module | Prouve |
|---|---|
| `test_01_acces` | le service est sain ; l'API refuse tout appel sans jeton ; un compte hors groupe est refusé ; un lien partagé mène à sa page |
| `test_02_accueil_catalogue` | l'accueil dit quoi faire et son exemple préremplit le bac à sable ; le catalogue liste, cherche, mène aux fiches ; une fiche se lit ; une adresse inconnue est dite en français |
| `test_03_bac_a_sable` | une question reçoit une réponse sans erreur, qui cite ses sources, lisibles au survol puis en fenêtre ; l'avis dit ce qu'il fait ; l'écran vouvoie |
| `test_04_creation_collection` | les cinq étapes, par l'interface : source, identification (identifiant vérifié), dépôt et indexation d'un document, question témoin à l'étape 4, étape 5 qui ne promet que ce qui existe, fiche créée ; un PDF refusé avec une explication ; graphe d'une collection non publique fermé sans lien signé |
| `test_05_publication_assistant` | grille de contrôle complétée et relue ; passages d'état jusqu'à « publiée à tous » ; publication « à tous » ; **le testeur voit le modèle dans l'assistant et il répond avec le témoin** ; dépublier le retire |
| `test_06_demandes` | la page explique seuil et garant ; déposer une demande ; la lire ; soutenir puis retirer ; l'auteur peut la clore |
| `test_07_guide` | six pages ordonnées, un sommaire qui mène à chacune, un contenu cohérent avec l'interface |
| `test_08_administration` | un simple testeur n'entre pas ; le superadmin entre ; aucune carte ne mène à une page absente |
| `test_09_captures` | une image de chaque écran, à 1280 px et 390 px, avec son texte visible (`E2E_CAPTURES` seulement) |
| `test_11_recherche_portail` | la recherche de Mon portail (`/api/v1/search`) : périmètres lisibles seulement, résultats limités aux collections lisibles, périmètre inconnu ignoré, requête invalide en 400, 401 sans jeton |

Le témoin est une phrase qu'aucun modèle ne peut connaître (`QUETZAL-9031`, dans
`fixtures/note-de-controle.md`) : la retrouver dans une réponse prouve que la chaîne
découpage → indexation → recherche → génération a fonctionné de bout en bout.

## Conventions

- **Un test écrit le comportement attendu.** Là où l'application échoue aujourd'hui, le test
  porte `xfail(strict=True, reason="P… : …")` : la suite reste verte, le défaut est documenté
  par un test, et il **casse le jour où le correctif arrive**, ce qui oblige à retirer la
  marque. `pytest -rxX` liste ces constats.
- **Les modules sont numérotés** dans l'ordre de la séquence, et partagent une seule session de
  testeur : ce que `test_04` crée, `test_05` le publie. Lancer un module seul fonctionne, mais
  `test_05` suppose la collection de `test_04`.
- **Les données d'essai sont nettoyées** : la collection `e2e-<date>` est dépubliée, archivée
  et purgée en fin de session (et toute `e2e-*` orpheline l'est au début) ; la demande d'essai
  est close. Les préfixes `test-` et `demo-` sont refusés par le serveur, d'où `e2e-`.
- **Le verdict de connexion vient de l'API**, jamais de l'allure de la page : c'est le backend
  qui applique la restriction de groupe. L'hôte du SSO est comparé, pas une sous-chaîne
  (Keycloak met `iss=https://sso…` dans l'adresse de retour).
- **À l'échec**, une image de la page du testeur est écrite dans `<E2E_CAPTURES>/_echecs/`
  (ou dans le dossier temporaire), et son chemin figure dans le rapport pytest.

## Ajouter un parcours pour une campagne

1. Créer `test_NN_<parcours>.py` ; prendre `session_testeur` (page + API), `collection_essai`
   ou `collection_publiee` selon qu'il faut une collection neuve ou une collection déjà
   servie, `captures` pour les écrans.
2. Viser des repères stables : identifiants de champs (`#titre`, `#d-titre`), rôles ARIA
   (`get_by_role("button", name=…)`), classes de composants (`.myrag-msg--assistant`).
3. Attendre une condition (`attendre(...)`, `wait_for`) plutôt qu'un délai.
4. Si l'application échoue : garder l'attendu, poser un `xfail` strict avec le constat.

## Pièges connus

- **Poste sous VPN** : si le SSO résout vers une adresse privée, la page publique ne peut pas
  l'appeler ; la suite s'ignore avec ce motif. Rejouer hors VPN.
- **Compte administrateur** : il doit être superadmin **et** membre du groupe requis ; sinon
  les parcours d'administration sont ignorés, et la raison est dite.
- **Le témoin dans l'assistant** peut mettre jusqu'à trois minutes : c'est le modèle, pas la suite.
