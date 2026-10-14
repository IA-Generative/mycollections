/**
 * Configuration lue AU DÉMARRAGE dans `/config.json` (monté par le déploiement).
 *
 * Le frontal est un site statique (`nuxt generate`, ssr:false) : sans ce fichier, les adresses
 * du SSO et de l'API seraient gravées dans le bundle, et il faudrait une image par
 * environnement. Avec lui, la même image sert la bêta et chaque preview.
 *
 * Fichier absent ou illisible : on garde la configuration de construction (dev local, compose).
 */

export interface ConfigPublique {
  myragApiUrl: string
  appTitle: string
  keycloakUrl: string
  keycloakRealm: string
  keycloakClientId: string
  authEnabled: boolean
}

const CHAINES = ['myragApiUrl', 'appTitle', 'keycloakUrl', 'keycloakRealm', 'keycloakClientId'] as const

/**
 * Ne retient du fichier que les clés connues, au bon type. Une adresse de SSO doit être en
 * https (ou http sur localhost) ; une URL d'API vide veut dire « même origine ».
 */
export function lireConfigExecution(brut: unknown): Partial<ConfigPublique> {
  if (!brut || typeof brut !== 'object' || Array.isArray(brut)) return {}
  const source = brut as Record<string, unknown>
  const retenu: Partial<ConfigPublique> = {}
  for (const cle of CHAINES) {
    const v = source[cle]
    if (typeof v === 'string') retenu[cle] = v.trim()
  }
  if (typeof source.authEnabled === 'boolean') retenu.authEnabled = source.authEnabled
  if (retenu.keycloakUrl !== undefined) {
    const url = retenu.keycloakUrl.replace(/\/+$/, '')
    if (!/^https:\/\/[^/]+/.test(url) && !/^http:\/\/(localhost|127\.0\.0\.1|host\.docker\.internal)(:\d+)?/.test(url)) {
      delete retenu.keycloakUrl
    } else {
      retenu.keycloakUrl = url
    }
  }
  for (const cle of ['keycloakRealm', 'keycloakClientId', 'appTitle'] as const) {
    if (retenu[cle] === '') delete retenu[cle]
  }
  return retenu
}
