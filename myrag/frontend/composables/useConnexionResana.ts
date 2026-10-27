/**
 * « Se connecter à Résana » ouvre la page de connexion de Résana dans une autre fenêtre : Résana ne
 * sait ni la refermer ni prévenir Mes collections. Ce composable s'en charge : il ouvre la fenêtre,
 * puis vérifie régulièrement (et dès qu'on revient sur l'onglet) si la session Résana est là ;
 * quand elle l'est, il referme la fenêtre qu'il a ouverte, dit « Connexion établie » et relance
 * ce que la personne voulait faire.
 */
export function useConnexionResana () {
  const { get } = useApi()
  /** On attend la connexion : la fenêtre Résana est ouverte. */
  const enAttente = ref(false)
  /** La connexion vient d'être établie : le message à montrer un instant. */
  const retablie = ref(false)
  let fenetre: Window | null = null
  let minuterie: ReturnType<typeof setInterval> | undefined
  let fin: ReturnType<typeof setTimeout> | undefined
  let apres: (() => void | Promise<void>) | undefined

  /** Une vérification est en cours : on n'en lance pas une autre par-dessus. */
  let verification = false

  /**
   * La session Résana répond-elle ? La liste des espaces SANS connexion automatique : avec elle,
   * chaque vérification (toutes les 4 s) ouvrait un navigateur côté Résana, et ces navigateurs
   * étouffaient celui de la personne qui se connectait (bêta, 2026-10-27).
   */
  async function sessionOuverte (): Promise<boolean> {
    try {
      await get('/api/sources/resana/espaces?connexion=false')
      return true
    }
    catch {
      return false
    }
  }

  async function verifier () {
    if (!enAttente.value || verification) {
      return
    }
    verification = true
    let ouverte = false
    try {
      ouverte = await sessionOuverte()
    }
    finally {
      verification = false
    }
    if (!ouverte || !enAttente.value) {
      return
    }
    arreter()
    retablie.value = true
    try {
      fenetre?.close()
    }
    catch { /* une fenêtre déjà fermée, ou que le navigateur refuse de fermer : la personne la fermera */ }
    fenetre = null
    window.focus()
    await apres?.()
    setTimeout(() => {
      retablie.value = false
    }, 8000)
  }

  function surRetour () {
    if (document.visibilityState === 'visible') {
      verifier()
    }
  }

  function arreter () {
    enAttente.value = false
    clearInterval(minuterie)
    clearTimeout(fin)
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', surRetour)
      window.removeEventListener('focus', surRetour)
    }
  }

  /**
   * Ouvre la page de connexion et attend la session : `reprendre` est appelé dès qu'elle est là
   * (recharger les espaces, relancer la mise à jour…). L'attente s'arrête d'elle-même au bout de
   * dix minutes.
   */
  function ouvrir (url: string, reprendre?: () => void | Promise<void>) {
    arreter()
    apres = reprendre
    retablie.value = false
    enAttente.value = true
    // Sans `noopener` : c'est ce qui permet de refermer la fenêtre une fois la session ouverte.
    fenetre = window.open(url, 'resana-connexion')
    minuterie = setInterval(verifier, 4000)
    fin = setTimeout(arreter, 10 * 60 * 1000)
    document.addEventListener('visibilitychange', surRetour)
    window.addEventListener('focus', surRetour)
  }

  onBeforeUnmount(arreter)

  return { enAttente, retablie, ouvrir, arreter }
}
