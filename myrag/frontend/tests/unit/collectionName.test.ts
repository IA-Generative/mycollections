import { describe, it, expect } from 'vitest'
import { slugifyCollectionName, isConflictError } from '../../utils/collectionName'

describe('slugifyCollectionName', () => {
  it('passe en minuscules et remplace les espaces par des tirets', () => {
    expect(slugifyCollectionName('Mon Corpus')).toBe('mon-corpus')
  })

  it('supprime les caractères non [a-z0-9-]', () => {
    expect(slugifyCollectionName('Droit_Étrangers! v2')).toBe('droittrangers-v2')
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
