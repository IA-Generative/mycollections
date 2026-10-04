"""MyRAG (beta) configuration."""

import os

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Réglages lus dans l'environnement.

    L'application s'appelle Mes collections (« mycollections ») : chaque variable MYRAG_* se lit
    aussi sous le nom MYCOLLECTIONS_* (ex. MYCOLLECTIONS_SUPERADMIN_GROUPES), qui est la forme à
    privilégier ; l'ancien nom reste accepté le temps que les déploiements basculent. Si les
    deux sont posés, MYCOLLECTIONS_* l'emporte."""
    app_title: str = Field(default="Mes collections (bêta)")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)

    # Database
    database_url: str = Field(default="sqlite+aiosqlite:////app/data/myrag.db")

    # OpenRAG
    openrag_url: str = Field(default="http://openrag:8080")
    openrag_admin_token: str = Field(default="")
    # L'adresse à laquelle un SI joint OpenRAG (bloc « Où interroger » des fiches).
    # Vide : on reprend openrag_url si elle est déjà publique (https).
    openrag_public_url: str = Field(default="")

    # Keycloak
    keycloak_url: str = Field(default="http://keycloak:8080")
    keycloak_realm: str = Field(default="openwebui")
    keycloak_client_id: str = Field(default="myrag-admin")
    keycloak_client_secret: str = Field(default="")
    keycloak_admin_user: str = Field(default="admin")
    keycloak_admin_password: str = Field(default="")

    # Restriction d'accès à un groupe du realm. Vide = pas de restriction (dev,
    # tests, intégration). Liste séparée par des virgules ; une entrée qui commence
    # par « / » est un CHEMIN (`/g/mirai-beta-testeurs`, mapper `full.path=true`,
    # la forme sûre), sinon un NOM COURT comparé tel quel (forme héritée du mapper
    # `full.path=false` : un homonyme créé dans keycloak-comu passerait). Les droits
    # de Mes collections (superadmin, groupes de collection) n'existent, eux, qu'en
    # chemins complets — cf. app/services/access.py.
    myrag_groupe_exige: str = Field(default="", validation_alias=AliasChoices("MYCOLLECTIONS_GROUPE_EXIGE", "MYRAG_GROUPE_EXIGE", "myrag_groupe_exige"))

    # Les groupes dont les membres administrent Mes collections (toutes les collections, les
    # catégories, les amorces, le menu Administration). Liste de CHEMINS COMPLETS séparés par des
    # virgules, par ex. `/g/mirai-beta-testeurs-admin`. Vide ⇒ personne n'est superadmin (hors
    # développement sans authentification). Remplace le groupe codé en dur `/myrag/superadmin`.
    # Reprendre au démarrage les indexations coupées par l'arrêt précédent (désactivé en test :
    # la tâche de fond survivrait au client de test).
    reprise_au_demarrage: bool = Field(default=True, validation_alias=AliasChoices(
        "MYCOLLECTIONS_REPRISE_AU_DEMARRAGE", "reprise_au_demarrage"))

    myrag_superadmin_groupes: str = Field(default="", validation_alias=AliasChoices("MYCOLLECTIONS_SUPERADMIN_GROUPES", "MYRAG_SUPERADMIN_GROUPES", "myrag_superadmin_groupes"))

    # Garde d'auth du backend (validation JWT Keycloak sur les routes XHR).
    # false par défaut (dev/tests) ; true en prod via la configmap. Sert aussi
    # de coupe-circuit (repasser à false + restart désactive la garde).
    auth_enabled: bool = Field(default=False)

    # Legifrance PISTE
    legifrance_client_id: str = Field(default="")
    legifrance_client_secret: str = Field(default="")

    # Suite Numerique Drive (file source)
    drive_url: str = Field(default="")
    drive_client_id: str = Field(default="mycollections-drive")
    drive_client_secret: str = Field(default="")
    # Nom d'hôte public de Drive, à envoyer en en-tête quand `drive_url` désigne le
    # service INTERNE. Drive est un Django : il refuse par un « Bad Request (400) » nu
    # tout hôte absent de sa liste, et redirige en 301 vers son adresse publique tant
    # qu'il croit répondre en clair. Vide = on n'y touche pas (dev, adresse publique).
    drive_public_host: str = Field(default="")

    # Open WebUI (used by /publish to create model aliases)
    # Défaut d'EXEMPLE : chaque déploiement pose son adresse par OWUI_URL. Nommer ici
    # un namespace réel ferait de ce dépôt public une carte de l'infrastructure.
    owui_url: str = Field(default="http://openwebui.mon-namespace.svc.cluster.local")
    owui_admin_api_key: str = Field(default="")
    # Adresse PUBLIQUE de l'assistant (celle qu'ouvre un navigateur) — `owui_url` est l'adresse interne,
    # pour les appels de service. Vide : les écrans ne proposent pas d'ouvrir l'assistant.
    owui_public_url: str = Field(default="")

    # Graph
    graphrag_viewer_url: str = Field(default="")
    myrag_group_root: str = Field(default="/myrag", validation_alias=AliasChoices("MYCOLLECTIONS_GROUP_ROOT", "MYRAG_GROUP_ROOT", "myrag_group_root"))
    # Préfixes refusés à la création d'une collection (séparés par des virgules) : ils disent
    # d'où vient la collection, pas ce qu'elle contient — et l'identifiant est ce que tapent
    # les applications (`openrag-<identifiant>`).
    myrag_prefixes_bannis: str = Field(default="demo-,amorce-,rag-,test-", validation_alias=AliasChoices("MYCOLLECTIONS_PREFIXES_BANNIS", "MYRAG_PREFIXES_BANNIS", "myrag_prefixes_bannis"))

    # Public URL (for iframe links)
    myrag_public_url: str = Field(default="http://localhost:8200", validation_alias=AliasChoices("MYCOLLECTIONS_PUBLIC_URL", "MYRAG_PUBLIC_URL", "myrag_public_url"))

    # CORS — liste d'origines autorisées (CSV). Vide => '*' SANS credentials
    # (l'API utilise des Bearer, pas de cookies). En prod, renseigner les
    # origines frontend de confiance pour verrouiller.
    cors_allow_origins: str = Field(default="")

    # Data directory
    data_dir: str = Field(default="/app/data")

    # ─── Le collectif (ADR-0001) ─────────────────────────────────────────────────
    # Sel du condensé des identités (HMAC-SHA256 du `sub`). LE MÊME que celui du bus
    # de la bêta (Secret `obs-pseudo-salt`) : un abonné a le même condensé ici et dans
    # la cloche du menu. Vide ⇒ les routes collaboratives répondent 503 plutôt que
    # d'écrire une identité en clair. En dev : MYRAG_PSEUDO_SEL=dev-sel.
    myrag_pseudo_sel: str = Field(default="", validation_alias=AliasChoices("MYCOLLECTIONS_PSEUDO_SEL", "MYRAG_PSEUDO_SEL", "myrag_pseudo_sel"))
    # Clé des liens signés (sources, graphe, articles ouverts sans jeton). Vide ⇒ dérivée du
    # sel des identités ; les deux vides ⇒ aucun lien signé n'est accepté.
    myrag_liens_sel: str = Field(default="", validation_alias=AliasChoices("MYCOLLECTIONS_LIENS_SEL", "MYRAG_LIENS_SEL", "myrag_liens_sel"))
    # Où lire capacites.json du menu commun (service interne du cluster). Vide ⇒
    # drapeaux à false et seuil au défaut : rien ne s'affiche, rien ne s'écrit.
    capacites_url: str = Field(default="")
    seuil_chantier_defaut: int = Field(default=5)
    # Un chantier sans événement depuis ce nombre de jours est « en sommeil ».
    sommeil_jours: int = Field(default=30)
    # Une demande « à confirmer » sans réponse de son auteur passe « réalisée » au bout de ce
    # nombre de jours (décision PO du 2026-09-21 : 5) — personne ne bloque le circuit.
    confirmation_jours: int = Field(default=5)
    # Le bus de la bêta (mirai-apps-menu) : l'adresse interne pour relayer le fil vers
    # la cloche, et le secret partagé qui authentifie les deux sens (X-Bus-Secret).
    # Vides : pas de relais, et /api/bus répond 503 (le patron du sel).
    bus_url: str = Field(default="")
    bus_secret: str = Field(default="")

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore", "populate_by_name": True}


settings = Settings()
