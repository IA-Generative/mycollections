/**
 * Piloter la qualité d'une collection : ce que les écrans affichent se calcule ici, en fonctions
 * pures testées (tests/unit/qualite.test.ts). Pendant serveur : app/services/mesure/verdict.py.
 */

export type Verdict = 'conforme' | 'partiel' | 'non_conforme' | 'refus_ok' | 'refus_ko' | 'sans_source' | 'erreur'
export type Origine = 'generee' | 'importee' | 'saisie' | 'avis' | 'amorce'

export interface Question {
  id: string
  question: string
  reponse: string
  origine: Origine
  persona: string
  relecture: 'brut' | 'valide' | 'rejete'
  hors_sujet: boolean
  fiable: boolean
  dernier_verdict: Verdict | null
  derniere_mesure_le: string | null
  contextes: { chunk_id: string, file_id: string, fichier: string, texte: string }[]
  commentaire: string
  must_cite: string[]
  tags: string[]
}

export interface Mesure {
  id: string
  etat: 'en_attente' | 'en_cours' | 'termine' | 'erreur'
  phase: string
  actif: boolean
  methode: 'judge' | 'similarite'
  nb_questions: number
  nb_traitees: number
  verdicts: Record<'conformes' | 'partielles' | 'non_conformes' | 'refus_ok' | 'refus_ko' | 'sans_source' | 'erreurs', number>
  score: number | null
  compteurs: { appels_chat: number, appels_llm: number, tokens_entree: number, tokens_sortie: number }
  duree_s: number | null
  erreur: string | null
  cree_le: string
}

const VERDICTS: Record<Verdict, [string, string]> = {
  conforme: ['Conforme', 'fr-badge--success'],
  partiel: ['Partielle', 'fr-badge--warning'],
  non_conforme: ['Non conforme', 'fr-badge--error'],
  refus_ok: ['Refus correct', 'fr-badge--success'],
  refus_ko: ['Réponse inventée', 'fr-badge--error'],
  sans_source: ['Aucun passage trouvé', 'fr-badge--warning'],
  erreur: ['Non mesurée (erreur)', ''],
}
const ORIGINES: Record<Origine, string> = {
  generee: 'Générée', importee: 'Importée', saisie: 'Saisie', avis: 'Avis d\'usager', amorce: 'Amorce',
}
const PHASES: Record<string, string> = {
  attente: "En attente d'une place", questions: 'Préparation', reponses: 'Les questions sont posées à la collection, le juge compare les réponses',
  synthese: 'Synthèse', fini: 'Terminée',
}

export const libelleVerdict = (v: string | null) => (v ? (VERDICTS[v as Verdict]?.[0] ?? v) : 'Jamais mesurée')
export const classeVerdict = (v: string | null) => (v ? (VERDICTS[v as Verdict]?.[1] ?? '') : '')
export const libelleOrigine = (o: string) => ORIGINES[o as Origine] ?? o
export const libellePhaseMesure = (p: string) => PHASES[p] ?? p

/** L'appréciation d'un score (mêmes seuils que le serveur). */
export function appreciation(score: number | null | undefined): { libelle: string, classe: string } {
  if (score === null || score === undefined) return { libelle: 'Non mesurée', classe: '' }
  if (score >= 80) return { libelle: 'Très bonne', classe: 'fr-badge--success' }
  if (score >= 60) return { libelle: 'Satisfaisante', classe: 'fr-badge--success' }
  if (score >= 40) return { libelle: 'À améliorer', classe: 'fr-badge--warning' }
  return { libelle: 'Insuffisante', classe: 'fr-badge--error' }
}

/** « 7 conformes · 1 partielle · 1 non conforme · hors sujet refusés 2/2 · 1 sans passage ». */
export function resumeVerdicts(v: Mesure['verdicts']): string {
  const p: string[] = []
  const n = (k: number, un: string, plusieurs: string) => `${k} ${k > 1 ? plusieurs : un}`
  if (v.conformes) p.push(n(v.conformes, 'conforme', 'conformes'))
  if (v.partielles) p.push(n(v.partielles, 'partielle', 'partielles'))
  if (v.non_conformes) p.push(n(v.non_conformes, 'non conforme', 'non conformes'))
  const hs = v.refus_ok + v.refus_ko
  if (hs) p.push(`hors sujet refusés ${v.refus_ok}/${hs}`)
  if (v.sans_source) p.push(n(v.sans_source, 'sans passage', 'sans passage'))
  if (v.erreurs) p.push(n(v.erreurs, 'en erreur', 'en erreur'))
  return p.join(' · ')
}

/** Une durée estimée pour mesurer n questions (≈ 6 s par question à 2 en parallèle). */
export function estimationMesure(n: number): string {
  if (n <= 0) return ''
  const s = Math.max(20, Math.round(n * 6 / 2))
  return s < 90 ? `≈ ${s} s` : `≈ ${Math.round(s / 60)} min`
}

/** Les points d'une courbe de tendance dans un cadre largeur × hauteur (marges comprises). */
export function pointsCourbe(scores: (number | null)[], largeur = 400, hauteur = 140, marge = 28): { x: number, y: number, score: number }[] {
  const vals = scores.map((s, i) => ({ s, i })).filter(p => p.s !== null) as { s: number, i: number }[]
  if (!vals.length) return []
  const pas = scores.length > 1 ? (largeur - 2 * marge) / (scores.length - 1) : 0
  return vals.map(({ s, i }) => ({
    x: Math.round(marge + (scores.length > 1 ? i * pas : (largeur - 2 * marge) / 2)),
    y: Math.round(hauteur - marge - (s / 100) * (hauteur - 2 * marge)),
    score: s,
  }))
}

/** Où mène une action suggérée par le serveur (onglet de la page Qualité, ou autre page). */
export function cibleAction(code: string, collection: string): { onglet?: string, lien?: string, filtre?: Record<string, string> } {
  switch (code) {
    case 'constituer_jeu': return { onglet: 'jeu' }
    case 'valider_questions': return { onglet: 'jeu', filtre: { relecture: 'brut' } }
    case 'lancer_mesure': return { onglet: 'mesures' }
    case 'corriger_echecs': return { onglet: 'jeu', filtre: { verdict: 'non_conforme' } }
    case 'redecouper': return { onglet: 'leviers' }
    case 'regle_de_garde': return { onglet: 'leviers' }
    case 'traiter_avis': return { onglet: 'avis' }
    default: return { lien: `/c/${collection}/qualite` }
  }
}

/** Ce que le volet conseille selon le verdict. */
export function conseils(verdict: string | null, horsSujet: boolean): string[] {
  if (horsSujet && verdict === 'refus_ko') return ['consignes']
  switch (verdict) {
    case 'non_conforme': return ['corriger', 'decoupage', 'consignes', 'fiable']
    case 'partiel': return ['corriger', 'decoupage', 'fiable']
    case 'sans_source': return ['decoupage', 'corriger']
    default: return []
  }
}

/** Le contenu d'un fichier importé : JSON (jeu ou export eval-rag) ou CSV « question;reponse ». */
export function lireImport(texte: string, nomFichier: string): { questions: Record<string, unknown>[] } | { erreur: string } {
  const t = (texte || '').replace(/^﻿/, '').trim()
  if (!t) return { erreur: 'Le fichier est vide.' }
  if (nomFichier.toLowerCase().endsWith('.csv')) {
    const lignes = t.split(/\r?\n/).filter(Boolean)
    const sep = (lignes[0].match(/;/g) || []).length >= (lignes[0].match(/,/g) || []).length ? ';' : ','
    const entete = lignes[0].split(sep).map(c => c.trim().toLowerCase().replace(/^"|"$/g, ''))
    const iq = entete.findIndex(c => c === 'question')
    const ir = entete.findIndex(c => ['reponse', 'réponse', 'answer', 'expected_answer'].includes(c))
    if (iq < 0) return { erreur: 'Le CSV doit avoir une colonne « question » (et de préférence « reponse »).' }
    const questions = lignes.slice(1).map((l) => {
      const c = l.split(sep).map(x => x.trim().replace(/^"|"$/g, ''))
      return { question: c[iq] || '', expected_answer: ir >= 0 ? (c[ir] || '') : '' }
    }).filter(q => q.question)
    return questions.length ? { questions } : { erreur: 'Aucune question trouvée dans le CSV.' }
  }
  try {
    const d = JSON.parse(t)
    const questions = Array.isArray(d) ? d : (d.questions || d.samples)
    if (!Array.isArray(questions) || !questions.length) return { erreur: 'Le JSON doit contenir une liste « questions » (ou « samples »).' }
    return { questions }
  } catch {
    return { erreur: 'Le fichier n\'est pas un JSON lisible.' }
  }
}

/** La règle ajoutée aux consignes quand une question hors sujet a reçu une réponse. */
export const REGLE_DE_GARDE = `

## Regle de garde
Si la question de l'utilisateur ne concerne pas le contenu de cette collection, reponds poliment que tu ne disposes pas d'informations sur ce sujet et invite l'utilisateur a reformuler sa question en lien avec le contenu de la collection.`

export const aLaRegleDeGarde = (consignes: string | null | undefined) => /r[eè]gle de garde/i.test(consignes || '')

/** Où en est un redécoupage : ses travaux d'indexation, finis ou non. */
export function avancementTravaux(travaux: { status: string, completed_at?: string, progress_pct?: number }[]): { finis: number, total: number, pct: number, echecs: number } {
  const FINIS = ['completed', 'done', 'failed', 'error', 'interrupted']
  const total = travaux.length
  const finis = travaux.filter(t => !!t.completed_at || FINIS.includes(t.status)).length
  const echecs = travaux.filter(t => ['failed', 'error', 'interrupted'].includes(t.status)).length
  const pct = total ? Math.round(travaux.reduce((s, t) => s + (FINIS.includes(t.status) || t.completed_at ? 100 : (t.progress_pct || 0)), 0) / total) : 0
  return { finis, total, pct, echecs }
}

/** Une date du serveur (UTC, souvent sans fuseau) en heure locale : « 14 oct., 15:02 ». */
export function dateMesure(iso: string | null | undefined, avecHeure = true): string {
  if (!iso) return ''
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('fr-FR', avecHeure ? { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' } : { day: 'numeric', month: 'short' })
}
