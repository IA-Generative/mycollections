import { describe, it, expect } from 'vitest'
import { titreDe, titreDepuisNom, filtrerCollections, grouperParCategorie, cleDepuisLibelle, NON_CLASSEES } from '../../utils/catalogue'

const CATS = [
  { cle: 'securite', libelle: 'Sécurité et délinquance', description: '', ordre: 20 },
  { cle: 'etrangers', libelle: 'Droit des étrangers', description: '', ordre: 10 },
  { cle: 'vide', libelle: 'Rubrique vide', description: '', ordre: 30 },
]
const COLS = [
  { name: 'amorce-natinf', titre: 'Codes NATINF', categorie: 'securite', description: 'Nomenclature des infractions' },
  { name: 'amorce-ssmsi-delinquance', titre: 'Délinquance enregistrée (SSMSI)', categorie: 'securite' },
  { name: 'ceseda-legifrance', titre: 'CESEDA — articles en vigueur', categorie: 'etrangers' },
  { name: 'demo-teletravail', titre: '', categorie: null },
  { name: 'rag-perdu', titre: 'Rubrique retirée', categorie: 'n-existe-plus' },
]

describe('titreDe', () => {
  it('montre le titre de la fiche', () => {
    expect(titreDe(COLS[0])).toBe('Codes NATINF')
  })
  it("à défaut, rend l'identifiant lisible sans son préfixe de provenance", () => {
    expect(titreDe(COLS[3])).toBe('Teletravail')
    expect(titreDepuisNom('amorce-ta-caa-ceseda')).toBe('TA CAA CESEDA')
    expect(titreDepuisNom('dgef-sdst-faq')).toBe('DGEF SDST FAQ')
  })
  it("ne retire pas un préfixe s'il ne reste rien, et tolère le vide", () => {
    expect(titreDepuisNom('amorce-')).toBe('Amorce')
    expect(titreDepuisNom('')).toBe('')
    expect(titreDe(null)).toBe('')
  })
})

describe('filtrerCollections', () => {
  it('ignore les accents et la casse', () => {
    expect(filtrerCollections(COLS, 'delinquance').map(c => c.name)).toEqual(['amorce-ssmsi-delinquance'])
    expect(filtrerCollections(COLS, 'CÉSEDA').map(c => c.name)).toEqual(['ceseda-legifrance'])
  })
  it("trouve par le titre, par l'identifiant ou par la description", () => {
    expect(filtrerCollections(COLS, 'natinf')).toHaveLength(1)
    expect(filtrerCollections(COLS, 'amorce-')).toHaveLength(2)
    expect(filtrerCollections(COLS, 'infractions')).toHaveLength(1)
  })
  it('exige tous les mots, dans le désordre', () => {
    expect(filtrerCollections(COLS, 'natinf codes')).toHaveLength(1)
    expect(filtrerCollections(COLS, 'natinf ceseda')).toHaveLength(0)
  })
  it('rend tout sur une requête vide', () => {
    expect(filtrerCollections(COLS, '   ')).toHaveLength(COLS.length)
  })
})

describe('grouperParCategorie', () => {
  it("suit l'ordre de l'administration et trie par titre dans une rubrique", () => {
    const g = grouperParCategorie(COLS, CATS)
    expect(g.map(x => x.libelle)).toEqual(['Droit des étrangers', 'Sécurité et délinquance', NON_CLASSEES])
    expect(g[1].collections.map(c => c.name)).toEqual(['amorce-natinf', 'amorce-ssmsi-delinquance'])
  })
  it('range en dernier ce qui n\'a pas de rubrique, ou une rubrique disparue', () => {
    const dernier = grouperParCategorie(COLS, CATS).at(-1)!
    expect(dernier.cle).toBeNull()
    expect(dernier.collections.map(c => c.name).sort()).toEqual(['demo-teletravail', 'rag-perdu'])
  })
  it('cache les rubriques vides au catalogue, les garde pour l\'administration', () => {
    expect(grouperParCategorie(COLS, CATS).some(g => g.cle === 'vide')).toBe(false)
    expect(grouperParCategorie(COLS, CATS, true).some(g => g.cle === 'vide')).toBe(true)
  })
  it('ne perd ni ne double aucune collection', () => {
    const total = grouperParCategorie(COLS, CATS).reduce((n, g) => n + g.collections.length, 0)
    expect(total).toBe(COLS.length)
  })
  it('sans rubrique du tout, une seule section', () => {
    expect(grouperParCategorie(COLS, []).map(g => g.libelle)).toEqual([NON_CLASSEES])
  })
})

describe('cleDepuisLibelle', () => {
  it('translittère au lieu de supprimer les accents', () => {
    expect(cleDepuisLibelle('Droit des étrangers')).toBe('droit-des-etrangers')
    expect(cleDepuisLibelle('  Sécurité & délinquance ! ')).toBe('securite-delinquance')
  })
})
