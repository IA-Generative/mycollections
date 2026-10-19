/** Ce que rend GET /api/collections pour une collection (app/models/db.py, to_dict). */
export interface Collection {
  /** Identifiant technique : partition OpenRAG, modèle `openrag-<name>`, URL. */
  name: string
  /** Ce que lit une personne. Vide sur une partition sans fiche : voir titreDe(). */
  titre?: string
  /** Clé de la rubrique, ou null : « Non classées ». */
  categorie?: string | null
  description?: string
  strategy?: string
  sensitivity?: string
  scope?: string
  graph_enabled?: boolean
  etat_collab?: string | null
  contact_name?: string
  contact_email?: string
  source_type?: string
  file_count?: number
  orphan?: boolean
  archived_at?: string | null
  created_at?: string
  updated_at?: string
  /** La plus récente de `updated_at` et du dernier document déposé (catalogue). */
  derniere_mise_a_jour?: string | null
  /** L'avis des usagers (catalogue) : `satisfaction_rate` null sans avis. */
  avis?: AvisCollection
  /** Ce que l'appelant peut faire de la collection : l'interface n'offre que ces gestes. */
  mes_droits?: { lire: boolean, ecrire: boolean, garant: boolean, superadmin: boolean }
  publication?: { state?: string, visibility?: string, alias_name?: string, targets?: { app: string, model_id: string }[] }
  [cle: string]: unknown
}

export interface AvisCollection {
  total: number
  satisfaction_rate: number | null
}

export interface Categorie {
  cle: string
  libelle: string
  description: string
  ordre: number
  nb_collections?: number
}

/** Une section du catalogue : une rubrique et ses collections. `cle` null = « Non classées ». */
export interface GroupeDeCollections {
  cle: string | null
  libelle: string
  description: string
  collections: Collection[]
}
