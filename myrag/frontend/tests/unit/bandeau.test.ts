import { describe, expect, it } from 'vitest'
import { bandeauAffiche, lireFermes } from '../../utils/bandeau'

const B = { id: 'msg-1', titre: 'Titre', texte: 'Texte' }

describe('bandeauAffiche', () => {
  it('affiché tant qu\'il n\'est pas fermé', () => {
    expect(bandeauAffiche(B, [])).toBe(true)
    expect(bandeauAffiche(B, ['msg-1'])).toBe(false)
  })
  it('un nouveau message (nouvel identifiant) revient même si l\'ancien a été fermé', () => {
    expect(bandeauAffiche({ ...B, id: 'msg-2' }, ['msg-1'])).toBe(true)
  })
  it('pas de bandeau : rien', () => {
    expect(bandeauAffiche(null, [])).toBe(false)
  })
})

describe('lireFermes', () => {
  it('lit une liste, ignore le reste', () => {
    expect(lireFermes('["a","b"]')).toEqual(['a', 'b'])
    expect(lireFermes('[1,"a"]')).toEqual(['a'])
    expect(lireFermes(null)).toEqual([])
    expect(lireFermes('{"a":1}')).toEqual([])
    expect(lireFermes('pas du json')).toEqual([])
  })
})
