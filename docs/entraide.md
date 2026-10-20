# Le réseau d'entraide

Une personne lance un appel à l'aide ; le réseau propose d'abord ce qui existe, puis des
personnes, puis un lieu pour échanger. Drapeau : `entraide` (capacites.json). Décision :
[ADR-0003](adr/ADR-0003-assistants-de-recherche.md). Les demandes du collectif
([collectif.md](collectif.md)) en deviennent un type d'appel, inchangées.

## Fonctionnement

Trois types d'appel :

- **Il me manque une donnée** : ce sont les demandes du collectif, lues **par référence** (jamais copiées) ; elles s'ouvrent et se soutiennent sur `/demandes/<id>`, et `/api/demandes` ne change pas.
- **Je cherche quelqu'un qui connaît…** et **Je propose mon aide sur…** : des appels rédigés dans le réseau (`/entraide/nouveau`).

Un appel naît **brouillon**, visible de son seul auteur. Avant de le publier, l'écran affiche « Ceci existe peut-être déjà » (`GET /api/entraide/appels/{id}/recommandations`) : les collections et assistants que la personne peut lire et qui ressemblent à l'appel (apparieur du moteur des assistants, sac de mots par défaut), et les rôles anonymes — des décomptes — de ceux qui ont soutenu une demande voisine. Puis l'auteur **publie**, on **répond**, l'auteur (ou l'administration) **clôt**. On ne répond qu'à un appel publié et ouvert.

Un **lien Tchap** facultatif permet d'échanger : https, hôte de la liste blanche `MYCOLLECTIONS_ENTRAIDE_TCHAP_HOTES` (défaut `tchap.gouv.fr`), sans identifiants, port, chemin ni paramètres, et un fragment de salon `#/room/<salon>:<serveur>`. Une adresse de messagerie est refusée (`app/services/tchap.py`).

Données : tables `entraide_appel`, `entraide_reponse`, `entraide_lien` (`app/models/entraide.py`) ; identités condensées (`_hash`), aucune donnée personnelle en clair, et les réponses JSON n'exposent jamais le condensé de l'auteur. Tout le préfixe `/api/entraide` répond 404 tant que le drapeau est faux ; `/demandes` ne mène à `/entraide` que s'il est vrai.
