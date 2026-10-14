import { describe, expect, it } from 'vitest'
import { lireConfigExecution } from '../../utils/configExecution'

describe('lireConfigExecution', () => {
  it('retient les clés connues', () => {
    expect(lireConfigExecution({
      myragApiUrl: '', keycloakUrl: 'https://sso.fake-domain.name/', keycloakRealm: 'mirai',
      keycloakClientId: 'mycollections-front', authEnabled: true, appTitle: 'Mes collections',
    })).toEqual({
      myragApiUrl: '', keycloakUrl: 'https://sso.fake-domain.name', keycloakRealm: 'mirai',
      keycloakClientId: 'mycollections-front', authEnabled: true, appTitle: 'Mes collections',
    })
  })
  it('ignore un fichier absent, vide ou mal formé', () => {
    for (const v of [null, undefined, 'texte', 42, [], {}]) expect(lireConfigExecution(v)).toEqual({})
  })
  it('ignore les clés inconnues et les mauvais types', () => {
    expect(lireConfigExecution({ autre: 'x', authEnabled: 'false', keycloakRealm: 3 })).toEqual({})
  })
  it("refuse un SSO qui n'est pas en https", () => {
    expect(lireConfigExecution({ keycloakUrl: 'http://sso.fake-domain.name' })).toEqual({})
    expect(lireConfigExecution({ keycloakUrl: 'javascript:alert(1)' })).toEqual({})
    expect(lireConfigExecution({ keycloakUrl: 'http://localhost:8082' })).toEqual({ keycloakUrl: 'http://localhost:8082' })
  })
  it('ne vide pas un realm ni un client', () => {
    expect(lireConfigExecution({ keycloakRealm: ' ', keycloakClientId: '' })).toEqual({})
  })
})
