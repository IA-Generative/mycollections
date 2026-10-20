/**
 * Les assistants de recherche côté écran (lot B, B1) : libellés, état, formulaire de création,
 * fiche envoyée au serveur. Fonctions pures, testées dans tests/unit/assistants.test.ts. Le contrat
 * fait foi : `myrag/app/harnais/contrat.py` (FicheAssistant) ; le serveur reste seul juge des droits.
 */

export type Regime = 'toujours' | 'selon_question' | 'sur_consigne'
export type TypeSource = 'collection' | 'connecteur'
export type Canal = 'socle' | 'portail' | 'fenetre_js' | 'api'

export interface SourceFiche { id: string, type: TypeSource, regime: Regime, rang?: number | null }
export interface Canaux { socle: boolean, portail: boolean, fenetre_js: boolean, api: boolean }

export interface FicheAssistant {
  contrat: 1
  assistant: string
  titre: string
  rubrique: string | null
  description: string
  sources: SourceFiche[]
  consignes: unknown[]
  seuil_fiable: number
  validation_requise: boolean
  publication: Canaux
}

/** Même motif que IDENT_ASSISTANT du contrat. */
export const IDENT_ASSISTANT = /^[a-z0-9][a-z0-9._-]{2,63}$/

/** Les régimes, dits sans jargon : quand l'assistant interroge cette source. */
export const REGIMES: readonly { cle: Regime, libelle: string, aide: string }[] = [
  { cle: 'selon_question', libelle: 'Si la question s\'y rapporte', aide: 'L\'assistant l\'interroge quand la question ressemble à ce que la source contient.' },
  { cle: 'toujours', libelle: 'Toujours', aide: 'Interrogée pour chaque question.' },
  { cle: 'sur_consigne', libelle: 'Seulement si une consigne la cite', aide: 'Réservée aux cas que vous décrivez dans les consignes.' },
]

export function libelleRegime (r: Regime): string {
  return REGIMES.find(x => x.cle === r)?.libelle || r
}

/** Où l'assistant peut être servi, dit simplement. */
export const CANAUX: readonly { cle: Canal, libelle: string, aide: string }[] = [
  { cle: 'socle', libelle: 'Mon assistant', aide: 'Il apparaît dans la liste des modèles de Mon assistant.' },
  { cle: 'portail', libelle: 'Mon portail', aide: 'Ses réponses s\'affichent dans la recherche de Mon portail.' },
  { cle: 'fenetre_js', libelle: 'Une fenêtre sur un site', aide: 'Une ligne à coller dans une page intranet ouvre l\'assistant dans une fenêtre.' },
  { cle: 'api', libelle: 'L\'API', aide: 'D\'autres applications l\'interrogent, sur clé d\'API.' },
]

export const CANAUX_VIDES: Canaux = { socle: false, portail: false, fenetre_js: false, api: false }

export function canauxActifs (c: Partial<Canaux> | null | undefined): string[] {
  return CANAUX.filter(x => c?.[x.cle]).map(x => x.libelle)
}

/** « Brouillon » tant qu'aucune version n'est publiée, sinon « Version n ». */
export function etatAssistant (version: number | null | undefined): { libelle: string, classe: string } {
  return version ? { libelle: `Version ${version}`, classe: 'fr-badge--success' } : { libelle: 'Brouillon', classe: 'fr-badge--info' }
}

/** « 3 sources » ; et, si le serveur en a masqué (illisibles pour vous), « dont 1 que vous ne voyez pas ». */
export function resumeSources (visibles: number, masquees: number): string {
  const total = visibles + masquees
  const base = `${total} source${total > 1 ? 's' : ''}`
  return masquees ? `${base}, dont ${masquees} que vous ne pouvez pas lire` : base
}

export interface FormulaireAssistant {
  titre: string
  identifiant: string
  description: string
  rubrique: string
  sources: { id: string, regime: Regime }[]
}

/** Les erreurs du formulaire de création, par champ ; vide = prêt à envoyer. */
export function validerFormulaire (f: FormulaireAssistant): Record<string, string> {
  const e: Record<string, string> = {}
  if (!f.titre.trim()) {
    e.titre = 'Donnez un titre à l\'assistant.'
  }
  if (!IDENT_ASSISTANT.test(f.identifiant)) {
    e.identifiant = 'Minuscules, chiffres, tirets ou points, 3 à 64 caractères, en commençant par une lettre ou un chiffre.'
  }
  if (!f.sources.length) {
    e.sources = 'Choisissez au moins une collection.'
  }
  else if (f.sources.length > 20) {
    e.sources = 'Vingt sources au plus.'
  }
  if (f.description.length > 2000) {
    e.description = '2000 caractères au plus.'
  }
  return e
}

/** La fiche envoyée par `PUT /api/assistants/{id}` : le contrat, rien de plus. */
export function ficheDepuisFormulaire (f: FormulaireAssistant, publication: Canaux = CANAUX_VIDES): FicheAssistant {
  return {
    contrat: 1,
    assistant: f.identifiant,
    titre: f.titre.trim(),
    rubrique: f.rubrique || null,
    description: f.description.trim(),
    sources: f.sources.map((s, i) => ({ id: s.id, type: 'collection', regime: s.regime, rang: i + 1 })),
    consignes: [],
    seuil_fiable: 0.9,
    validation_requise: false,
    publication: { ...publication },
  }
}

const ECHAPPE_ATTRIBUT: Record<string, string> = { '&': '&amp;', '"': '&quot;', '<': '&lt;', '>': '&gt;' }
const A_ECHAPPER = /[&"<>]/g
const BARRES_FINALES = /\/+$/

/** La ligne à coller dans une page pour ouvrir l'assistant dans une fenêtre (canal `fenetre_js`). */
export function ligneFenetre (id: string, base: string): string {
  const b = base.replace(BARRES_FINALES, '').replace(A_ECHAPPER, c => ECHAPPE_ATTRIBUT[c]!)
  const i = id.replace(A_ECHAPPER, c => ECHAPPE_ATTRIBUT[c]!)
  return `<script src="${b}/fenetre.js" data-assistant="${i}" defer></script>`
}
