import { describe, expect, it } from 'vitest'
import { etapesDeFrappe, proxiedSourceUrl, sansMention } from '../../utils/playground'

describe('proxiedSourceUrl', () => {
  it('ramène une adresse OpenRAG sur le proxy', () => {
    expect(proxiedSourceUrl('http://openrag:8080/extract/12')).toBe('/api/openrag/extract/12')
    expect(proxiedSourceUrl('https://api.openrag.fake-domain.name/static/abc.pdf')).toBe('/api/openrag/static/abc.pdf')
  })
  it('garde intact un lien déjà signé par le serveur', () => {
    const signe = '/api/openrag/extract/12?exp=1790000000&sig=abc123'
    expect(proxiedSourceUrl(signe)).toBe(signe)
  })
  it('laisse le reste tel quel', () => {
    expect(proxiedSourceUrl('')).toBe('')
    expect(proxiedSourceUrl('https://www.data.gouv.fr/x')).toBe('https://www.data.gouv.fr/x')
  })
})

describe('etapesDeFrappe', () => {
  it('écrit une question courte lettre à lettre et finit sur le texte entier', () => {
    expect(etapesDeFrappe(5)).toEqual([1, 2, 3, 4, 5])
  })

  it('borne le nombre d\'étapes pour une question longue', () => {
    const e = etapesDeFrappe(400)
    expect(e.length).toBeLessThanOrEqual(41)
    expect(e.at(-1)).toBe(400)
    expect(e).toEqual([...e].sort((a, b) => a - b))
  })

  it('ne frappe rien pour un texte vide', () => {
    expect(etapesDeFrappe(0)).toEqual([])
  })
})

describe('sansMention', () => {
  it('retire exactement la mention mise en tête par le serveur', () => {
    expect(sansMention('⚠ en cours de vérification\n\nLa réponse.', 'en cours de vérification')).toBe('La réponse.')
  })

  it('ne touche à rien sans mention, ou si elle n\'est pas en tête', () => {
    expect(sansMention('La réponse.', null)).toBe('La réponse.')
    expect(sansMention('La réponse. ⚠ en cours de vérification', 'en cours de vérification')).toBe('La réponse. ⚠ en cours de vérification')
    expect(sansMention('', 'x')).toBe('')
  })
})
