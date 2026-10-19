import { describe, expect, it } from 'vitest'
import { actionsFiche, apercuConsignes, dateFiche, ligneMeta, ONGLET_PAR_DEFAUT, ongletDepuisAncien, ongletsFiche } from '../../utils/fiche'

describe('actionsFiche', () => {
  it('un lecteur n\'a ni Partager, ni Réglages, ni Ajouter des documents', () => {
    const { principales, plus } = actionsFiche({ ecrire: false }, true, 'code-exemple')
    expect(principales.map(a => a.libelle)).toEqual(['Poser une question'])
    expect(plus.map(a => a.libelle)).toEqual(['Liens entre documents'])
    expect(actionsFiche(null, true, 'x').principales.map(a => a.cle)).toEqual(['question'])
  })
  it('qui gère a Partager, et le menu Plus complet', () => {
    const { principales, plus } = actionsFiche({ ecrire: true }, true, 'code-exemple')
    expect(principales.map(a => `${a.libelle} ${a.vers}`)).toEqual(['Poser une question /c/code-exemple/playground', 'Partager /c/code-exemple/publish'])
    expect(plus.map(a => `${a.libelle} ${a.vers}`)).toEqual([
      'Ajouter des documents /c/code-exemple/upload',
      'Réglages /c/code-exemple/config',
      'Liens entre documents /c/code-exemple/graph',
    ])
  })
  it('« Liens entre documents » désactivé sans graphe, et il dit pourquoi', () => {
    const sans = actionsFiche({ ecrire: true }, false, 'x').plus.find(a => a.cle === 'graphe')!
    expect(sans.desactivee).toBe(true)
    expect(sans.aide).toContain('activés')
    expect(actionsFiche({ ecrire: true }, true, 'x').plus.find(a => a.cle === 'graphe')!.desactivee).toBe(false)
  })
  it('l\'identifiant est encodé', () => {
    expect(actionsFiche({ ecrire: false }, false, 'a/b').principales[0]!.vers).toBe('/c/a%2Fb/playground')
  })
})

describe('ongletsFiche', () => {
  it('exactement quatre onglets, dans l\'ordre, compteurs dans les libellés', () => {
    expect(ongletsFiche({ documents: 312, signalements: 2, propositions: 1 })).toEqual([
      { cle: 'documents', libelle: 'Documents (312)' },
      { cle: 'signalements', libelle: 'Signalements (2)' },
      { cle: 'propositions', libelle: 'Propositions (1)' },
      { cle: 'historique', libelle: 'Historique' },
    ])
  })
  it('un compteur inconnu ne s\'affiche pas ; zéro s\'affiche', () => {
    expect(ongletsFiche({}).map(o => o.libelle)).toEqual(['Documents', 'Signalements', 'Propositions', 'Historique'])
    expect(ongletsFiche({ signalements: 0, documents: null })[1]!.libelle).toBe('Signalements (0)')
  })
  it('l\'onglet de l\'agent s\'ajoute en dernier quand Mes agents est branché', () => {
    expect(ongletsFiche({}, { agent: true }).map(o => o.cle)).toEqual(['documents', 'signalements', 'propositions', 'historique', 'agent'])
  })
  it('l\'onglet par défaut est Documents', () => {
    expect(ONGLET_PAR_DEFAUT).toBe('documents')
  })
})

describe('ongletDepuisAncien', () => {
  it.each([
    ['consulter', { type: 'onglet', cle: 'historique' }],
    ['discussion', { type: 'onglet', cle: 'historique' }],
    ['signaler', { type: 'onglet', cle: 'signalements' }],
    ['proposer', { type: 'onglet', cle: 'propositions' }],
    ['prompt', { type: 'ancre', cle: 'consignes' }],
    ['feedback', { type: 'page', vers: '/c/code-exemple/qualite?onglet=avis' }],
    ['qr', { type: 'page', vers: '/c/code-exemple/qualite' }],
    ['generation', { type: 'page', vers: '/c/code-exemple/qualite' }],
  ])('« %s » est redirigé', (cle, attendu) => {
    expect(ongletDepuisAncien(cle, 'code-exemple')).toEqual(attendu)
  })
  it('une clé actuelle ou inconnue n\'est pas redirigée', () => {
    expect(ongletDepuisAncien('documents', 'x')).toBeNull()
    expect(ongletDepuisAncien('n-importe-quoi', 'x')).toBeNull()
    expect(ongletDepuisAncien(undefined, 'x')).toBeNull()
  })
})

describe('ligneMeta', () => {
  it('les cinq éléments, séparés par des points médians', () => {
    expect(ligneMeta({ categorie_libelle: 'Droit et codes', nb_documents: 312, cree_le: '12 mars 2026', mise_a_jour: 'il y a 4 jours', responsable: 'Mission d\'exemple' }))
      .toBe('Droit et codes · 312 documents · créée le 12 mars 2026 · mise à jour il y a 4 jours · Mission d\'exemple')
  })
  it('sans élément vide : rien d\'inconnu ne laisse un « ·  · »', () => {
    expect(ligneMeta({ nb_documents: 1, responsable: '  ' })).toBe('1 document')
    expect(ligneMeta({})).toBe('')
    expect(ligneMeta({ categorie_libelle: '', nb_documents: 0 })).toBe('0 document')
  })
})

describe('apercuConsignes', () => {
  const CONSIGNES = 'Ligne 1.\nLigne 2.\nLigne 3.\nLigne 4.\nLigne 5.'
  it('borné à quatre lignes, et dit qu\'il en reste', () => {
    expect(apercuConsignes(CONSIGNES)).toEqual({ texte: 'Ligne 1.\nLigne 2.\nLigne 3.\nLigne 4.', tronque: true })
    expect(apercuConsignes('Court.')).toEqual({ texte: 'Court.', tronque: false })
    expect(apercuConsignes(CONSIGNES, 2).texte).toBe('Ligne 1.\nLigne 2.')
  })
  it('borné en longueur', () => {
    const r = apercuConsignes('x'.repeat(2000))
    expect(r.texte.length).toBeLessThanOrEqual(601)
    expect(r.tronque).toBe(true)
  })
  it('du texte : une balise reste une suite de caractères', () => {
    expect(apercuConsignes('<img src=x onerror=alert(1)>').texte).toBe('<img src=x onerror=alert(1)>')
    expect(apercuConsignes(null)).toEqual({ texte: '', tronque: false })
  })
})

describe('dateFiche', () => {
  it('une date du serveur, sans fuseau, lue en UTC et écrite en français', () => {
    expect(dateFiche('2026-03-12T09:00:00')).toBe('12 mars 2026')
    expect(dateFiche('2026-10-15T09:00:00', false)).toBe('15 oct.')
  })
  it('absente ou illisible : vide', () => {
    expect(dateFiche(null)).toBe('')
    expect(dateFiche('pas une date')).toBe('')
  })
})
