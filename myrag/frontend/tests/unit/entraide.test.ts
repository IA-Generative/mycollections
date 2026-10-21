import { describe, expect, it } from 'vitest'
import { adresseAppel, compteReponses, destinationDemandes, libelleRoles, LIBELLES_ETAT_APPEL, LIBELLES_TYPE, libelleType, lienTchapPlausible, sansRecommandation } from '../../utils/entraide'

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

describe('les recommandations avant de publier', () => {
  it('rien à montrer : pas de bloc', () => {
    expect(sansRecommandation(null)).toBe(true)
    expect(sansRecommandation({ collections: [], assistants: [], demandes_voisines: [] })).toBe(true)
  })
  it('une collection suffit à montrer le bloc', () => {
    expect(sansRecommandation({ collections: [{ id: 'a', titre: 'A', description: '', vers: '/c/a' }], assistants: [], demandes_voisines: [] })).toBe(false)
  })
  it('les rôles se lisent sans identité', () => {
    expect(libelleRoles({ soutien: 2, fournisseur: 1 })).toBe('2 soutiens, 1 fournisseur')
    expect(libelleRoles({})).toBe('personne encore')
  })
})

describe('le lien Tchap, vérification de forme', () => {
  it('vide, ou https sans adresse de messagerie', () => {
    expect(lienTchapPlausible('')).toBe(true)
    expect(lienTchapPlausible('https://tchap.gouv.fr/#/room/!a:b')).toBe(true)
    expect(lienTchapPlausible('http://tchap.gouv.fr/#/room/!a:b')).toBe(false)
    expect(lienTchapPlausible('prenom.nom@fake-domain.name')).toBe(false)
  })
})
