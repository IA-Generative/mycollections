"""Open WebUI HTTP client — used by the publish flow to register/update
an OWUI Model entity that aliases an OpenRAG partition.

Pattern aligned with owuiapps-agents/src/lib/owui-admin-client.ts: a
single server-side `OWUI_ADMIN_API_KEY` (generated once by an OWUI admin
in Settings > Account > Cles API) is used for all model CRUD. The
published_by field on the Publication row keeps the audit trail of who
pressed the button on our side.

OWUI v0.8.12 endpoint shape:
- POST /api/v1/models/create         — create new model
- POST /api/v1/models/model/update   — update (id in body, not query)
- POST /api/v1/models/model/delete   — delete
- GET  /api/v1/models/model?id=…     — fetch one

All accept `Authorization: Bearer <admin_api_key>`.
"""

from __future__ import annotations

import httpx

from app.config import settings


class OwuiAdminUnavailable(RuntimeError):
    """Raised when OWUI_ADMIN_API_KEY isn't configured. The publish flow
    catches this and returns a helpful message to the UI rather than
    exposing the bare exception text.
    """


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

    async def upsert_model(
        self,
        model_id: str,
        name: str,
        description: str = "",
        base_model_id: str | None = None,
        system_prompt: str = "",
        access_control: dict | None = None,
        suggestion_prompts: list[str] | None = None,
    ) -> dict:
        """Create or update an OWUI Model.

        Mirrors owuiapps-agents' approach: try update first, fall back to
        create if the update fails (e.g. model doesn't exist yet).
        Idempotent on repeated calls with the same model_id.
        """
        body = {
            "id": model_id,
            "name": name,
            "meta": {
                "description": description or f"Collection MyRAG {model_id}",
                "profile_image_url": "/static/favicon.png",
                "suggestion_prompts": [
                    {"content": p} for p in (suggestion_prompts or [])
                ],
                "tags": [{"name": "Mes collections"}],
                "capabilities": {"vision": False, "usage": False, "citations": True},
            },
            "params": (
                {"system": system_prompt} if system_prompt else {}
            ),
            "base_model_id": base_model_id or model_id,
            "access_control": access_control,
            "is_active": True,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Update first — if the model exists this is a no-op creation-wise.
            upd = await client.post(
                f"{self.base_url}/api/v1/models/model/update",
                json=body,
                headers=self._headers(),
            )
            if upd.status_code in (401, 403):
                raise PermissionError(
                    f"OWUI a rejete la cle admin (HTTP {upd.status_code}). "
                    f"Reponse: {upd.text[:300]}. "
                    f"URL: {upd.request.url}."
                )
            if upd.is_success:
                return upd.json()

            # Any other status: try create. OWUI v0.8.12 returns 400 on
            # update for unknown models — we don't want to branch on exact
            # codes, so just fall through.
            cre = await client.post(
                f"{self.base_url}/api/v1/models/create",
                json=body,
                headers=self._headers(),
            )
            if cre.status_code == 401:
                raise PermissionError(
                    "OWUI a rejete la cle admin lors de la publication."
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
                    headers=self._headers(),
                    json=json_body,
                )
                if resp.status_code == 401:
                    raise PermissionError("OWUI a rejete la cle admin lors de la depublication.")
                if resp.is_success or resp.status_code == 404:
                    return
