import { describe, expect, it } from 'vitest'
import { canauxActifs, etatAssistant, ficheDepuisFormulaire, libelleRegime, ligneFenetre, resumeSources, validerFormulaire } from '../../utils/assistants'

const FORM = { titre: ' Séjour des étrangers ', identifiant: 'sejour-etrangers', description: ' Titres et procédures. ', rubrique: 'droit-etrangers', sources: [{ id: 'ceseda', regime: 'toujours' as const }, { id: 'guide-titres', regime: 'selon_question' as const }] }

describe('validerFormulaire', () => {
  it('un formulaire complet est prêt', () => {
    expect(validerFormulaire(FORM)).toEqual({})
  })
  it('titre, identifiant et au moins une source sont exigés', () => {
    const e = validerFormulaire({ ...FORM, titre: '  ', identifiant: 'Pas Bon', sources: [] })
    expect(Object.keys(e).sort()).toEqual(['identifiant', 'sources', 'titre'])
  })
  it('vingt sources au plus, comme le contrat', () => {
    const sources = Array.from({ length: 21 }, (_, i) => ({ id: `col-${i}`, regime: 'toujours' as const }))
    expect(validerFormulaire({ ...FORM, sources }).sources).toContain('Vingt')
  })
})

describe('ficheDepuisFormulaire', () => {
  it('la fiche du contrat : sources rangées dans l\'ordre choisi, aucun canal ouvert', () => {
    const f = ficheDepuisFormulaire(FORM)
    expect(f).toMatchObject({ contrat: 1, assistant: 'sejour-etrangers', titre: 'Séjour des étrangers', rubrique: 'droit-etrangers', description: 'Titres et procédures.', consignes: [] })
    expect(f.sources).toEqual([{ id: 'ceseda', type: 'collection', regime: 'toujours', rang: 1 }, { id: 'guide-titres', type: 'collection', regime: 'selon_question', rang: 2 }])
    expect(Object.values(f.publication).every(v => v === false)).toBe(true)
  })
  it('sans catégorie : null', () => {
    expect(ficheDepuisFormulaire({ ...FORM, rubrique: '' }).rubrique).toBeNull()
  })
})

describe('libellés', () => {
  it('le régime dit sans jargon', () => {
    expect(libelleRegime('selon_question')).toBe('Si la question s\'y rapporte')
    expect(libelleRegime('sur_consigne')).toBe('Seulement si une consigne la cite')
  })
  it('brouillon ou version', () => {
    expect(etatAssistant(null).libelle).toBe('Brouillon')
    expect(etatAssistant(3)).toEqual({ libelle: 'Version 3', classe: 'fr-badge--success' })
  })
  it('les canaux ouverts', () => {
    expect(canauxActifs({ socle: true, api: true })).toEqual(['Mon assistant', 'L\'API'])
    expect(canauxActifs(null)).toEqual([])
  })
  it('les sources, sans nommer celles que l\'on ne lit pas', () => {
    expect(resumeSources(3, 0)).toBe('3 sources')
    expect(resumeSources(1, 1)).toBe('2 sources, dont 1 que vous ne pouvez pas lire')
  })
})

describe('ligneFenetre', () => {
  it('la ligne à coller, échappée', () => {
    expect(ligneFenetre('sejour-etrangers', 'https://collections.fake-domain.name/')).toBe('<script src="https://collections.fake-domain.name/fenetre.js" data-assistant="sejour-etrangers" defer></script>')
    expect(ligneFenetre('a"b', 'https://x')).toContain('data-assistant="a&quot;b"')
  })
})
