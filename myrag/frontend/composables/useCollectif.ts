/**
 * Les appels du collectif — demandes, circuit d'une collection, amorces, guide.
 * Rien de calculé ici : les états viennent du serveur, l'écran les montre.
 */
export function useCollectif() {
  const { get, post, patch, del } = useApi()

  return {
    // demandes
    listerDemandes: (params?: Record<string, string>) => get('/api/demandes', params),
    lireDemande: (id: string) => get(`/api/demandes/${id}`),
    deposerDemande: (corps: any) => post('/api/demandes', corps),
    modifierDemande: (id: string, corps: any) => patch(`/api/demandes/${id}`, corps),
    soutenir: (id: string, role = 'soutien', temps?: number | null) =>
      post(`/api/demandes/${id}/soutenir`, { role, temps_declare_min: temps ?? null }),
    retirerSoutien: (id: string) => del(`/api/demandes/${id}/soutenir`),
    abonnerDemande: (id: string, oui: boolean) => (oui ? post(`/api/demandes/${id}/abonner`) : del(`/api/demandes/${id}/abonner`)),
    journalDemande: (id: string, params?: Record<string, string>) => get(`/api/demandes/${id}/journal`, params),
    cloreDemande: (id: string, corps: any) => post(`/api/demandes/${id}/clore`, corps),
    // collection
    etat: (n: string) => get(`/api/collections/${n}/etat`),
    changerEtat: (n: string, cible: string, forcer = false, motif = '') =>
      post(`/api/collections/${n}/etat`, { cible, forcer, motif }),
    grille: (n: string) => get(`/api/collections/${n}/grille`),
    majGrille: (n: string, corps: any) => fetchPut(`/api/collections/${n}/grille`, corps),
    relire: (n: string) => post(`/api/collections/${n}/grille/relire`),
    propositions: (n: string) => get(`/api/collections/${n}/propositions`),
    proposer: (n: string, corps: any) => post(`/api/collections/${n}/propositions`, corps),
    lireProposition: (n: string, id: string) => get(`/api/collections/${n}/propositions/${id}`),
    publierProposition: (n: string, id: string) => post(`/api/collections/${n}/propositions/${id}/publier`),
    refuserProposition: (n: string, id: string, motif: string) => post(`/api/collections/${n}/propositions/${id}/refuser`, { motif }),
    signalements: (n: string) => get(`/api/collections/${n}/signalements`),
    signaler: (n: string, corps: any) => post(`/api/collections/${n}/signalements`, corps),
    traiterSignalement: (n: string, id: string, etat: string) => post(`/api/collections/${n}/signalements/${id}/traiter`, { etat }),
    journalCollection: (n: string, params?: Record<string, string>) => get(`/api/collections/${n}/journal`, params),
    abonnerCollection: (n: string, oui: boolean) => (oui ? post(`/api/collections/${n}/abonner`) : del(`/api/collections/${n}/abonner`)),
    // amorces et guide
    amorces: () => get('/api/amorces'),
    importerAmorce: (id: string) => post(`/api/amorces/${id}/import`),
    guide: () => get('/api/guide'),
    pageGuide: (slug: string) => get(`/api/guide/${slug}`),
  }

  async function fetchPut(path: string, body: any) {
    // useApi n'a pas de PUT : même en-têtes, même renouvellement.
    const { baseUrl } = useApi()
    const { getAccessToken, renewToken } = useAuth()
    const faire = () => fetch(`${baseUrl}${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}) },
      body: JSON.stringify(body),
    })
    let r = await faire()
    if (r.status === 401 && (await renewToken())) r = await faire()
    if (!r.ok) throw new Error(`API error ${r.status}: ${await r.text()}`)
    return r.json()
  }
}
