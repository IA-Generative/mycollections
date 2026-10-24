/**
 * La session qui expire : un appel refusé (401) se rejoue une fois après un renouvellement
 * silencieux du jeton ; si le renouvellement échoue, la session est finie (le SSO ne renouvelle
 * plus : session Keycloak expirée, inactivité). L'écran doit alors le dire et proposer de se
 * reconnecter, au lieu de laisser travailler sur des appels qui échouent tous.
 * Fonction pure, testée dans tests/unit/session.test.ts.
 */

export const MESSAGE_SESSION_EXPIREE = 'Votre session a expiré : reconnectez-vous pour continuer.'

/**
 * Faire l'appel ; sur un 401, renouveler le jeton et le refaire une fois. Si le renouvellement
 * échoue, `expiree()` est appelée (une seule fois par appel) et la réponse 401 est rendue telle
 * quelle. Un 401 malgré un renouvellement réussi n'est PAS une expiration (le service refuse pour
 * une autre raison) : rien n'est signalé.
 */
export async function avecRenouvellement (
  faire: () => Promise<Response>,
  renouveler: () => Promise<boolean>,
  expiree: () => void,
): Promise<Response> {
  const premiere = await faire()
  if (premiere.status !== 401) {
    return premiere
  }
  if (!(await renouveler())) {
    expiree()
    return premiere
  }
  return faire()
}

/** Le contenu (non vérifié) d'un jeton JWT ; null s'il n'en est pas un. */
export function contenuJwt (jeton: string | null | undefined): Record<string, unknown> | null {
  const partie = (jeton || '').split('.')[1]
  if (!partie) {
    return null
  }
  try {
    const b64 = partie.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(partie.length / 4) * 4, '=')
    const brut = JSON.parse(atob(b64))
    return brut && typeof brut === 'object' ? brut : null
  }
  catch {
    return null
  }
}

/**
 * Dans combien de millisecondes renouveler la session, pour qu'elle reste ouverte tant que la page
 * l'est. Le SSO de la bêta donne un jeton d'accès de 15 min mais un jeton de rafraîchissement de
 * 10 min (inactivité de la session) : renouveler à l'approche de la fin du jeton d'ACCÈS, comme le
 * fait la bibliothèque, arrivait trop tard — la session était déjà close. On renouvelle donc avant
 * la PREMIÈRE des deux échéances, avec une marge. Échéances en secondes (claims `exp`), `maintenant`
 * en millisecondes ; jamais moins de `plancher` ms ; null si aucune échéance n'est connue.
 */
export function delaiAvantRenouvellement (
  maintenant: number,
  accesExp: number | null | undefined,
  rafraichissementExp: number | null | undefined,
  marge = 90,
  plancher = 5000,
): number | null {
  const echeances = [accesExp, rafraichissementExp].filter((e): e is number => typeof e === 'number' && e > 0)
  if (!echeances.length) {
    return null
  }
  return Math.max(plancher, (Math.min(...echeances) - marge) * 1000 - maintenant)
}
