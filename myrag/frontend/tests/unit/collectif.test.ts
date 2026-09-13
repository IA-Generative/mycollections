import { describe, it, expect } from 'vitest'
import { ceQuiManque, chiffres, indexEtat, libelleEtat, libelleEvenement, messageErreur, progression, ROLES } from '../../utils/collectif'
import { normaliserCapacites } from '../../utils/capacites'

describe('les capacités ne se lisent qu’à true', () => {
  it('un « oui » ou un 1 ne sont pas vrais', () => {
    const c = normaliserCapacites({ demandes: 'oui', signalements: 1, seuil_chantier: 3 })
    expect(c.demandes).toBe(false)
    expect(c.signalements).toBe(false)
    expect(c.seuil_chantier).toBe(3)
  })
  it('un seuil absurde retombe au repli', () => {
    expect(normaliserCapacites({ seuil_chantier: 0 }).seuil_chantier).toBe(5)
    expect(normaliserCapacites({ seuil_chantier: '5' }).seuil_chantier).toBe(5)
    expect(normaliserCapacites(null).demandes).toBe(false)
  })
})

describe('la progression et ce qui manque (règle 2 : ET, jamais OU)', () => {
  it('3 / 5', () => {
    expect(progression(3, 5)).toEqual({ texte: '3 / 5', pourcent: 60, atteint: false })
    expect(progression(7, 5).pourcent).toBe(100)
  })
  it('cinq soutiens sans garant : il manque un garant', () => {
    expect(ceQuiManque({ nb_soutiens: 5, seuil: 5, garant: false, etat: 'ouverte' })).toBe('il manque un garant')
    expect(ceQuiManque({ nb_soutiens: 3, seuil: 5, garant: false, etat: 'ouverte' })).toBe('il manque 2 soutiens et un garant')
    expect(ceQuiManque({ nb_soutiens: 4, seuil: 5, garant: true, etat: 'ouverte' })).toBe('il manque 1 soutien')
    expect(ceQuiManque({ nb_soutiens: 5, seuil: 5, garant: true, etat: 'chantier' })).toBeNull()
  })
})

describe('les états d’une collection', () => {
  it('quatre étapes dans l’ordre', () => {
    expect(indexEtat('amorcee')).toBe(0)
    expect(indexEtat('publiee_tous')).toBe(3)
    expect(indexEtat(null)).toBe(0)
    expect(libelleEtat('en_controle')).toBe('En contrôle')
  })
})

describe('les rôles portent leur coût en temps', () => {
  it('quatre rôles, le garant en heures par mois', () => {
    expect(ROLES.map(r => r.valeur)).toEqual(['soutien', 'fournisseur', 'relecteur', 'garant'])
    expect(ROLES.find(r => r.valeur === 'garant')!.cout).toContain('mois')
    expect(ROLES.find(r => r.valeur === 'soutien')!.minutes).toBe(0)
  })
})

describe('le fil parle français et chiffre', () => {
  it('un forçage se lit', () => {
    expect(libelleEvenement('collection.etat', { de: 'amorcee', vers: 'publiee_tous', force: true })).toContain('Forçage')
    expect(libelleEvenement('seuil.atteint', { soutiens: 5 })).toBe('Seuil atteint : 5 soutiens et un garant')
    expect(chiffres({ lignes_importees: 1248, questions_testees: 20, taux: 0.85 })).toBe('lignes 1248 · questions testées 20 · taux 0.85')
  })
})

describe('le message d’erreur de l’API', () => {
  it('extrait le détail, y compris celui d’une validation', () => {
    expect(messageErreur(new Error('API error 422: {"detail":"Cette collection est en cours de vérification"}'))).toBe('Cette collection est en cours de vérification')
    expect(messageErreur(new Error('API error 422: {"detail":[{"msg":"Value error, Le titre est obligatoire"}]}'))).toBe('Le titre est obligatoire')
    expect(messageErreur(new Error('panne'))).toBe('panne')
  })
})
