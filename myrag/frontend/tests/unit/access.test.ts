import { describe, it, expect } from 'vitest'
import { isAdminGroup } from '../../utils/access'

describe('isAdminGroup (identification super-admin)', () => {
  it('vrai pour /myrag/superadmin', () => {
    expect(isAdminGroup(['/myrag/superadmin'])).toBe(true)
  })

  it('vrai sans slash initial (forme Keycloak alternative)', () => {
    expect(isAdminGroup(['myrag/superadmin'])).toBe(true)
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
