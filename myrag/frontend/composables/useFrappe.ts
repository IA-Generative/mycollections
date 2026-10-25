/**
 * La frappe simulée d'une question choisie (bac à sable, étape 4 de l'assistant) : le texte
 * s'écrit dans le champ, pour que la personne voie que son choix est pris en compte, puis part.
 * Sans animation si la personne a réduit les mouvements.
 */
import { etapesDeFrappe } from '~/utils/playground'

export function useFrappe (draft: Ref<string>) {
  const enFrappe = ref(false)
  const attendre = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))
  const mouvementReduit = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  async function taper (texte: string, avant?: () => void) {
    enFrappe.value = true
    try {
      avant?.()
      if (mouvementReduit()) {
        draft.value = texte
        return
      }
      for (const n of etapesDeFrappe(texte.length)) {
        draft.value = texte.slice(0, n)
        await attendre(18)
      }
      await attendre(250)
    }
    finally {
      enFrappe.value = false
    }
  }

  return { enFrappe, taper, mouvementReduit }
}
