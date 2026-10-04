import { describe, expect, it } from 'vitest'
import { adresseCourante, cheminDeRetour } from '../../utils/retour'

describe('cheminDeRetour', () => {
  it('rejoue un chemin interne, requête et ancre comprises', () => {
    expect(cheminDeRetour('/c/codes-natinf?onglet=documents#x')).toBe('/c/codes-natinf?onglet=documents#x')
    expect(adresseCourante({ pathname: '/guide', search: '', hash: '' })).toBe('/guide')
  })
  it("refuse tout ce qui sortirait de l'application", () => {
    for (const v of ['https://exemple.fake-domain.name/', '//exemple.fake-domain.name', '/\\exemple', 'javascript:alert(1)', '', null, 42]) {
      expect(cheminDeRetour(v)).toBe('/')
    }
  })
  it('ne revient ni sur le retour du SSO ni sur la déconnexion', () => {
    expect(cheminDeRetour('/auth/callback?code=x')).toBe('/')
    expect(cheminDeRetour('/deconnexion')).toBe('/')
  })
})
