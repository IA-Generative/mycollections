import { describe, it, expect } from 'vitest'
import { slugifyCollectionName, isConflictError, deriverIdentifiant, motifRefus } from '../../utils/collectionName'

describe('slugifyCollectionName', () => {
  it('passe en minuscules et remplace les espaces par des tirets', () => {
    expect(slugifyCollectionName('Mon Corpus')).toBe('mon-corpus')
  })

  it('translittère les accents au lieu de les supprimer', () => {
    expect(slugifyCollectionName('Droit_Étrangers! v2')).toBe('droit-etrangers-v2')
    expect(slugifyCollectionName('Sécurité')).toBe('securite')
  })

  it('tolère vide / null', () => {
    expect(slugifyCollectionName('')).toBe('')
    // @ts-expect-error entrée volontairement invalide
    expect(slugifyCollectionName(null)).toBe('')
  })
})

describe('isConflictError', () => {
  it('vrai sur une erreur API 409', () => {
    expect(isConflictError(new Error('API error 409: {"detail":"Collection \'victor\' already exists"}'))).toBe(true)
  })

  it('vrai si le message contient "already exists"', () => {
    expect(isConflictError(new Error("Collection 'x' already exists"))).toBe(true)
  })

  it('faux sur une autre erreur', () => {
    expect(isConflictError(new Error('API error 500: boom'))).toBe(false)
    expect(isConflictError(null)).toBe(false)
  })
})

describe('deriverIdentifiant', () => {
  it('nomme par le contenu, sans mots vides ni accents', () => {
    expect(deriverIdentifiant('Codes NATINF')).toBe('codes-natinf')
    expect(deriverIdentifiant('Droit des étrangers')).toBe('droit-etrangers')
    expect(deriverIdentifiant('2024 — Accidents de la circulation')).toBe('accidents-circulation')
  })
  it('coupe sur un tiret, jamais au milieu d\'un mot', () => {
    const ident = deriverIdentifiant('Répertoire national des élus municipaux départementaux régionaux et européens')
    expect(ident.length).toBeLessThanOrEqual(40)
    expect(ident.endsWith('-')).toBe(false)
    expect(motifRefus(ident)).toBeNull()
  })
  it('tolère le vide', () => {
    expect(deriverIdentifiant('')).toBe('')
  })
})

describe('motifRefus', () => {
  it('donne la même clé que le serveur', () => {
    expect(motifRefus('codes-natinf')).toBeNull()
    expect(motifRefus('')).toBe('empty')
    expect(motifRefus('ab')).toBe('longueur')
    expect(motifRefus('Codes')).toBe('format')
    expect(motifRefus('codes--natinf')).toBe('format')
    expect(motifRefus('templates')).toBe('reserve')
    expect(motifRefus('demo-teletravail')).toBe('prefixe')
    expect(motifRefus('demonstration')).toBeNull()
  })
  it('suit les préfixes servis par le serveur', () => {
    const regles = { min: 3, max: 40, prefixes_bannis: ['tmp-'], reserves: [], motifs: {} }
    expect(motifRefus('demo-x', regles)).toBeNull()
    expect(motifRefus('tmp-x', regles)).toBe('prefixe')
  })
})
