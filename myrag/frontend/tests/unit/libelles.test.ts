import { describe, it, expect } from 'vitest'
import { libelleStrategie, libelleSensibilite, libelleConsignes, libelleActionPublication } from '../../utils/libelles'

describe('libellés des réglages', () => {
  it('traduit les valeurs connues', () => {
    expect(libelleStrategie('article')).toBe('Découpage par article')
    expect(libelleSensibilite('internal')).toBe('Interne au ministère')
    expect(libelleConsignes('generic')).toBe('Consignes générales')
    expect(libelleActionPublication('disabled')).toBe("Retirée de l'assistant")
  })

  it("rend une valeur inconnue telle quelle, plutôt que de la faire disparaître", () => {
    expect(libelleConsignes('modele-maison')).toBe('modele-maison')
    expect(libelleStrategie('nouvelle')).toBe('nouvelle')
  })

  it('rend vide sur une valeur absente', () => {
    expect(libelleSensibilite('')).toBe('')
    expect(libelleSensibilite(undefined)).toBe('')
    expect(libelleStrategie(null)).toBe('')
  })
})
