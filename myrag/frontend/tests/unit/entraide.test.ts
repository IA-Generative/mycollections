import { describe, expect, it } from 'vitest'
import { adresseAppel, compteReponses, destinationDemandes, LIBELLES_ETAT_APPEL, LIBELLES_TYPE, libelleType } from '../../utils/entraide'

describe('/demandes mène au réseau d’entraide seulement si le drapeau est vrai', () => {
  it('drapeau vrai : /entraide', () => {
    expect(destinationDemandes({ entraide: true })).toBe('/entraide')
  })
  it('drapeau faux : /demandes, inchangé', () => {
    expect(destinationDemandes({ entraide: false })).toBe('/demandes')
  })
  it('le dépôt d’une demande reste sur les demandes', () => {
    expect(destinationDemandes({ entraide: true }, { deposer: '1' })).toBe('/demandes')
  })
  it('un drapeau qui n’est pas exactement true ne compte pas', () => {
    expect(destinationDemandes({ entraide: 'oui' as unknown as boolean })).toBe('/demandes')
  })
})

describe('les libellés', () => {
  it('ne disent jamais « ticket »', () => {
    const tous = JSON.stringify([LIBELLES_TYPE, LIBELLES_ETAT_APPEL, compteReponses({ nb_reponses: 2 }), compteReponses({ nb_reponses: 0, par_reference: true })])
    expect(tous.toLowerCase()).not.toContain('ticket')
  })
  it('compte les réponses', () => {
    expect(compteReponses({ nb_reponses: 0 })).toBe('aucune réponse')
    expect(compteReponses({ nb_reponses: 1 })).toBe('1 réponse')
    expect(compteReponses({ nb_reponses: 3 })).toBe('3 réponses')
    expect(compteReponses({ nb_reponses: 2, par_reference: true })).toBe('2 collègues intéressés')
  })
  it('nomme les types', () => {
    expect(libelleType('cherche')).toBe('Je cherche quelqu’un')
    expect(libelleType('autre')).toBe('autre')
  })
})

describe('l’adresse d’un appel', () => {
  it('une demande en référence s’ouvre sur sa page', () => {
    expect(adresseAppel({ id: 'demande:abc', demande_id: 'abc', par_reference: true })).toBe('/demandes/abc')
  })
  it('un appel s’ouvre sur la sienne', () => {
    expect(adresseAppel({ id: 'x1', demande_id: null, par_reference: false })).toBe('/entraide/x1')
  })
})
