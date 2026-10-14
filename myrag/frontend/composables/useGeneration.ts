/**
 * Les appels de la génération de questions (onglet « Questions générées »).
 * Rien de calculé ici : les états viennent du serveur ; les libellés, de utils/generation.ts.
 */
import { nomFichierExport } from '~/utils/generation'

export function useGeneration() {
  const { get, post, patch, del, baseUrl, fetchWithAuth } = useApi()
  const racine = (n: string) => `/api/collections/${encodeURIComponent(n)}/generation`

  async function exporter(n: string, runId: string, format: 'json' | 'csv') {
    const r = await fetchWithAuth(`${baseUrl}${racine(n)}/runs/${runId}/export?format=${format}`)
    if (!r.ok) throw new Error(`API error ${r.status}: ${await r.text()}`)
    const blob = await r.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = nomFichierExport(n, runId, format)
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(a.href), 1000)
  }

  return {
    etat: (n: string) => get(racine(n)),
    personas: (n: string) => get(`${racine(n)}/personas`),
    creerPersona: (n: string, corps: { nom: string, description_role: string }) => post(`${racine(n)}/personas`, corps),
    modifierPersona: (n: string, id: string, corps: Partial<{ nom: string, description_role: string }>) => patch(`${racine(n)}/personas/${id}`, corps),
    supprimerPersona: (n: string, id: string) => del(`${racine(n)}/personas/${id}`),
    lancer: (n: string, corps: { personas: string[], taille: number, distribution?: Record<string, number> }) => post(`${racine(n)}/runs`, corps),
    runs: (n: string) => get(`${racine(n)}/runs`),
    run: (n: string, id: string) => get(`${racine(n)}/runs/${id}`),
    supprimerRun: (n: string, id: string) => del(`${racine(n)}/runs/${id}`),
    paires: (n: string, id: string, params?: Record<string, string>) => get(`${racine(n)}/runs/${id}/paires`, params),
    relire: (n: string, id: string, corps: { relecture: string, commentaire?: string }) => patch(`${racine(n)}/paires/${id}`, corps),
    exporter,
  }
}
