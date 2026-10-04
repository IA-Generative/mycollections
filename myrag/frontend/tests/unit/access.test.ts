import { describe, it, expect } from 'vitest'
import { groupPaths, isAdminGroup } from '../../utils/access'

describe('isAdminGroup (identification super-admin)', () => {
  it('vrai pour /myrag/superadmin', () => {
    expect(isAdminGroup(['/myrag/superadmin'])).toBe(true)
  })

  it('faux sans slash initial : un nom de groupe peut contenir « / »', () => {
    // Groupe keycloak-comu nommé « myrag/superadmin », mapper en noms courts.
    expect(isAdminGroup(['myrag/superadmin'])).toBe(false)
  })

  it('faux pour un simple membre / admin de collection', () => {
    expect(isAdminGroup(['/myrag/collec-a', '/myrag/collec-a-admin'])).toBe(false)
  })

  it('faux pour vide, null, undefined ou non-liste', () => {
    expect(isAdminGroup([])).toBe(false)
    expect(isAdminGroup(null)).toBe(false)
    expect(isAdminGroup(undefined)).toBe(false)
    // @ts-expect-error entrée volontairement invalide
    expect(isAdminGroup('myrag/superadmin')).toBe(false)
  })

  it('faux pour un superadmin hors du namespace /myrag', () => {
    expect(isAdminGroup(['/autre/superadmin'])).toBe(false)
  })

  it('vrai si superadmin présent parmi d’autres groupes', () => {
    expect(isAdminGroup(['/myrag/collec-a', '/myrag/superadmin', '/x'])).toBe(true)
  })
})

describe('forme de la bêta (mapper full.path=false) : aucun droit', () => {
  it('le nom court « superadmin » ne vaut rien', () => {
    expect(isAdminGroup(['mirai-beta-testeurs', 'superadmin'])).toBe(false)
  })

  it('un homonyme qui imite le chemin ne vaut rien dans un claim en noms courts', () => {
    // Groupe créé dans keycloak-comu sous le nom « /myrag/superadmin » : le claim court
    // porte cette valeur, mais aussi le groupe exigé des testeurs, sans « / ».
    expect(isAdminGroup(['mirai-beta-testeurs', '/myrag/superadmin'])).toBe(false)
  })

  it('le superadmin est reconnu une fois le mapper en chemins complets', () => {
    expect(isAdminGroup(['/g/mirai-beta-testeurs', '/myrag/superadmin'])).toBe(true)
  })

  it('un homonyme hors périmètre reste refusé en chemins complets', () => {
    expect(isAdminGroup(['/g/mirai-beta-testeurs', '/g/superadmin', '/g/myrag/superadmin'])).toBe(false)
  })
})

describe('groupPaths', () => {
  it('rend les chemins tels quels', () => {
    expect(groupPaths(['/g/a', '/myrag/b'])).toEqual(['/g/a', '/myrag/b'])
  })

  it('rend une liste vide dès qu’une valeur est un nom court', () => {
    expect(groupPaths(['/g/a', 'b'])).toEqual([])
  })

  it('tolère une entrée qui n’est pas une liste', () => {
    expect(groupPaths('/g/a')).toEqual([])
    expect(groupPaths(undefined)).toEqual([])
  })
})
