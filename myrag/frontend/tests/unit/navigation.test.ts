import { describe, expect, it } from 'vitest'
import { CAPACITES_DEFAUT } from '../../utils/capacites'
import { entreesPrincipales, estActive, RUBRIQUES_ASSISTANT, sousMenuAssistant, sousMenuCollection } from '../../utils/navigation'

const RIEN = { ...CAPACITES_DEFAUT }
const AVEC_DEMANDES = { ...CAPACITES_DEFAUT, demandes: true }

describe('entreesPrincipales', () => {
  it('sans drapeau ni droit d\'administration : les trois entrées de toujours, dans l\'ordre', () => {
    expect(entreesPrincipales(RIEN, false)).toEqual([
      { libelle: 'Accueil', vers: '/', exact: true },
      { libelle: 'Catalogue', vers: '/admin/catalog', exact: true },
      { libelle: 'Soyez acteurs vous-mêmes', vers: '/guide' },
    ])
  })
  it('les demandes de la communauté s\'insèrent en troisième quand le menu les déclare', () => {
    expect(entreesPrincipales(AVEC_DEMANDES, false).map(e => e.libelle)).toEqual([
      'Accueil',
      'Catalogue',
      'Demandes de la communauté',
      'Soyez acteurs vous-mêmes',
    ])
    expect(entreesPrincipales(AVEC_DEMANDES, false)[2]).toEqual({ libelle: 'Demandes de la communauté', vers: '/demandes' })
  })
  it('l\'administration ferme la liste pour qui en a le droit', () => {
    const libelles = entreesPrincipales(AVEC_DEMANDES, true).map(e => e.libelle)
    expect(libelles.at(-1)).toBe('Administration')
    expect(libelles).toHaveLength(5)
    expect(entreesPrincipales(AVEC_DEMANDES, true).at(-1)).toEqual({ libelle: 'Administration', vers: '/admin' })
  })
  it('un drapeau inconnu ne change rien', () => {
    expect(entreesPrincipales({ ...RIEN, inconnu: true } as never, false)).toEqual(entreesPrincipales(RIEN, false))
  })
})

describe('estActive', () => {
  const [accueil, catalogue, demandes, guide, admin] = entreesPrincipales(AVEC_DEMANDES, true)
  it('accueil et Catalogue seulement sur leur adresse exacte', () => {
    expect(estActive(accueil!, '/')).toBe(true)
    expect(estActive(accueil!, '/guide')).toBe(false)
    expect(estActive(catalogue!, '/admin/catalog')).toBe(true)
    expect(estActive(catalogue!, '/admin/catalog?x=1')).toBe(false)
  })
  it('demandes, Guide et Administration sur tout leur sous-arbre', () => {
    expect(estActive(demandes!, '/demandes/42')).toBe(true)
    expect(estActive(guide!, '/guide/interroger-depuis-vos-si')).toBe(true)
    expect(estActive(admin!, '/admin/create/step-4')).toBe(true)
    expect(estActive(guide!, '/')).toBe(false)
  })
  it('le Catalogue vit sous /admin : l\'Administration y est courante aussi (comportement actuel)', () => {
    expect(estActive(admin!, '/admin/catalog')).toBe(true)
  })
})

describe('les entrées du chantier des assistants (drapeaux)', () => {
  const TOUT = { ...CAPACITES_DEFAUT, demandes: true, assistants: true, entraide: true }
  it('assistants vient après l\'accueil, le réseau d\'entraide remplace les demandes', () => {
    expect(entreesPrincipales(TOUT, true).map(e => `${e.libelle} ${e.vers}`)).toEqual([
      'Accueil /',
      'Assistants /assistants',
      'Catalogue /admin/catalog',
      'Réseau d\'entraide /entraide',
      'Soyez acteurs vous-mêmes /guide',
      'Administration /admin',
    ])
  })
  it('chaque drapeau seul n\'ajoute que son entrée', () => {
    expect(entreesPrincipales({ ...CAPACITES_DEFAUT, assistants: true }, false).map(e => e.libelle)).toEqual(['Accueil', 'Assistants', 'Catalogue', 'Soyez acteurs vous-mêmes'])
    expect(entreesPrincipales({ ...CAPACITES_DEFAUT, entraide: true }, false).map(e => e.libelle)).toEqual(['Accueil', 'Catalogue', 'Réseau d\'entraide', 'Soyez acteurs vous-mêmes'])
  })
  it('assistants est courante sur toute la fiche d\'un assistant', () => {
    const assistants = entreesPrincipales(TOUT, false)[1]!
    expect(estActive(assistants, '/assistants/sejour-des-etrangers/consignes')).toBe(true)
    expect(estActive(assistants, '/admin/catalog')).toBe(false)
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
