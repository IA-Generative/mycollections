"""MyRAG (beta) configuration."""

import os

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_title: str = Field(default="MyRAG (beta)")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)

    # Database
    database_url: str = Field(default="sqlite+aiosqlite:////app/data/myrag.db")

    # OpenRAG
    openrag_url: str = Field(default="http://openrag:8080")
    openrag_admin_token: str = Field(default="")

    # Keycloak
    keycloak_url: str = Field(default="http://keycloak:8080")
    keycloak_realm: str = Field(default="openwebui")
    keycloak_client_id: str = Field(default="myrag-admin")
    keycloak_client_secret: str = Field(default="")
    keycloak_admin_user: str = Field(default="admin")
    keycloak_admin_password: str = Field(default="")

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

    # Open WebUI (used by /publish to create model aliases)
    owui_url: str = Field(default="http://openwebui.miraiku.svc.cluster.local")
    owui_admin_api_key: str = Field(default="")

    # Graph
    graphrag_viewer_url: str = Field(default="")
    myrag_group_root: str = Field(default="/myrag")

    # Public URL (for iframe links)
    myrag_public_url: str = Field(default="http://localhost:8200")

    # CORS — liste d'origines autorisées (CSV). Vide => '*' SANS credentials
    # (l'API utilise des Bearer, pas de cookies). En prod, renseigner les
    # origines frontend de confiance pour verrouiller.
    cors_allow_origins: str = Field(default="")

    # Data directory
    data_dir: str = Field(default="/app/data")

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}


settings = Settings()
