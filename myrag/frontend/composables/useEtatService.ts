/**
 * L'état du service, partagé par toutes les pages : le layout affiche le bandeau et la
 * fenêtre « État du service », les pages grisent ce qui dépend de la recherche. Une
 * seule minuterie pour toute l'application. Rien n'est affiché quand tout va bien.
 *
 * L'entrée « État du service » est rangée dans le menu personnel de la barre commune
 * (`window.MirAI.poserEntrees`, barre ≥ 1.13.0) : l'en-tête ne porte plus de voyants.
 */
import { computed, ref } from 'vue'
import { noterMesure, sondeInitiale, type Sonde } from '~/utils/etatService'

const PERIODE_MS = 30000
const DUREE_RETABLI_MS = 5000

const service = ref<Sonde>(sondeInitiale())
const recherche = ref<Sonde>(sondeInitiale())
const derniereVerification = ref<number | null>(null)
const verificationEnCours = ref(false)
/** Le détail technique de la dernière mesure — affiché aux seuls administrateurs. */
const detail = ref({ service: '', recherche: '' })
const retabli = ref(false)
const fenetreOuverte = ref(false)
let minuterie: ReturnType<typeof setInterval> | null = null
// Lue une fois, au démarrage : `useRuntimeConfig` n'est sûr que dans un contexte Nuxt,
// pas dans le rappel d'une minuterie.
let base = ''
let minuterieRetabli: ReturnType<typeof setTimeout> | null = null

const ICONE = 'svg:<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" ' +
  'stroke-width="2" aria-hidden="true"><path d="M3 12h4l3-8 4 16 3-8h4"/></svg>'

function publierEntreeMenu() {
  if (typeof window === 'undefined') return
  const enPanne = service.value.etat === 'ko' || recherche.value.etat === 'ko'
  const entrees = [{
    libelle: 'État du service',
    icone: ICONE,
    compte: enPanne ? '1 souci' : '',
    titre: enPanne ? 'Une partie du service est indisponible' : 'Voir ce qui fonctionne',
    action: () => { fenetreOuverte.value = true },
  }]
  const w = window as any
  // Deux portes (barre 1.13.0) : la fonction si la barre est déjà chargée, sinon la
  // déclaration qu'elle lira à son chargement.
  // Le titre est donné : la barre ne reconnaît le service que sur son adresse publique.
  const titreEntrees = 'Mes collections · avancé'
  w.MIRAI_MENU = Object.assign(w.MIRAI_MENU || {}, { entrees, titreEntrees })
  try { w.MirAI?.poserEntrees?.(entrees, { titre: titreEntrees }) } catch {}
}

async function mesurer(url: string, ms: number): Promise<{ ok: boolean, detail: string, data?: any }> {
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(ms) })
    if (!r.ok) return { ok: false, detail: `HTTP ${r.status}` }
    return { ok: true, detail: 'OK', data: await r.json().catch(() => ({})) }
  } catch {
    return { ok: false, detail: 'injoignable' }
  }
}

async function verifier() {
  if (verificationEnCours.value) return
  verificationEnCours.value = true
  const avant = service.value.etat === 'ko' || recherche.value.etat === 'ko'
  try {
    const [s, r] = await Promise.all([
      mesurer(`${base}/health`, 3000),
      // La recherche passe par le serveur de Mes collections (le navigateur ne joint pas
      // le moteur directement).
      mesurer(`${base}/api/openrag/health`, 5000),
    ])
    const rechercheOk = r.ok && r.data?.status === 'up'
    const maintenant = Date.now()
    service.value = noterMesure(service.value, s.ok, maintenant)
    recherche.value = noterMesure(recherche.value, rechercheOk, maintenant)
    detail.value = {
      service: s.ok ? `MyRAG ${s.data?.version || ''} — OK` : `MyRAG — ${s.detail}`,
      recherche: rechercheOk ? 'OpenRAG — OK' : `OpenRAG — ${r.ok ? 'injoignable depuis MyRAG' : r.detail}`,
    }
    derniereVerification.value = maintenant
  } finally {
    verificationEnCours.value = false
  }
  const apres = service.value.etat === 'ko' || recherche.value.etat === 'ko'
  if (avant && !apres) {
    retabli.value = true
    if (minuterieRetabli) clearTimeout(minuterieRetabli)
    minuterieRetabli = setTimeout(() => { retabli.value = false }, DUREE_RETABLI_MS)
  } else if (apres) {
    retabli.value = false
  }
  if (avant !== apres) publierEntreeMenu()
}

export function useEtatService() {
  function demarrer() {
    if (minuterie) return
    base = useRuntimeConfig().public.myragApiUrl
    publierEntreeMenu()
    verifier()
    minuterie = setInterval(verifier, PERIODE_MS)
  }
  return {
    service,
    recherche,
    detail,
    derniereVerification,
    verificationEnCours,
    retabli,
    fenetreOuverte,
    /** Tout Mes collections ne répond plus. */
    serviceIndisponible: computed(() => service.value.etat === 'ko'),
    /** Poser une question ou ajouter des documents est impossible pour l'instant. */
    rechercheIndisponible: computed(() => service.value.etat === 'ko' || recherche.value.etat === 'ko'),
    verifier,
    demarrer,
  }
}
