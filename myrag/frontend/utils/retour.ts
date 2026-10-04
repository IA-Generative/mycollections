/**
 * La page où revenir après la connexion au SSO.
 *
 * Avant : le retour du SSO menait toujours à « / » — un lien partagé (une collection, le guide)
 * atterrissait sur l'accueil. On garde l'adresse demandée dans l'état OIDC, et on ne la rejoue
 * que si c'est un chemin INTERNE : jamais une adresse absolue ni « //hôte » (redirection ouverte).
 */
export function cheminDeRetour(valeur: unknown): string {
  if (typeof valeur !== 'string' || !valeur.startsWith('/') || valeur.startsWith('//') || valeur.startsWith('/\\')) return '/'
  if (/^\/auth\/callback\b/.test(valeur) || /^\/deconnexion\b/.test(valeur)) return '/'
  return valeur
}

export function adresseCourante(loc: { pathname: string; search: string; hash: string }): string {
  return cheminDeRetour(`${loc.pathname}${loc.search}${loc.hash}`)
}
