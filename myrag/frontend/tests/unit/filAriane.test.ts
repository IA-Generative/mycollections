import { describe, it, expect } from 'vitest'
import { maillonsFil, ongletDeLAdresse, libelleSansCompteur } from '../../utils/filAriane'

describe('maillonsFil', () => {
  it('passe par le catalogue, pas seulement par l\'accueil', () => {
    expect(maillonsFil('natinf', 'Codes NATINF', 'Réglages')).toEqual([
      { libelle: 'Accueil', vers: '/' },
      { libelle: 'Catalogue', vers: '/admin/catalog' },
      { libelle: 'Codes NATINF', vers: '/c/natinf' },
      { libelle: 'Réglages' },
    ])
  })

  it('sans rubrique, la collection est la page courante', () => {
    const fil = maillonsFil('natinf', 'Codes NATINF')
    expect(fil).toHaveLength(3)
    expect(fil[2]).toEqual({ libelle: 'Codes NATINF' })
  })

  it("prend l'identifiant quand le titre n'est pas encore là", () => {
    expect(maillonsFil('natinf', '')[2].libelle).toBe('natinf')
  })
})

describe('ongletDeLAdresse', () => {
  const connus = ['consulter', 'documents', 'feedback']
  it("lit l'onglet porté par l'adresse", () => {
    expect(ongletDeLAdresse('documents', connus, 'consulter')).toBe('documents')
    expect(ongletDeLAdresse(['feedback', 'documents'], connus, 'consulter')).toBe('feedback')
  })
  it('retombe sur l\'onglet par défaut sur une valeur absente ou inconnue', () => {
    expect(ongletDeLAdresse(undefined, connus, 'consulter')).toBe('consulter')
    expect(ongletDeLAdresse('inconnu', connus, 'consulter')).toBe('consulter')
    expect(ongletDeLAdresse(null, connus, 'consulter')).toBe('consulter')
  })
})

describe('libelleSansCompteur', () => {
  it('retire le compteur final', () => {
    expect(libelleSansCompteur('Avis (12)')).toBe('Avis')
    expect(libelleSansCompteur('Signaler un défaut')).toBe('Signaler un défaut')
  })
})
