import { describe, it, expect } from 'vitest'
import { libelleStrategie, libelleSensibilite, libelleConsignes, libelleActionPublication, SENSIBILITES } from '../../utils/libelles'

describe('libellés des réglages', () => {
  it('traduit les valeurs connues', () => {
    expect(libelleStrategie('article')).toBe('Découpage par article')
    expect(libelleSensibilite('internal')).toBe('Interne')
    expect(libelleConsignes('generic')).toBe('Consignes générales')
    expect(libelleActionPublication('disabled')).toBe("Retirée du chat MirAI")
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

describe('sensibilités (#134)', () => {
  it('propose les six niveaux, dans cet ordre', () => {
    expect(SENSIBILITES.map(s => s.libelle)).toEqual([
      'Public — internet',
      'Interne',
      'Données personnelles',
      'Données personnelles sensibles',
      'Diffusion contrôlée',
      'Diffusion restreinte',
    ])
    expect(libelleSensibilite('personal_sensitive')).toBe('Données personnelles sensibles')
  })
})
