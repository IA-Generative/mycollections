/**
 * Télécharger un fichier servi derrière l'authentification (export CSV, JSON…) : l'appel porte le
 * jeton, la réponse devient un fichier que le navigateur enregistre sous `nom`.
 */
export function useTelechargement () {
  const { baseUrl, fetchWithAuth } = useApi()

  async function telecharger (chemin: string, nom: string) {
    const r = await fetchWithAuth(`${baseUrl}${chemin}`)
    if (!r.ok) {
      throw new Error(`API error ${r.status}: ${await r.text()}`)
    }
    const a = document.createElement('a')
    a.href = URL.createObjectURL(await r.blob())
    a.download = nom
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(a.href), 1000)
  }

  return { telecharger }
}
