import { describe, expect, it } from 'vitest'
import { fusionnerGroupes, groupPaths, lignesVersGroupes, optionsGroupes } from '../../utils/groupes'

describe('groupPaths', () => {
  it('rend les chemins complets', () => {
    expect(groupPaths(['/g/mirai-beta-testeurs', '/g/x'])).toEqual(['/g/mirai-beta-testeurs', '/g/x'])
  })
  it('ne rend rien d\'un claim en noms courts, même mêlé de chemins', () => {
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

describe('optionsGroupes', () => {
  it('propose chaque chemin avec son dernier segment en libellé', () => {
    expect(optionsGroupes(['/g/equipe-a', '/g/dir/equipe-b'])).toEqual([
      { value: '/g/equipe-a', label: 'equipe-a', hint: '/g/equipe-a' },
      { value: '/g/dir/equipe-b', label: 'equipe-b', hint: '/g/dir/equipe-b' },
    ])
  })

  it('ne propose rien si le claim est en noms courts', () => {
    expect(optionsGroupes(['equipe-a'])).toEqual([])
  })
})

describe('fusionnerGroupes', () => {
  it('coche puis saisit, sans doublon ni vide, dans l\'ordre', () => {
    expect(fusionnerGroupes(['/g/a', '/g/b'], [' /g/B ', '', '/g/c'])).toEqual(['/g/a', '/g/b', '/g/c'])
  })
})
