import type { BilanPartage } from '../../utils/accueil'
import { describe, expect, it } from 'vitest'
import { CLE_NON_CLASSEES, impactDuPartage, indicateurs, indicateursCollection, messageImpact, nombre, porteNonClassees, portes, tuilesAccueil } from '../../utils/accueil'

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
  it('suit l\'ordre de l\'administration et cache les catégories vides', () => {
    expect(portes(COLS, CATS)).toEqual([
      { cle: 'etrangers', libelle: 'Droit des étrangers', nb: 1 },
      { cle: 'securite', libelle: 'Sécurité et délinquance', nb: 2 },
    ])
  })
})

describe('porteNonClassees', () => {
  it('compte les collections sans catégorie ou d\'une catégorie disparue', () => {
    expect(porteNonClassees(COLS, CATS)).toEqual({ cle: CLE_NON_CLASSEES, libelle: 'Non classées', nb: 2 })
  })
  it('rien quand tout est classé', () => {
    expect(porteNonClassees([{ name: 'a', categorie: 'securite' }], CATS)).toBeNull()
  })
})

const col = (titre: string, questions: number, publiee = true) => ({ name: titre.toLowerCase(), titre, questions, publiee, signalements_ouverts: 0 })
const BILAN: BilanPartage = { collections: [col('FAQ', 12), col('Marchés', 3)], actives: 2, questions: 15, personnes: 7, signalements_ouverts: 2, fenetre_jours: 30 }

describe('impactDuPartage', () => {
  const COLS = [
    { name: 'faq', avis: { total: 84, satisfaction_rate: 0.92 } },
    { name: 'marchés', avis: { total: 16, satisfaction_rate: 0.5 } },
    { name: 'pas-a-moi', avis: { total: 1000, satisfaction_rate: 0 } },
  ]
  it('rien pour qui ne gère rien', () => {
    expect(impactDuPartage(null, COLS)).toBeNull()
    expect(impactDuPartage({ ...BILAN, collections: [] }, COLS)).toBeNull()
  })
  it('la note de MES collections, pondérée par le nombre d\'avis', () => {
    const i = impactDuPartage(BILAN, COLS)!
    expect(i.avis).toBe(100)
    expect(i.satisfaction).toBe(85) // (84 × 0,92 + 16 × 0,5) / 100 = 85,28
  })
  it('sans avis, pas de note', () => {
    expect(impactDuPartage(BILAN, [{ name: 'faq', avis: { total: 0, satisfaction_rate: null } }])!.satisfaction).toBeNull()
  })
  it('les chiffres du serveur, dont le seuil de 3 personnes, et la collection la plus utile', () => {
    const i = impactDuPartage(BILAN, COLS)!
    expect([i.personnes, i.questions, i.signalements, i.fenetre_jours]).toEqual([7, 15, 2, 30])
    expect(i.plusUtile).toEqual({ name: 'faq', titre: 'FAQ', questions: 12 })
    expect(impactDuPartage({ ...BILAN, personnes: null }, COLS)!.personnes).toBeNull()
    expect(impactDuPartage({ ...BILAN, collections: [col('FAQ', 0)], questions: 0 }, COLS)!.plusUtile).toBeNull()
  })
})

describe('messageImpact', () => {
  const base = { fenetre_jours: 30, actives: 1, questions: 0, personnes: null, satisfaction: null, avis: 0, signalements: 0, plusUtile: null }
  it('au-dessus du seuil : combien de collègues aidés', () => {
    expect(messageImpact({ ...base, questions: 15, personnes: 7 }).titre).toBe('Vous avez aidé 7 collègues en 30 jours.')
  })
  it('sous le seuil : les questions, sans nombre de personnes', () => {
    expect(messageImpact({ ...base, questions: 2 }).titre).toBe('Vos collections ont répondu à 2 questions de collègues en 30 jours.')
  })
  it('publiée mais pas encore interrogée : faire connaître, pas un zéro sec', () => {
    expect(messageImpact(base).titre).toContain('faites-les connaître')
  })
  it('rien de publié : finir la vérification', () => {
    expect(messageImpact({ ...base, actives: 0 }).titre).toContain('presque là')
  })
})

describe('tuilesAccueil', () => {
  const EXEMPLE = { name: 'code-route', titre: 'Code de la route', question: 'Quelle sanction pour un feu rouge ?', autres: true }
  const CHIFFRES = { collections: 27, categories: 6, documents: 0 }
  it('exactement quatre tuiles, dans l\'ordre décidé', () => {
    expect(tuilesAccueil({ assistants: false }, EXEMPLE, CHIFFRES).map(t => t.titre)).toEqual([
      'Découvrir',
      'Explorer le catalogue',
      'Suivre mes collections',
      'Partager une nouvelle collection',
    ])
  })
  it('« & assistants » seulement si le drapeau est vrai', () => {
    const t = tuilesAccueil({ assistants: true }, EXEMPLE, CHIFFRES)
    expect(t[2]!.titre).toBe('Suivre mes collections & assistants')
    expect(t[3]!.titre).toBe('Partager une nouvelle collection & assistant')
    expect(tuilesAccueil({ assistants: false }, EXEMPLE, CHIFFRES).some(x => x.titre.includes('assistant'))).toBe(false)
  })
  it('les cibles : bac à sable prérempli, catalogue, mes collections, création', () => {
    const [decouvrir, explorer, gerer, creer] = tuilesAccueil({ assistants: false }, EXEMPLE, CHIFFRES)
    expect(decouvrir!.vers).toEqual({ path: '/c/code-route/playground', query: { q: 'Quelle sanction pour un feu rouge ?' } })
    expect(decouvrir!.description).toBe('« Quelle sanction pour un feu rouge ? »')
    expect(explorer!.vers).toBe('/admin/catalog')
    expect(gerer!.vers).toBe('/mes-collections')
    expect(creer!.vers).toBe('/admin/create')
    expect(creer!.description).toContain('sans compétence technique')
  })
  it('sans exemple, Découvrir mène au catalogue', () => {
    const t = tuilesAccueil({ assistants: false }, null, null)[0]!
    expect(t.vers).toBe('/admin/catalog')
    expect(t.action).toBe('Voir le catalogue')
  })
  it('le nombre de collections dans la phrase du catalogue, quand il est connu', () => {
    expect(tuilesAccueil({ assistants: false }, null, CHIFFRES)[1]!.description).toContain('27 collections')
    expect(tuilesAccueil({ assistants: false }, null, null)[1]!.description).not.toMatch(/\d/)
  })
  it('aucune tuile ne parle d\'une donnée manquante', () => {
    const textes = tuilesAccueil({ assistants: true }, EXEMPLE, CHIFFRES).map(t => `${t.titre} ${t.description} ${t.action} ${t.mention || ''}`).join(' ')
    expect(textes).not.toMatch(/manque|demande/i)
  })
})

describe('indicateursCollection', () => {
  it('l\'usage du serveur et la note des usagers, arrondie', () => {
    expect(indicateursCollection({ questions: 12, signalements_ouverts: 1 }, { avis: { total: 84, satisfaction_rate: 0.9166 } }))
      .toEqual({ questions: 12, satisfaction: 92, avis: 84, signalements: 1 })
  })
  it('sans avis, pas de note', () => {
    expect(indicateursCollection({ questions: 0, signalements_ouverts: 0 }, { avis: { total: 0, satisfaction_rate: null } }).satisfaction).toBeNull()
    expect(indicateursCollection({ questions: 0, signalements_ouverts: 0 }, null)).toEqual({ questions: 0, satisfaction: null, avis: 0, signalements: 0 })
  })
})
