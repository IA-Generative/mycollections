"""Le filet de non-régression du chantier « assistants de recherche ».

Ces tests figent le comportement EXISTANT avant que les lots ne le touchent : le contrat
de recherche v1, les demandes de la communauté, le bac à sable, l'étape 4 de l'assistant
de création, l'accueil, l'intégration Open WebUI, les capacités. Ils doivent rester verts
après chaque lot ; quand un lot change un comportement figé, il ré-enregistre le fichier
figé dans SA PR (voir `_outils.py`) et le diff se relit.

Ce que figent déjà les tests existants, et qui compte aussi : `tests/unit/test_recherche.py`
(périmètre, droits, erreurs, CORS, jeton), `test_regle5_capacites.py` (404 à drapeau faux),
`test_qualite_questions.py` (règles de la réponse fiable), `test_accueil.py` (règles de
l'accueil), `test_non_regression.py` (tables et routes historiques).
"""
