import { describe, expect, it } from 'vitest'
import { lignesVersMotifs, messageRefus, motifsVersLignes } from '../../utils/sites'

describe('lignesVersMotifs', () => {
  it('un motif par ligne, sans lignes vides ni doublons', () => {
    expect(lignesVersMotifs(' https://a.fake-domain.name/* \n\n https://a.fake-domain.name/*\r\nhttps://b.fake-domain.name/x ')).toEqual([
      'https://a.fake-domain.name/*',
      'https://b.fake-domain.name/x',
    ])
  })
  it('un texte vide ne déclare rien', () => {
    expect(lignesVersMotifs('')).toEqual([])
  })
  it('aller-retour', () => {
    const m = ['https://a.fake-domain.name/*', 'https://b.fake-domain.name/x']
    expect(lignesVersMotifs(motifsVersLignes(m))).toEqual(m)
  })
})

describe('messageRefus', () => {
  it('reprend la raison donnée par le serveur', () => {
    const e = new Error(`API error 422: ${JSON.stringify({ detail: { reason: 'motif', message: 'Motif 1 : Le motif doit commencer par https://.' } })}`)
    expect(messageRefus(e)).toBe('Motif 1 : Le motif doit commencer par https://.')
  })
  it('sinon le message commun', () => {
    expect(messageRefus(new Error('API error 403: {"detail":"Seules les personnes qui gèrent la collection déclarent ses sites"}'))).toContain('gèrent')
  })
})
