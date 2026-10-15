import { describe, expect, it } from 'vitest'
import {
  appreciation, cibleAction, classeVerdict, conseils, estimationMesure, libelleOrigine, libelleVerdict, lireImport,
  pointsCourbe, resumeVerdicts, REGLE_DE_GARDE, aLaRegleDeGarde, avancementTravaux, dateMesure,
} from '../../utils/qualite'

describe('libellés', () => {
  it('dit les verdicts et les origines en français', () => {
    expect(libelleVerdict('refus_ko')).toBe('Réponse inventée')
    expect(libelleVerdict(null)).toBe('Jamais mesurée')
    expect(classeVerdict('non_conforme')).toBe('fr-badge--error')
    expect(libelleOrigine('avis')).toBe("Avis d'usager")
  })
  it('apprécie un score avec les seuils du serveur', () => {
    expect(appreciation(85).libelle).toBe('Très bonne')
    expect(appreciation(62.5).libelle).toBe('Satisfaisante')
    expect(appreciation(40).libelle).toBe('À améliorer')
    expect(appreciation(null).libelle).toBe('Non mesurée')
  })
})

describe('synthèse', () => {
  it('résume les verdicts', () => {
    expect(resumeVerdicts({ conformes: 7, partielles: 1, non_conformes: 1, refus_ok: 2, refus_ko: 0, sans_source: 0, erreurs: 0 }))
      .toBe('7 conformes · 1 partielle · 1 non conforme · hors sujet refusés 2/2')
  })
  it('estime la durée', () => {
    expect(estimationMesure(9)).toBe('≈ 27 s')
    expect(estimationMesure(50)).toBe('≈ 3 min')
    expect(estimationMesure(0)).toBe('')
  })
  it('place les points de la courbe et saute les trous', () => {
    const p = pointsCourbe([50, null, 100], 400, 140, 20)
    expect(p).toEqual([{ x: 20, y: 70, score: 50 }, { x: 380, y: 20, score: 100 }])
    expect(pointsCourbe([])).toEqual([])
  })
})

describe('actions et conseils', () => {
  it('mène chaque action au bon endroit', () => {
    expect(cibleAction('corriger_echecs', 'c')).toEqual({ onglet: 'jeu', filtre: { verdict: 'non_conforme' } })
    expect(cibleAction('traiter_avis', 'c').onglet).toBe('avis')
  })
  it('conseille selon le verdict', () => {
    expect(conseils('sans_source', false)).toEqual(['decoupage', 'corriger'])
    expect(conseils('refus_ko', true)).toEqual(['consignes'])
    expect(conseils('conforme', false)).toEqual([])
  })
})

describe('import', () => {
  it('lit un JSON de jeu ou un export eval-rag', () => {
    expect(lireImport('{"questions":[{"question":"Q ?"}]}', 'a.json')).toEqual({ questions: [{ question: 'Q ?' }] })
    expect(lireImport('{"samples":[{"question":"Q ?","answer":"R"}]}', 'a.json')).toEqual({ questions: [{ question: 'Q ?', answer: 'R' }] })
    expect('erreur' in lireImport('pas du json', 'a.json')).toBe(true)
  })
  it('lit un CSV avec point-virgule ou virgule', () => {
    expect(lireImport('﻿question;reponse\nQuel délai ?;Deux mois.\n', 'jeu.csv'))
      .toEqual({ questions: [{ question: 'Quel délai ?', expected_answer: 'Deux mois.' }] })
    expect(lireImport('question,answer\nQ ?,R\n', 'jeu.csv')).toEqual({ questions: [{ question: 'Q ?', expected_answer: 'R' }] })
    expect('erreur' in lireImport('titre;texte\na;b', 'x.csv')).toBe(true)
  })
})

describe('leviers', () => {
  it('reconnaît la règle de garde, avec ou sans accent', () => {
    expect(aLaRegleDeGarde(`Consignes${REGLE_DE_GARDE}`)).toBe(true)
    expect(aLaRegleDeGarde('## Règle de garde')).toBe(true)
    expect(aLaRegleDeGarde('Réponds en français.')).toBe(false)
    expect(aLaRegleDeGarde(null)).toBe(false)
  })

  it('suit un redécoupage : finis, échecs, pourcentage', () => {
    expect(avancementTravaux([])).toEqual({ finis: 0, total: 0, pct: 0, echecs: 0 })
    const a = avancementTravaux([
      { status: 'completed', completed_at: '2026-10-15T10:00:00' },
      { status: 'uploading', progress_pct: 50 },
      { status: 'failed' },
      { status: 'chunking', progress_pct: 0 },
    ])
    expect(a).toEqual({ finis: 2, total: 4, pct: 63, echecs: 1 })
  })

  it('lit une date du serveur sans fuseau comme de l\'UTC', () => {
    expect(dateMesure('')).toBe('')
    expect(dateMesure('pas une date')).toBe('pas une date')
    const sans = dateMesure('2026-10-14T13:02:00')
    expect(sans).toBe(dateMesure('2026-10-14T13:02:00Z'))
    expect(sans).toBe(dateMesure('2026-10-14T15:02:00+02:00'))
  })
})
