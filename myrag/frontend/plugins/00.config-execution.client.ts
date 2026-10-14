import { lireConfigExecution } from '~/utils/configExecution'

// Avant tout autre plugin et avant le montage : l'authentification lit `keycloakUrl` dès
// l'ouverture de la page.
export default defineNuxtPlugin({
  name: 'config-execution',
  enforce: 'pre',
  parallel: false,
  async setup() {
    try {
      const reponse = await fetch('/config.json', { cache: 'no-store', credentials: 'omit' })
      if (!reponse.ok) return
      const lu = lireConfigExecution(await reponse.json())
      Object.assign(useRuntimeConfig().public, lu)
    } catch {
      // Fichier absent ou invalide : la configuration de construction reste en place.
    }
  },
})
