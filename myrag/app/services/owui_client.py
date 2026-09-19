"""Open WebUI HTTP client — used by the publish flow to register/update
an OWUI Model entity that aliases an OpenRAG partition.

Pattern aligned with owuiapps-agents/src/lib/owui-admin-client.ts: a
single server-side `OWUI_ADMIN_API_KEY` (generated once by an OWUI admin
in Settings > Account > Cles API) is used for all model CRUD. The
published_by field on the Publication row keeps the audit trail of who
pressed the button on our side.

OWUI v0.8.12 endpoint shape:
- POST /api/v1/models/create         — create new model
- POST /api/v1/models/model/update   — update (id in body AND query — cf. ci-dessous)
- POST /api/v1/models/model/delete   — delete
- GET  /api/v1/models/model?id=…     — fetch one

All accept `Authorization: Bearer <admin_api_key>`.

À partir d'OWUI 0.11, le partage ne passe plus par ``access_control`` mais par une
liste ``access_grants``. Deux conséquences, toutes deux mesurées sur un socle 0.11 :

1. ``access_control: null`` fait échouer la mise à jour avec un **500** dont le corps ne
   dit rien (la trace n'existe que dans le journal du socle : « access_grants — Input
   should be a valid list »). La mise à jour tombait alors sur la création, qui répond
   **401 « This model id is already registered »** — un code d'authentification pour un
   conflit de nom, de quoi chercher la panne du mauvais côté pendant longtemps ;
2. le partage se déclare avec ``{principal_type, principal_id, permission}``.
   ``user/*`` = tout compte connecté ; ``group/<id>`` = un groupe ; ``anyone/*`` =
   **sans authentification**, systématiquement retiré par le socle sur cette route —
   ce n'est pas la façon de rendre une collection visible aux testeurs.

Le corps envoyé porte les DEUX formes : le socle ignore celle qu'il ne connaît pas.
"""

from __future__ import annotations

import httpx

from app.config import settings


class OwuiAdminUnavailable(RuntimeError):
    """Raised when OWUI_ADMIN_API_KEY isn't configured. The publish flow
    catches this and returns a helpful message to the UI rather than
    exposing the bare exception text.
    """


def grants_de_partage(visibility: str, groupes: list[str] | None) -> list[dict]:
    """Traduit la portée d'une publication en autorisations OpenWebUI (>= 0.11).

    `anyone/*` n'est JAMAIS émis : ce serait un accès sans authentification, et le
    socle le retire de toute façon sur cette route. « Tout le monde » veut dire ici
    « tout compte connecté », soit `user/*`.
    """
    if visibility == "group" and groupes:
        return [
            {"principal_type": "group", "principal_id": g, "permission": "read"}
            for g in groupes
        ]
    if visibility == "all":
        return [{"principal_type": "user", "principal_id": "*", "permission": "read"}]
    return []


#: Ce que Mes collections pose dans `meta` d'une fiche. Tout le reste (outils, filtres,
#: actions, connaissances… posés dans l'assistant ou par un script d'exploitation) ne lui
#: appartient pas et survit à une republication.
_META_GERE = ("description", "profile_image_url", "suggestion_prompts", "tags", "capabilities")
TAG_MES_COLLECTIONS = "Mes collections"


def fusionner_fiche(existante: dict | None, voulue: dict, *, description: str = "",
                    system_prompt: str = "", suggestions_fournies: bool = False) -> dict:
    """Ce qu'on envoie au socle : la fiche VOULUE, sans rien effacer de ce qu'on ne gère pas.

    Republier une collection réécrivait la fiche entière : le prompt système réglé dans
    l'assistant (`params.system`), ses autres paramètres, ses outils et ses filtres
    disparaissaient sans un mot — la collection répondait encore, mais plus comme prévu.

    - `params` : ceux de la fiche existante ; `system` n'est remplacé que si un prompt
      est FOURNI (un prompt vide ne veut pas dire « effacer »).
    - `meta` : les clés que Mes collections ne gère pas sont gardées ; une description
      vide ne remplace pas une description rédigée ; les étiquettes posées ailleurs
      restent, « Mes collections » s'y ajoute ; les suggestions ne sont remplacées que
      si l'appelant en fournit.
    Fonction pure : ni réseau ni horloge.
    """
    fiche = {**voulue, "meta": dict(voulue.get("meta") or {}), "params": dict(voulue.get("params") or {})}
    if not existante:
        return fiche
    meta_avant = existante.get("meta") or {}
    params_avant = existante.get("params") or {}

    fiche["params"] = {**params_avant, **({"system": system_prompt} if system_prompt else {})}

    meta = {k: v for k, v in meta_avant.items() if k not in _META_GERE}
    meta.update(fiche["meta"])
    if not description and meta_avant.get("description"):
        meta["description"] = meta_avant["description"]
    if not suggestions_fournies and meta_avant.get("suggestion_prompts"):
        meta["suggestion_prompts"] = meta_avant["suggestion_prompts"]
    if meta_avant.get("profile_image_url"):
        meta["profile_image_url"] = meta_avant["profile_image_url"]
    noms = [t.get("name") for t in meta.get("tags") or [] if isinstance(t, dict)]
    autres = [t for t in meta_avant.get("tags") or []
              if isinstance(t, dict) and t.get("name") and t.get("name") not in noms]
    meta["tags"] = autres + list(meta.get("tags") or [])
    fiche["meta"] = meta
    return fiche


class OwuiClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 timeout: float = 15.0):
        self.api_key = api_key or settings.owui_admin_api_key
        if not self.api_key:
            raise OwuiAdminUnavailable(
                "OWUI_ADMIN_API_KEY n'est pas configure sur ce MyRAG. "
                "Un admin OWUI doit generer une cle API (Parametres > Compte > "
                "Cles API) et la stocker dans le secret 'myrag-secrets' du cluster."
            )
        self.base_url = (base_url or settings.owui_url).rstrip("/")
        self.timeout = timeout

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def get_model(self, model_id: str) -> dict | None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/models/model",
                params={"id": model_id},
                headers=self._headers(),
            )
        if resp.status_code == 401:
            raise PermissionError(
                "OWUI a rejete la cle admin (cle invalide ou expiree). "
                "Regenere une cle dans OWUI > Parametres > Compte > Cles API."
            )
        resp.raise_for_status()
        data = resp.json()
        return data if data else None

    async def _fiche_existante(self, model_id: str) -> dict | None:
        """La fiche déjà posée, ou None s'il n'y en a pas.

        Un socle répond 401, 403 ou 404 selon sa version pour une fiche ABSENTE (c'est
        déjà ce qui oblige `upsert_model` à tenter la création après tout échec de mise
        à jour) : ces réponses valent « pas de fiche ». Une clé vraiment invalide sera
        dite par la création. Toute AUTRE panne (délai, 5xx) remonte : mieux vaut une
        publication à rejouer qu'une fiche réécrite à l'aveugle, prompt effacé.
        """
        try:
            return await self.get_model(model_id)
        except PermissionError:
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 404):
                return None
            raise

    async def upsert_model(
        self,
        model_id: str,
        name: str,
        description: str = "",
        base_model_id: str | None = None,
        system_prompt: str = "",
        access_control: dict | None = None,
        access_grants: list[dict] | None = None,
        suggestion_prompts: list[str] | None = None,
    ) -> dict:
        """Create or update an OWUI Model.

        Mirrors owuiapps-agents' approach: try update first, fall back to
        create if the update fails (e.g. model doesn't exist yet).
        Idempotent on repeated calls with the same model_id.

        Ne réécrit pas ce qu'il ne gère pas : voir `fusionner_fiche`.
        """
        existante = await self._fiche_existante(model_id)
        body = {
            "id": model_id,
            "name": name,
            "meta": {
                "description": description or f"Collection MyRAG {model_id}",
                "profile_image_url": "/static/favicon.png",
                "suggestion_prompts": [
                    {"content": p} for p in (suggestion_prompts or [])
                ],
                "tags": [{"name": TAG_MES_COLLECTIONS}],
                "capabilities": {"vision": False, "usage": False, "citations": True},
            },
            "params": (
                {"system": system_prompt} if system_prompt else {}
            ),
            # `None` veut dire « cette fiche RECOUVRE le modele de connexion qui porte le
            # meme identifiant » — c'est le cas quand la collection est servie
            # directement par OpenRAG, declare comme connexion du socle. Y remettre
            # l'identifiant du modele donnerait le resultat inverse : la fiche serait
            # traitee comme un modele DERIVE, dont l'identifiant existe deja, donc
            # ignoree en silence. La collection disparaitrait du selecteur des
            # utilisateurs tout en restant appelable — un symptome qui n'oriente vers
            # rien. Ne renseigner ce champ que pour viser un AUTRE modele (un connecteur
            # « pipelines », par exemple).
            "base_model_id": base_model_id,
            "access_control": access_control,
            # Toujours une LISTE, jamais `None` : c'est cette valeur nulle qui faisait
            # répondre 500 au socle 0.11, sans rien dire dans le corps de la réponse.
            "access_grants": access_grants or [],
            "is_active": True,
        }
        body = fusionner_fiche(existante, body, description=description, system_prompt=system_prompt,
                               suggestions_fournies=suggestion_prompts is not None)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Update first — succeeds only if the model already exists.
            # OWUI v0.8.12 returns 401 (not 404) on update for missing
            # models; we used to raise here, but that broke first-time
            # publication. Treat update as best-effort and fall through to
            # create for *any* non-success status.
            upd = await client.post(
                f"{self.base_url}/api/v1/models/model/update",
                params={"id": model_id},
                json=body,
                headers=self._headers(),
            )
            if upd.is_success:
                return upd.json()

            cre = await client.post(
                f"{self.base_url}/api/v1/models/create",
                json=body,
                headers=self._headers(),
            )
            if cre.status_code in (401, 403):
                # Both calls hit a real auth failure — the key truly lacks
                # the required role.
                raise PermissionError(
                    f"OWUI a rejete la cle admin (HTTP {cre.status_code}). "
                    f"Reponse: {cre.text[:300]}. URL: {cre.request.url}."
                )
            if not cre.is_success:
                raise RuntimeError(
                    f"OWUI create/update echoue — update HTTP {upd.status_code}: "
                    f"{upd.text[:200]} / create HTTP {cre.status_code}: "
                    f"{cre.text[:200]}"
                )
            return cre.json()

    async def delete_model(self, model_id: str) -> None:
        """Best-effort delete. OWUI versions differ, so try both shapes."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for method, path, json_body in (
                ("POST", "/api/v1/models/model/delete", {"id": model_id}),
                ("DELETE", f"/api/v1/models/{model_id}", None),
            ):
                resp = await client.request(
                    method, f"{self.base_url}{path}",
                    # L'identifiant est passé des deux façons : en paramètre de requête
                    # pour les socles récents, dans le corps pour les anciens.
                    params={"id": model_id},
                    headers=self._headers(),
                    json=json_body,
                )
                if resp.status_code == 401:
                    raise PermissionError("OWUI a rejete la cle admin lors de la depublication.")
                if resp.is_success or resp.status_code == 404:
                    return
