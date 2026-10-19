import { describe, expect, it } from 'vitest'
import { CAPACITES_DEFAUT, normaliserCapacites } from '../../utils/capacites'

describe('normaliserCapacites', () => {
  it('seul `true` active un drapeau, jamais une valeur « vraie »', () => {
    expect(normaliserCapacites({ demandes: 'oui', signalements: 1, seuil_chantier: 3 })).toEqual({ demandes: false, signalements: false, seuil_chantier: 3 })
    expect(normaliserCapacites({ demandes: true, signalements: true })).toEqual({ demandes: true, signalements: true, seuil_chantier: 5 })
  })
  it('un seuil hors bornes ou non entier garde le défaut', () => {
    expect(normaliserCapacites({ seuil_chantier: 0 }).seuil_chantier).toBe(5)
    expect(normaliserCapacites({ seuil_chantier: 1001 }).seuil_chantier).toBe(5)
    expect(normaliserCapacites({ seuil_chantier: 2.5 }).seuil_chantier).toBe(5)
    expect(normaliserCapacites({ seuil_chantier: '7' }).seuil_chantier).toBe(5)
  })
  it('rien, ou pas un objet : les défauts', () => {
    expect(normaliserCapacites(null)).toEqual(CAPACITES_DEFAUT)
    expect(normaliserCapacites('demandes')).toEqual(CAPACITES_DEFAUT)
    expect(normaliserCapacites(undefined)).toEqual(CAPACITES_DEFAUT)
  })
  it('un drapeau inconnu est ignoré', () => {
    expect(normaliserCapacites({ assistants: true })).toEqual(CAPACITES_DEFAUT)
  })
  it('ne modifie pas le repli reçu', () => {
    const repli = { ...CAPACITES_DEFAUT }
    normaliserCapacites({ demandes: true }, repli)
    expect(repli).toEqual(CAPACITES_DEFAUT)
  })
})
