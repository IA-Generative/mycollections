"""Suite Numerique Drive connector.

Ported from /Users/etiquet/Documents/GitHub/openrag/openrag/components/connectors/drive.py
and adapted to the BaseConnector interface used by mycollections. The client
talks to the Drive REST API (/api/v1.0/items/*) with a Bearer OIDC access
token minted server-side via client_credentials on Keycloak.
"""

from __future__ import annotations

import httpx

from app.services.connectors.base import BaseConnector, DocumentInfo


def _entetes(access_token: str, public_host: str | None) -> dict:
    """En-têtes d'appel à Drive.

    Quand on joint Drive par son SERVICE INTERNE — ce qui est la règle dans un cluster
    partagé, l'adresse publique n'y répondant qu'une fois sur deux — deux en-têtes sont
    indispensables, et leur absence ne produit aucun message exploitable :

    · ``Host`` : Drive est un Django dont la liste d'hôtes autorisés ne contient que son
      nom public. Un appel au nom du service reçoit un « Bad Request (400) » en HTML nu,
      sans un mot d'explication.
    · ``X-Forwarded-Proto`` : sans lui, Drive se croit appelé en clair et répond 301 vers
      son adresse publique — l'appelant y court, et retombe précisément sur l'adresse
      qu'on cherchait à éviter.
    """
    entetes = {"Authorization": f"Bearer {access_token}"}
    if public_host:
        entetes["Host"] = public_host
        entetes["X-Forwarded-Proto"] = "https"
    return entetes


class DriveClient:
    """Thin async HTTP client for the Suite Numerique Drive API."""

    def __init__(self, base_url: str, access_token: str, timeout: float = 30.0,
                 public_host: str | None = None):
        self.base_url = base_url.rstrip("/")
        # IMPORTANT: /external_api/v1.0/ — the OIDC-RS protected variant.
        # /api/v1.0/ requires a session cookie (user login) and would 500
        # on Bearer-token calls from a service account.
        self._client = httpx.AsyncClient(
            base_url=f"{self.base_url}/external_api/v1.0",
            headers=_entetes(access_token, public_host),
            timeout=timeout,
            follow_redirects=True,
        )

    async def list_children(self, folder_id: str, page: int = 1) -> dict:
        resp = await self._client.get(
            f"/items/{folder_id}/children/", params={"page": page}
        )
        resp.raise_for_status()
        return resp.json()

    async def get_item(self, item_id: str) -> dict:
        resp = await self._client.get(f"/items/{item_id}/")
        resp.raise_for_status()
        return resp.json()

    async def download(self, item_id: str) -> tuple[bytes, str]:
        """Return (content_bytes, filename). Filename from Content-Disposition
        header, fallback to a synthesized name."""
        resp = await self._client.get(f"/items/{item_id}/download/")
        resp.raise_for_status()
        cd = resp.headers.get("content-disposition", "")
        filename = ""
        if "filename=" in cd:
            filename = cd.split("filename=", 1)[1].strip().strip('"').strip("'")
        if not filename:
            filename = f"drive_{item_id}"
        return resp.content, filename

    async def close(self):
        await self._client.aclose()


class DriveConnector(BaseConnector):
    """BaseConnector implementation backed by Suite Numerique Drive."""

    def __init__(self, base_url: str, access_token: str, folder_id: str,
                 public_host: str | None = None):
        self.client = DriveClient(base_url, access_token, public_host=public_host)
        self.folder_id = folder_id
        self.base_url = base_url.rstrip("/")

    async def list_documents(self) -> list[DocumentInfo]:
        return [item async for item in self._iter_files(self.folder_id, recursive=True)]

    async def fetch_document(self, doc_id: str) -> tuple[bytes, str]:
        return await self.client.download(doc_id)

    async def check_updates(self, since: str) -> list[DocumentInfo]:
        """Return documents whose updated_at is >= `since` (ISO-8601 string
        comparison — works because ISO-8601 is lexicographically ordered)."""
        if not since:
            return await self.list_documents()
        return [
            doc
            async for doc in self._iter_files(self.folder_id, recursive=True)
            if doc.updated_at and doc.updated_at >= since
        ]

    async def _iter_files(self, folder_id: str, recursive: bool):
        page = 1
        while True:
            data = await self.client.list_children(folder_id, page=page)
            results = data.get("results", []) if isinstance(data, dict) else data
            if not results:
                break

            for raw in results:
                item_type = (raw.get("type") or "FILE").upper()
                if item_type == "FILE":
                    yield DocumentInfo(
                        id=raw["id"],
                        title=raw.get("title", "") or raw.get("filename", ""),
                        source_type="drive",
                        url=f"{self.base_url}/items/{raw['id']}",
                        size=raw.get("size", 0) or 0,
                        mime_type=raw.get("mimetype", "") or "",
                        updated_at=raw.get("updated_at", "") or "",
                        metadata={"drive_id": raw["id"]},
                    )
                elif recursive and item_type == "FOLDER":
                    async for sub in self._iter_files(raw["id"], recursive=True):
                        yield sub

            if not data.get("next"):
                break
            page += 1

    async def close(self):
        await self.client.close()
