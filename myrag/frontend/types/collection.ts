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
  publication?: { state?: string; visibility?: string; alias_name?: string; targets?: string[] }
  [cle: string]: unknown
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
