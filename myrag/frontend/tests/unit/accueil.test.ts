import { describe, it, expect } from 'vitest'
import { indicateurs, nombre, portes, demandeEnVue, messageMerci } from '../../utils/accueil'

const CATS = [
  { cle: 'securite', libelle: 'Sécurité et délinquance', description: '', ordre: 20 },
  { cle: 'etrangers', libelle: 'Droit des étrangers', description: '', ordre: 10 },
  { cle: 'vide', libelle: 'Vide', description: '', ordre: 30 },
]
const COLS = [
  { name: 'a', categorie: 'securite', file_count: 17249 },
  { name: 'b', categorie: 'securite', file_count: 1919 },
  { name: 'c', categorie: 'etrangers', file_count: 3585 },
  { name: 'd', categorie: null },
  { name: 'e', categorie: 'disparue', file_count: 10 },
  { name: 'orpheline', orphan: true, file_count: 999 },
]

describe('indicateurs', () => {
  it('compte ce que la personne peut lire, sans les partitions sans fiche', () => {
    expect(indicateurs(COLS, CATS)).toEqual({ collections: 5, categories: 2, documents: 22763 })
  })
  it('tient sur un catalogue vide', () => {
    expect(indicateurs([], [])).toEqual({ collections: 0, categories: 0, documents: 0 })
  })
})

describe('nombre', () => {
  it('sépare les milliers à la française', () => {
    expect(nombre(31400)).toBe('31 400')
    expect(nombre(412)).toBe('412')
    expect(nombre(1234567)).toBe('1 234 567')
  })
})

describe('portes', () => {
  it("suit l'ordre de l'administration et cache les catégories vides", () => {
    expect(portes(COLS, CATS)).toEqual([
      { cle: 'etrangers', libelle: 'Droit des étrangers', nb: 1 },
      { cle: 'securite', libelle: 'Sécurité et délinquance', nb: 2 },
    ])
  })
})

describe('demandeEnVue', () => {
  const d = (id: string, etat: string, nb: number, seuil = 5) => ({ id, titre: id, etat, nb_soutiens: nb, seuil })
  it("montre l'ouverte la plus proche du seuil", () => {
    expect(demandeEnVue([d('loin', 'ouverte', 1), d('proche', 'ouverte', 4), d('chantier', 'chantier', 5), d('close', 'close', 4)])?.id).toBe('proche')
  })
  it('ne montre rien quand aucune n\'est ouverte', () => {
    expect(demandeEnVue([d('chantier', 'chantier', 6), d('close', 'close', 0)])).toBeNull()
    expect(demandeEnVue([])).toBeNull()
  })
})

describe('messageMerci', () => {
  const col = (titre: string, questions: number, publiee = true) => ({ name: titre.toLowerCase(), titre, questions, publiee, signalements_ouverts: 0 })
  it('ne dit rien à qui ne gère rien', () => {
    expect(messageMerci(null)).toBeNull()
    expect(messageMerci({ collections: [], actives: 0, questions: 0, personnes: null, fenetre_jours: 30 })).toBeNull()
  })
  it('dit à quoi le partage a servi, et nomme la plus consultée', () => {
    const m = messageMerci({ collections: [col('Marchés', 131), col('FAQ', 268)], actives: 2, questions: 399, personnes: 57, fenetre_jours: 30 })!
    expect(m.titre).toContain('travaillent pour vos collègues')
    expect(m.texte).toContain('57 collègues ont trouvé')
    expect(m.texte).toContain('« FAQ »')
    expect(m.action.vers).toBe('/admin/create')
  })
  it('sous le seuil de personnes, ne donne pas de nombre', () => {
    const m = messageMerci({ collections: [col('FAQ', 2)], actives: 1, questions: 2, personnes: null, fenetre_jours: 30 })!
    expect(m.texte.startsWith('Des collègues ont trouvé')).toBe(true)
  })
  it('sans question, invite à faire connaître — pas un zéro sec', () => {
    const m = messageMerci({ collections: [col('FAQ', 0)], actives: 1, questions: 0, personnes: null, fenetre_jours: 30 })!
    expect(m.titre).toContain('faites-les connaître')
    expect(m.action.vers).toBe('/c/faq')
  })
  it('ne dit pas « personne » à qui vient d’y poser ses propres questions', () => {
    const m = messageMerci({ collections: [col('CESEDA', 0)], actives: 1, questions: 0, mes_essais: 6, personnes: null, fenetre_jours: 30 })!
    expect(m.texte).toContain('Vos 6 essais ne comptent pas')
    expect(m.texte).toContain('aucun collègue')
    expect(m.texte).toContain('bac à sable')
    expect(m.texte).not.toContain('Personne')
    const un = messageMerci({ collections: [col('CESEDA', 0)], actives: 1, questions: 0, mes_essais: 1, personnes: null, fenetre_jours: 30 })!
    expect(un.texte).toContain('Votre essai ne compte pas')
  })
  it('rien de publié : invite à finir', () => {
    const m = messageMerci({ collections: [col('FAQ', 0, false)], actives: 0, questions: 0, personnes: null, fenetre_jours: 30 })!
    expect(m.titre).toContain('presque là')
  })
})
