import { describe, expect, it } from 'vitest'
import { CAPACITES_DEFAUT, normaliserCapacites } from '../../utils/capacites'

describe('normaliserCapacites', () => {
  it('seul `true` active un drapeau, jamais une valeur « vraie »', () => {
    expect(normaliserCapacites({ demandes: 'oui', signalements: 1, assistants: 'true', seuil_chantier: 3 })).toEqual({ ...CAPACITES_DEFAUT, seuil_chantier: 3 })
    expect(normaliserCapacites({ demandes: true, signalements: true })).toEqual({ ...CAPACITES_DEFAUT, demandes: true, signalements: true })
    expect(normaliserCapacites({ assistants: true, entraide: true })).toEqual({ ...CAPACITES_DEFAUT, assistants: true, entraide: true })
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
    expect(normaliserCapacites({ inconnu: true })).toEqual(CAPACITES_DEFAUT)
  })
  it('ne modifie pas le repli reçu', () => {
    const repli = { ...CAPACITES_DEFAUT }
    normaliserCapacites({ demandes: true }, repli)
    expect(repli).toEqual(CAPACITES_DEFAUT)
  })
})
