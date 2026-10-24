import { describe, expect, it } from 'vitest'
import { groupPaths, lignesVersGroupes } from '../../utils/groupes'

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

describe('lignesVersGroupes', () => {
  it('un groupe par ligne ou par virgule, sans vide ni doublon', () => {
    expect(lignesVersGroupes(' /g/equipe-a \n\n/g/equipe-b, /g/equipe-a\n')).toEqual(['/g/equipe-a', '/g/equipe-b'])
    expect(lignesVersGroupes('   ')).toEqual([])
  })
})
