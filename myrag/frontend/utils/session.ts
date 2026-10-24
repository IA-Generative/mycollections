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
