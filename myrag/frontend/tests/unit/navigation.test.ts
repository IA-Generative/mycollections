import { describe, expect, it } from 'vitest'
import { CAPACITES_DEFAUT } from '../../utils/capacites'
import { entreeEntraide, ENTREES_PIED_DE_PAGE, entreesPrincipales, estActive, RUBRIQUES_ASSISTANT, sousMenuAssistant, sousMenuCollection } from '../../utils/navigation'

const RIEN = { ...CAPACITES_DEFAUT }
const AVEC_DEMANDES = { ...CAPACITES_DEFAUT, demandes: true }
const TOUT = { ...CAPACITES_DEFAUT, demandes: true, assistants: true, entraide: true }

describe('entreesPrincipales — le menu décidé (refonte du 2026-10-19)', () => {
  it('sans drapeau ni droit d\'administration : Accueil, Catalogue, Mes collections', () => {
    expect(entreesPrincipales(RIEN, false)).toEqual([
      { libelle: 'Accueil', vers: '/', exact: true },
      { libelle: 'Catalogue', vers: '/admin/catalog', exact: true },
      { libelle: 'Mes collections', vers: '/mes-collections', pastille: true },
    ])
  })
  it('tous les drapeaux et l\'administration : six entrées, dans l\'ordre', () => {
    expect(entreesPrincipales(TOUT, true).map(e => `${e.libelle} ${e.vers}`)).toEqual([
      'Accueil /',
      'Catalogue /admin/catalog',
      'Mes collections /mes-collections',
      'Assistants /assistants',
      'Entraide /entraide',
      'Administration /admin',
    ])
  })
  it('« Soyez acteurs vous-mêmes » n\'est plus dans le menu : il est au pied de page', () => {
    expect(entreesPrincipales(TOUT, true).map(e => e.libelle)).not.toContain('Soyez acteurs vous-mêmes')
    expect(ENTREES_PIED_DE_PAGE).toEqual([{ libelle: 'Soyez acteurs vous-mêmes', vers: '/guide' }])
  })
  it('« Mes collections » est un lien simple vers la liste, avec sa pastille, en troisième position', () => {
    const e = entreesPrincipales(RIEN, false)[2]!
    expect(e).toEqual({ libelle: 'Mes collections', vers: '/mes-collections', pastille: true })
    expect(entreesPrincipales(TOUT, true).filter(x => x.pastille)).toHaveLength(1)
  })
  it('l\'administration ferme la liste pour qui en a le droit, et seulement pour lui', () => {
    expect(entreesPrincipales(AVEC_DEMANDES, true).at(-1)).toEqual({ libelle: 'Administration', vers: '/admin' })
    expect(entreesPrincipales(AVEC_DEMANDES, false).map(e => e.libelle)).not.toContain('Administration')
  })
  it('un drapeau inconnu ne change rien', () => {
    expect(entreesPrincipales({ ...RIEN, inconnu: true } as never, false)).toEqual(entreesPrincipales(RIEN, false))
  })
})

describe('les assistants, un objet distinct des collections', () => {
  it('une entrée « Assistants » à part, seulement si le drapeau est vrai', () => {
    expect(entreesPrincipales({ ...RIEN, assistants: true }, false).map(e => e.libelle)).toEqual(['Accueil', 'Catalogue', 'Mes collections', 'Assistants'])
    expect(entreesPrincipales(RIEN, false).map(e => e.libelle)).not.toContain('Assistants')
  })
  it('« Mes collections » ne parle jamais des assistants', () => {
    expect(entreesPrincipales(TOUT, true).find(e => e.pastille)!.libelle).toBe('Mes collections')
  })
  it('« Assistants » est courante sur toute la fiche d\'un assistant', () => {
    const a = entreesPrincipales(TOUT, false).find(e => e.libelle === 'Assistants')!
    expect(estActive(a, '/assistants/sejour/consignes')).toBe(true)
    expect(estActive(a, '/mes-collections')).toBe(false)
  })
})

describe('entreeEntraide', () => {
  it('le réseau d\'entraide d\'abord', () => {
    expect(entreeEntraide({ entraide: true, demandes: true })).toEqual({ libelle: 'Entraide', vers: '/entraide', icone: 'fr-icon-team-line' })
    expect(entreeEntraide({ entraide: true, demandes: false })?.vers).toBe('/entraide')
  })
  it('sinon les demandes de la communauté', () => {
    expect(entreeEntraide({ entraide: false, demandes: true })).toEqual({ libelle: 'Entraide', vers: '/demandes', icone: 'fr-icon-team-line' })
  })
  it('sinon l\'entrée n\'existe pas', () => {
    expect(entreeEntraide({ entraide: false, demandes: false })).toBeNull()
    expect(entreesPrincipales(RIEN, true).map(e => e.libelle)).not.toContain('Entraide')
  })
  it('l\'icône est portée par l\'entrée du menu', () => {
    const e = entreesPrincipales(AVEC_DEMANDES, false).find(x => x.libelle === 'Entraide')!
    expect(e.icone).toBe('fr-icon-team-line')
    expect(entreesPrincipales(AVEC_DEMANDES, false).filter(x => x.icone)).toHaveLength(1)
  })
})

describe('estActive', () => {
  const [accueil, catalogue, miennes, entraide, admin] = entreesPrincipales(AVEC_DEMANDES, true)
  it('accueil et Catalogue seulement sur leur adresse exacte', () => {
    expect(estActive(accueil!, '/')).toBe(true)
    expect(estActive(accueil!, '/guide')).toBe(false)
    expect(estActive(catalogue!, '/admin/catalog')).toBe(true)
    expect(estActive(catalogue!, '/admin/catalog?x=1')).toBe(false)
  })
  it('mes collections, Entraide et Administration sur tout leur sous-arbre', () => {
    expect(estActive(miennes!, '/mes-collections')).toBe(true)
    expect(estActive(entraide!, '/demandes/42')).toBe(true)
    expect(estActive(admin!, '/admin/create/step-4')).toBe(true)
    expect(estActive(entraide!, '/')).toBe(false)
  })
  it('le Catalogue vit sous /admin : l\'Administration y est courante aussi (comportement actuel)', () => {
    expect(estActive(admin!, '/admin/catalog')).toBe(true)
  })
})

describe('sousMenuAssistant', () => {
  it('six rubriques, dans l\'ordre de l\'architecture cible, chacune exacte', () => {
    expect(sousMenuAssistant('sejour-des-etrangers').map(e => e.libelle)).toEqual(['Sources', 'Consignes', 'Réponses fiables', 'Qualité', 'Publication', 'Bac à sable'])
    expect(sousMenuAssistant('sejour-des-etrangers')[2]).toEqual({ libelle: 'Réponses fiables', vers: '/assistants/sejour-des-etrangers/fiables', exact: true })
    expect(RUBRIQUES_ASSISTANT).toHaveLength(6)
  })
  it('l\'identifiant est encodé dans l\'adresse', () => {
    expect(sousMenuAssistant('a/b')[0]!.vers).toBe('/assistants/a%2Fb/sources')
  })
})

describe('sousMenuCollection', () => {
  it('quatre rubriques vers les pages qui existent', () => {
    expect(sousMenuCollection('codes-natinf').map(e => `${e.libelle} ${e.vers}`)).toEqual([
      'Vue d\'ensemble /c/codes-natinf',
      'Documents /c/codes-natinf?onglet=documents',
      'Qualité /c/codes-natinf/qualite',
      'Publication /c/codes-natinf/publish',
    ])
  })
})
