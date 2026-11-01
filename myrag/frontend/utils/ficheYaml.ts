/**
 * La fiche d'un assistant en fichier YAML (docs/assistants.md, « Le fichier YAML ») : ce que l'écran
 * Consignes en calcule avant et après `GET|PUT /api/assistants/{id}/fiche.yaml`. Le serveur valide
 * le fichier ; l'écran ne fait que refuser tôt ce qui ne peut pas partir et dire ce qu'il répond.
 */
import { messageErreur } from './collectif'

/** Comme le serveur (`fiche_yaml.TAILLE_MAX`). */
export const TAILLE_MAX_FICHE_YAML = 64 * 1024
const EXTENSION_YAML = /\.ya?ml$/i
const ERREUR_API = /^API error \d+: (.*)$/s

export function nomFichierFiche (id: string): string {
  return `${id}.yaml`
}

/** Pourquoi ce fichier ne peut pas partir (extension, taille) ; null s'il le peut. */
export function refusFichierFiche (f: { name: string, size: number }): string | null {
  if (!EXTENSION_YAML.test(f.name)) {
    return 'Choisissez un fichier .yaml (celui que donne « Exporter le fichier »).'
  }
  if (f.size === 0) {
    return 'Ce fichier est vide.'
  }
  if (f.size > TAILLE_MAX_FICHE_YAML) {
    return `Ce fichier dépasse ${TAILLE_MAX_FICHE_YAML / 1024} Kio : une fiche d'assistant est bien plus courte.`
  }
  return null
}

export interface ErreurImport {
  message: string
  /** Une ligne par champ fautif : « consignes[2] (accord) › chercher[1] › source : … ». */
  erreurs: string[]
}

interface ErreurChamp {
  champ?: string
  message?: string
}

/** L'échec d'un import, lisible : le message et, pour un fichier invalide (422), une ligne par champ. */
export function erreurImport (e: unknown): ErreurImport {
  const brut = e instanceof Error ? e.message : String(e)
  const m = ERREUR_API.exec(brut)
  if (m) {
    try {
      const detail = JSON.parse(m[1]!).detail
      if (detail && typeof detail === 'object' && Array.isArray(detail.erreurs)) {
        return {
          message: typeof detail.message === 'string' ? detail.message : 'Le fichier n\'est pas une fiche d\'assistant valide.',
          erreurs: (detail.erreurs as ErreurChamp[]).map(x => (x.champ ? `${x.champ} : ${x.message ?? ''}` : String(x.message ?? ''))),
        }
      }
    }
    catch {}
  }
  return { message: messageErreur(e), erreurs: [] }
}

/** Ce que rend un import réussi (en plus de la fiche enregistrée). */
export interface ReponseImport {
  empreinte?: string
  avertissements?: string[]
}

export function bilanImport (r: ReponseImport): string {
  const emp = r.empreinte ? ` Empreinte : ${r.empreinte.slice(0, 12)}…` : ''
  return `Fichier importé dans le brouillon. Publiez pour en faire une version.${emp}`
}
