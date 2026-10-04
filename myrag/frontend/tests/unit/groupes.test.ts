import { describe, expect, it } from 'vitest'
import { groupPaths } from '../../utils/groupes'

describe('groupPaths', () => {
  it('rend les chemins complets', () => {
    expect(groupPaths(['/g/mirai-beta-testeurs', '/g/x'])).toEqual(['/g/mirai-beta-testeurs', '/g/x'])
  })
  it("ne rend rien d'un claim en noms courts, même mêlé de chemins", () => {
    expect(groupPaths(['mirai-beta-testeurs', '/g/x'])).toEqual([])
  })
  it('ignore ce qui n\'est pas une liste', () => {
    expect(groupPaths(null)).toEqual([])
    expect(groupPaths('/g/x')).toEqual([])
  })
})
