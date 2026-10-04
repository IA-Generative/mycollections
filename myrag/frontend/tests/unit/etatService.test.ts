import { describe, it, expect } from 'vitest'
import { sondeInitiale, noterMesure, heureLisible, SEUIL_ECHECS } from '../../utils/etatService'

describe('noterMesure (seuil de panne)', () => {
  it('une mesure réussie rend le service disponible', () => {
    expect(noterMesure(sondeInitiale(), true, 1000).etat).toBe('ok')
  })

  it('un seul échec ne déclare pas de panne : pas de bandeau sur un hoquet', () => {
    const s = noterMesure(noterMesure(sondeInitiale(), true, 0), false, 1000)
    expect(s.etat).toBe('ok')
    expect(s.echecs).toBe(1)
  })

  it(`${SEUIL_ECHECS} échecs de suite déclarent la panne, datée du PREMIER échec`, () => {
    let s = noterMesure(sondeInitiale(), true, 0)
    s = noterMesure(s, false, 1000)
    s = noterMesure(s, false, 31000)
    expect(s.etat).toBe('ko')
    expect(s.premierEchec).toBe(1000)
  })

  it('un succès entre deux échecs remet le compteur à zéro', () => {
    let s = noterMesure(sondeInitiale(), false, 0)
    s = noterMesure(s, true, 1000)
    s = noterMesure(s, false, 2000)
    expect(s.etat).toBe('ok')
  })

  it('le retour après une panne déclarée est daté ; un retour sans panne ne l\'est pas', () => {
    let s = noterMesure(sondeInitiale(), false, 0)
    s = noterMesure(s, false, 1000)
    s = noterMesure(s, true, 5000)
    expect(s.etat).toBe('ok')
    expect(s.retablieA).toBe(5000)
    expect(noterMesure(noterMesure(sondeInitiale(), false, 0), true, 1000).retablieA).toBeNull()
  })

  it('au premier chargement, un échec isolé laisse l\'état inconnu', () => {
    expect(noterMesure(sondeInitiale(), false, 0).etat).toBe('inconnu')
  })
})

describe('libellés', () => {
  it('heure lisible', () => {
    expect(heureLisible(new Date(2026, 9, 1, 14, 2).getTime())).toBe('14 h 02')
    expect(heureLisible(new Date(2026, 9, 1, 9, 30).getTime())).toBe('9 h 30')
  })
})
