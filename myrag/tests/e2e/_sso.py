"""Connexion au SSO (Keycloak, PKCE) depuis un navigateur sans écran.

Porté du parcours de la bêta, avec ses pièges déjà payés :
- `chez_le_sso` compare l'HÔTE, jamais une sous-chaîne : Keycloak ajoute `iss=https://sso…` à
  l'adresse de retour, et une page servie par l'application porte donc le nom du SSO ;
- `jeton_de_session` lit le jeton que l'application range elle-même dans `sessionStorage`
  (clé `oidc.user:*`) : interroger l'API avec, c'est faire exactement ce que fait l'interface ;
- `connexion` rend un verdict donné par l'API, pas par l'allure de la page : c'est le backend
  qui applique la restriction de groupe.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse


def chez_le_sso(url: str, sso_host: str) -> bool:
    """Sommes-nous SUR le fournisseur d'identité, ou seulement en train d'en parler ?"""
    return bool(sso_host) and urlparse(url).netloc == sso_host


def sso_en_adresse_privee(sso_host: str) -> tuple[bool, str | None]:
    """Un poste sous VPN résout parfois le SSO vers une adresse privée : une page servie en
    public n'a alors pas le droit de l'appeler. Le service n'est pas en cause."""
    try:
        adresse = socket.gethostbyname(sso_host)
    except OSError:
        return False, None
    return ipaddress.ip_address(adresse).is_private, adresse


_JETON_JS = """() => {
    for (let i = 0; i < sessionStorage.length; i++) {
        const cle = sessionStorage.key(i);
        if (!cle.startsWith('oidc.user:')) continue;
        try { return JSON.parse(sessionStorage.getItem(cle)).access_token; }
        catch (e) { return null; }
    }
    return null;
}"""


def jeton_de_session(page) -> str | None:
    """Le jeton d'accès courant, tel que l'application l'envoie à l'API (suit le renouvellement)."""
    return page.evaluate(_JETON_JS)


def _apercu(page) -> str:
    return re.sub(r"\s+", " ", page.locator("body").inner_text()[:180])


def connexion(navigateur, base: str, sso_host: str, identifiant: str, motdepasse: str,
              chemin: str = "/"):
    """Ouvre un contexte neuf, va sur `chemin`, passe le SSO, et rend (issue, détail, contexte).

    `issue` vaut `entre` (détail = le jeton), `refuse`, `poste-sous-vpn`, `sso-bloque` ou
    `anomalie`. Le contexte est rendu dans tous les cas : à l'appelant de le fermer.
    """
    contexte = navigateur.new_context(locale="fr-FR", viewport={"width": 1280, "height": 800})
    page = contexte.new_page()
    try:
        page.goto(f"{base}{chemin}", wait_until="networkidle", timeout=45_000)

        if not chez_le_sso(page.url, sso_host):
            # L'application part d'elle-même vers le SSO ; si elle propose un bouton, on le
            # pousse, mais seulement après lui avoir laissé le temps de démarrer.
            page.wait_for_timeout(2_500)
            bouton = page.get_by_role("button", name=re.compile("connect|connexion", re.I))
            if bouton.count():
                bouton.first.click()
            try:
                page.wait_for_url(lambda u: chez_le_sso(u, sso_host), timeout=25_000)
            except Exception:
                prive, adresse = sso_en_adresse_privee(sso_host)
                if prive:
                    return ("poste-sous-vpn",
                            f"le SSO résout vers l'adresse privée {adresse} depuis ce poste ; "
                            "rejouer hors VPN", contexte)
                return "anomalie", f"pas de départ vers le SSO ({page.url}) : {_apercu(page)}", contexte

        # Thème DSFR de Keycloak : l'identifiant du champ change à chaque rendu, l'attribut
        # `name`, lui, ne bouge pas.
        champ = page.locator("input[name=username]")
        champ.wait_for(state="visible", timeout=30_000)
        champ.fill(identifiant)
        page.locator("input[name=password]").fill(motdepasse)
        page.locator("#kc-login, button[type=submit]").first.click()
        page.wait_for_load_state("networkidle", timeout=45_000)
        page.wait_for_timeout(3_000)

        if chez_le_sso(page.url, sso_host):
            return "sso-bloque", f"le SSO demande une action : {_apercu(page)}", contexte

        jeton = jeton_de_session(page)
        if not jeton:
            return "refuse", "aucun jeton en session après le retour du SSO", contexte

        reponse = page.request.get(f"{base}/api/collections",
                                   headers={"Authorization": f"Bearer {jeton}"})
        if reponse.status == 403:
            return "refuse", "403 de l'API : groupe requis absent du jeton", contexte
        if reponse.status != 200:
            return "anomalie", f"l'API répond {reponse.status} sur /api/collections ({reponse.text()[:100]})", contexte
        return "entre", jeton, contexte
    except Exception:
        contexte.close()
        raise
