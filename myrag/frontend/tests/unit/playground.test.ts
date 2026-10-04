import { describe, expect, it } from 'vitest'
import { proxiedSourceUrl } from '../../utils/playground'

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
