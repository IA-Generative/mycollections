import { describe, expect, it, vi } from 'vitest'
import { avecRenouvellement } from '../../utils/session'

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

  it('un 401 malgré un jeton neuf n\'est pas une expiration', async () => {
    const expiree = vi.fn()
    expect((await avecRenouvellement(async () => reponse(401), async () => true, expiree)).status).toBe(401)
    expect(expiree).not.toHaveBeenCalled()
  })
})
