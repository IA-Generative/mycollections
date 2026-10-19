import { describe, expect, it } from 'vitest'
import { CAPACITES_DEFAUT } from '../../utils/capacites'
import { entreesPrincipales, estActive } from '../../utils/navigation'

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
    expect(entreesPrincipales({ ...RIEN, assistants: true } as never, false)).toEqual(entreesPrincipales(RIEN, false))
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
