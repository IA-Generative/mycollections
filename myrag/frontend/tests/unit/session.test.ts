import { describe, expect, it, vi } from 'vitest'
import { avecRenouvellement, contenuJwt, delaiAvantRenouvellement } from '../../utils/session'

const reponse = (status: number) => new Response(null, { status })

describe('la session qui expire', () => {
  it('un appel accepté ne renouvelle rien', async () => {
    const renouveler = vi.fn(async () => true)
    const expiree = vi.fn()
    expect((await avecRenouvellement(async () => reponse(200), renouveler, expiree)).status).toBe(200)
    expect(renouveler).not.toHaveBeenCalled()
    expect(expiree).not.toHaveBeenCalled()
  })

  it('un 401 se rejoue une fois après un renouvellement réussi', async () => {
    const faire = vi.fn().mockResolvedValueOnce(reponse(401)).mockResolvedValueOnce(reponse(200))
    const expiree = vi.fn()
    expect((await avecRenouvellement(faire, async () => true, expiree)).status).toBe(200)
    expect(faire).toHaveBeenCalledTimes(2)
    expect(expiree).not.toHaveBeenCalled()
  })

  it('un renouvellement impossible : la session est finie, on le signale', async () => {
    const faire = vi.fn(async () => reponse(401))
    const expiree = vi.fn()
    expect((await avecRenouvellement(faire, async () => false, expiree)).status).toBe(401)
    expect(faire).toHaveBeenCalledTimes(1)
    expect(expiree).toHaveBeenCalledTimes(1)
  })

  it('un 401 malgré un jeton neuf : la session est inutilisable, on le signale', async () => {
    const faire = vi.fn(async () => reponse(401))
    const expiree = vi.fn()
    expect((await avecRenouvellement(faire, async () => true, expiree)).status).toBe(401)
    expect(faire).toHaveBeenCalledTimes(2)
    expect(expiree).toHaveBeenCalledTimes(1)
  })
})

describe('garder la session ouverte', () => {
  const t0 = 1_800_000_000_000 // ms
  const s = t0 / 1000
  it('renouvelle avant la première échéance : le jeton de rafraîchissement (10 min) avant l\'accès (15 min)', () => {
    expect(delaiAvantRenouvellement(t0, s + 900, s + 600)).toBe((600 - 180) * 1000)
    expect(delaiAvantRenouvellement(t0, s + 300, s + 600)).toBe((300 - 180) * 1000)
  })
  it('jamais trop tôt ni dans le passé ; rien à planifier sans échéance', () => {
    expect(delaiAvantRenouvellement(t0, s + 30, s + 600)).toBe(5000)
    expect(delaiAvantRenouvellement(t0, null, undefined)).toBeNull()
  })
  it('lit l\'échéance d\'un jeton', () => {
    const jeton = `x.${btoa(JSON.stringify({ exp: 123, typ: 'Refresh' })).replace(/=+$/, '')}.y`
    expect(contenuJwt(jeton)).toEqual({ exp: 123, typ: 'Refresh' })
    expect(contenuJwt('opaque')).toBeNull()
    expect(contenuJwt(null)).toBeNull()
  })
})
