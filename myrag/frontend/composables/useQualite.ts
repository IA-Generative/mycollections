/**
 * Les appels de la page Qualité et de l'étape 4 de l'assistant (docs/qualite.md).
 * Rien de calculé ici : les états viennent du serveur ; les libellés, de utils/qualite.ts.
 */
export function useQualite(collection: string) {
  const { get, post, patch, del, baseUrl, fetchWithAuth } = useApi()
  const racine = `/api/collections/${encodeURIComponent(collection)}/qualite`

  async function exporter(format: 'json' | 'csv') {
    const r = await fetchWithAuth(`${baseUrl}${racine}/questions/export?format=${format}`)
    if (!r.ok) throw new Error(`API error ${r.status}: ${await r.text()}`)
    const a = document.createElement('a')
    a.href = URL.createObjectURL(await r.blob())
    a.download = `${collection}-jeu-de-questions.${format}`
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(a.href), 1000)
  }

  return {
    synthese: () => get(racine),
    questions: (params?: Record<string, string>) => get(`${racine}/questions`, params),
    question: (id: string) => get(`${racine}/questions/${id}`),
    creer: (corps: Record<string, unknown>) => post(`${racine}/questions`, corps),
    importer: (questions: unknown[], origine: 'importee' | 'generee' = 'importee') => post(`${racine}/questions/import`, { questions, origine }),
    modifier: (id: string, corps: Record<string, unknown>) => patch(`${racine}/questions/${id}`, corps),
    supprimer: (id: string) => del(`${racine}/questions/${id}`),
    tester: (id: string) => post(`${racine}/questions/${id}/tester`, {}),
    depuisAvis: (feedbackId: number, reponse: string) => post(`${racine}/questions/depuis-avis/${feedbackId}`, { reponse }),
    mesurer: (corps: Record<string, unknown> = {}) => post(`${racine}/mesures`, corps),
    mesures: () => get(`${racine}/mesures`),
    mesure: (id: string) => get(`${racine}/mesures/${id}`),
    resultats: (id: string, params?: Record<string, string>) => get(`${racine}/mesures/${id}/resultats`, params),
    supprimerMesure: (id: string) => del(`${racine}/mesures/${id}`),
    avis: (params?: Record<string, string>) => get(`/api/feedback/${encodeURIComponent(collection)}`, params),
    marquerLu: (id: number) => patch(`/api/feedback/${encodeURIComponent(collection)}/${id}/review`, { status: 'reviewed' }),
    exporter,
  }
}
