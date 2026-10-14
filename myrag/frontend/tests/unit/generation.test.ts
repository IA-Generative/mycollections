import { describe, expect, it } from 'vitest'
import {
  bilanRelecture, dureeLisible, libelleEtatRun, libelleModele, libellePhase, libelleRelecture, libelleStyle, nombreCourt,
  nomFichierExport, pairesVersJeu, progressionRun, resumeCout, validerPersona, EXEMPLES_PERSONAS, HORS_SUJET,
  PERSONNA_DEFAUT,
} from '../../utils/generation'

const COMPTEURS = { appels_llm: 195, tokens_entree: 190_400, tokens_sortie: 24_900, reparations_json: 3, inachevees: 0, erreurs_llm: 0, appels_embeddings: 0 }

describe('libellés', () => {
  it('dit les états, phases, relectures et styles en français', () => {
    expect(libelleEtatRun('termine')).toBe('Terminée')
    expect(libellePhase('extraction')).toBe('Repérage des sujets de chaque passage')
    expect(libelleRelecture('rejete')).toBe('Rejetée')
    expect(libelleStyle('MISSPELLED')).toBe('avec des fautes')
    expect(libelleEtatRun('inconnu')).toBe('inconnu')
    expect(libelleModele('chat')).toBe('chat')
    expect(libelleModele('')).toBe('celui du serveur')  // sans nom de modèle : le serveur en aval choisit
  })
})

describe('durées et nombres', () => {
  it('rend une durée lisible', () => {
    expect(dureeLisible(42)).toBe('42 s')
    expect(dureeLisible(190)).toBe('3 min 10 s')
    expect(dureeLisible(3720)).toBe('1 h 02 min')
    expect(dureeLisible(null)).toBe('')
  })
  it('abrège les grands nombres', () => {
    expect(nombreCourt(950)).toBe('950')
    expect(nombreCourt(215_300)).toBe('215 k')
    expect(nombreCourt(2_400_000)).toBe('2,4 M')
  })
})

describe('resumeCout', () => {
  it('dit appels, jetons, réparations et durée', () => {
    expect(resumeCout({ compteurs: COMPTEURS, duree_s: 290 }))
      .toBe('195 appels au modèle · 215 k jetons (190 k lus, 25 k écrits) · 3 réponses mal formées réparées · 4 min 50 s')
  })
  it('dit les refus de quota de la passerelle', () => {
    expect(resumeCout({ compteurs: { ...COMPTEURS, reparations_json: 0, erreurs_llm: 3, refus_debit: 2 }, duree_s: 5 }))
      .toBe('195 appels au modèle · 215 k jetons (190 k lus, 25 k écrits) · 3 erreurs du modèle (dont 2 refus de quota) · 5 s')
  })
  it('accorde au singulier et tait ce qui vaut zéro', () => {
    expect(resumeCout({ compteurs: { ...COMPTEURS, appels_llm: 1, tokens_entree: 10, tokens_sortie: 2, reparations_json: 0 }, duree_s: null }))
      .toBe('1 appel au modèle · 12 jetons (10 lus, 2 écrits)')
  })
})

describe('progressionRun', () => {
  const base = { etat: 'en_cours' as const, morceaux_envoyes: 100, taille: 20, compteurs: { ...COMPTEURS, appels_llm: 0 } }
  it('avance avec la phase et les appels', () => {
    expect(progressionRun({ ...base, phase: 'lecture' })).toBe(5)
    expect(progressionRun({ ...base, phase: 'extraction', compteurs: { ...COMPTEURS, appels_llm: 50 } })).toBe(35)
    expect(progressionRun({ ...base, phase: 'generation', compteurs: { ...COMPTEURS, appels_llm: 120 } })).toBe(78)
    expect(progressionRun({ ...base, phase: 'generation', compteurs: { ...COMPTEURS, appels_llm: 900 } })).toBe(95)
  })
  it('reste borné et finit à 100', () => {
    expect(progressionRun({ ...base, phase: 'extraction', compteurs: { ...COMPTEURS, appels_llm: 10_000 } })).toBe(60)
    expect(progressionRun({ ...base, etat: 'erreur', phase: 'extraction' })).toBe(100)
  })
})

describe('validerPersona', () => {
  it('exige un nom unique et un contexte décrit', () => {
    expect(validerPersona({ nom: '', description_role: 'court' })).toEqual({
      nom: 'Donnez un nom au persona.',
      description_role: 'Décrivez qui pose la question et dans quelle situation (une phrase au moins).',
    })
    expect(validerPersona({ nom: 'agent', description_role: 'x'.repeat(30) }, ['Agent']).nom).toBe('Un persona porte déjà ce nom.')
  })
  it('accepte les exemples proposés', () => {
    for (const e of EXEMPLES_PERSONAS) expect(validerPersona(e)).toEqual({})
  })
  it('accepte le persona créé d’office par l’assistant de création', () => {
    expect(validerPersona(PERSONNA_DEFAUT)).toEqual({})
  })
})

describe('pairesVersJeu', () => {
  const paires = [
    { id: 'a', question: 'Quelle procedure suivre ?', reponse: 'Deposer une demande.', persona: 'Agent', relecture: 'brut' },
    { id: 'b', question: 'Quel delai ?', reponse: 'Trois mois.', persona: 'RH', relecture: 'valide' },
    { id: 'c', question: 'Rejetee ?', reponse: 'Hors sujet.', persona: 'RH', relecture: 'rejete' },
  ]

  it('fait du run un jeu de test : les paires non rejetées, leurs réponses pour référence', () => {
    const jeu = pairesVersJeu(paires, 'faq-sdst')
    expect(jeu.name).toBe('faq-sdst-evaluation')
    expect(jeu.questions.map(q => q.id)).toEqual(['a', 'b', 'hors-sujet-1', 'hors-sujet-2'])
    expect(jeu.questions[0]).toMatchObject({
      question: 'Quelle procedure suivre ?',
      expected_answer: 'Deposer une demande.',
      must_cite: [],
      tags: ['Agent'],
    })
  })
  it('termine par les questions hors-sujet, qui éprouvent le garde-fou', () => {
    const jeu = pairesVersJeu([], 'faq-sdst')
    expect(jeu.questions).toHaveLength(HORS_SUJET.length)
    for (const q of HORS_SUJET) expect(q.out_of_scope).toBe(true)
  })
})

describe('divers', () => {
  it('nomme le fichier exporté', () => {
    expect(nomFichierExport('faq-sdst', '0123456789abcdef', 'csv')).toBe('faq-sdst-questions-01234567.csv')
  })
  it('fait le bilan des relectures', () => {
    expect(bilanRelecture([{ relecture: 'brut' }, { relecture: 'valide' }, { relecture: 'valide' }])).toEqual({ brut: 1, valide: 2, rejete: 0 })
  })
})
