import type { ConnecteurDeclare } from '../../utils/assistants'
import { describe, expect, it } from 'vitest'
import { choixSource, connecteursAjoutables, etiquetteSource, ficheDepuisFormulaire, sourceDepuisChoix } from '../../utils/assistants'

const ELIGIBILITE: ConnecteurDeclare = { id: 'eligibilite-dgef', type: 'connecteur', titre: 'Référentiel d\'éligibilité', description: 'Titres de séjour et pièces.', exemples: [] }
const AUTRE: ConnecteurDeclare = { id: 'autre-referentiel', type: 'connecteur', titre: 'Autre', description: '', exemples: [] }

describe('connecteursAjoutables', () => {
  it('propose les connecteurs déclarés qui ne sont pas déjà des sources', () => {
    expect(connecteursAjoutables([ELIGIBILITE, AUTRE], [{ id: 'ceseda' }])).toEqual([ELIGIBILITE, AUTRE])
    expect(connecteursAjoutables([ELIGIBILITE, AUTRE], [{ id: 'eligibilite-dgef' }])).toEqual([AUTRE])
  })
  it('rien de déclaré, rien à proposer', () => {
    expect(connecteursAjoutables([], [])).toEqual([])
  })
})

describe('etiquetteSource', () => {
  it('« Référentiel » pour un connecteur, rien pour une collection', () => {
    expect(etiquetteSource('connecteur')).toBe('Référentiel')
    expect(etiquetteSource('collection')).toBe('')
    expect(etiquetteSource(undefined)).toBe('')
  })
})

describe('choixSource / sourceDepuisChoix', () => {
  it('l\'option choisie redonne la source, avec son type', () => {
    expect(sourceDepuisChoix(choixSource('connecteur', 'eligibilite-dgef'))).toEqual({ id: 'eligibilite-dgef', type: 'connecteur', regime: 'selon_question' })
    expect(sourceDepuisChoix(choixSource('collection', 'ceseda'))).toEqual({ id: 'ceseda', type: 'collection', regime: 'selon_question' })
  })
  it('un identifiant qui contient « : » reste entier', () => {
    expect(sourceDepuisChoix('collection:a:b')?.id).toBe('a:b')
  })
  it('une valeur vide ou d\'un type inconnu n\'ajoute rien', () => {
    expect(sourceDepuisChoix('')).toBeNull()
    expect(sourceDepuisChoix('ceseda')).toBeNull()
    expect(sourceDepuisChoix('collection:')).toBeNull()
    expect(sourceDepuisChoix('autre:x')).toBeNull()
  })
})

describe('ficheDepuisFormulaire avec un connecteur', () => {
  it('garde le type de chaque source, collection par défaut', () => {
    const f = ficheDepuisFormulaire({
      titre: 'Séjour',
      identifiant: 'sejour-etrangers',
      description: '',
      rubrique: '',
      sources: [{ id: 'ceseda', regime: 'toujours' }, { id: 'eligibilite-dgef', type: 'connecteur', regime: 'selon_question' }],
    })
    expect(f.sources).toEqual([{ id: 'ceseda', type: 'collection', regime: 'toujours', rang: 1 }, { id: 'eligibilite-dgef', type: 'connecteur', regime: 'selon_question', rang: 2 }])
  })
})
