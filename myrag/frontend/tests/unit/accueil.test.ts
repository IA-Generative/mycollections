import type { BilanPartage } from '../../utils/accueil'
import { describe, expect, it } from 'vitest'
import { CLE_NON_CLASSEES, indicateurs, indicateursDeGestion, nombre, porteNonClassees, portes, tuilesAccueil } from '../../utils/accueil'

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

describe('indicateursDeGestion', () => {
  it('rien pour qui ne gère rien', () => {
    expect(indicateursDeGestion(null)).toEqual([])
    expect(indicateursDeGestion({ ...BILAN, collections: [] })).toEqual([])
  })
  it('les quatre chiffres de la maquette', () => {
    expect(indicateursDeGestion(BILAN)).toEqual([
      { valeur: 2, libelle: 'collections actives' },
      { valeur: 15, libelle: 'questions de collègues en 30 jours' },
      { valeur: 7, libelle: 'collègues aidés' },
      { valeur: 2, libelle: 'signalements à traiter', alerte: true },
    ])
  })
  it('seuil de 3 personnes : sous le seuil le serveur rend null, pas de « collègues aidés »', () => {
    expect(indicateursDeGestion({ ...BILAN, personnes: null }).map(k => k.libelle)).not.toContain('collègues aidés')
    expect(indicateursDeGestion({ ...BILAN, personnes: 3 }).find(k => k.libelle === 'collègues aidés')?.valeur).toBe(3)
  })
  it('la fenêtre du serveur est reprise dans le libellé', () => {
    expect(indicateursDeGestion(BILAN)[1]!.libelle).toBe('questions de collègues en 30 jours')
    expect(indicateursDeGestion({ ...BILAN, fenetre_jours: 7 })[1]!.libelle).toBe('questions de collègues en 7 jours')
  })
  it('aucun signalement : pas de KPI de signalement', () => {
    expect(indicateursDeGestion({ ...BILAN, signalements_ouverts: 0 }).some(k => k.alerte)).toBe(false)
    expect(indicateursDeGestion({ ...BILAN, signalements_ouverts: undefined })).toHaveLength(3)
  })
  it('accorde au singulier', () => {
    const un = indicateursDeGestion({ ...BILAN, actives: 1, questions: 1, signalements_ouverts: 1 })
    expect(un.map(k => k.libelle)).toEqual(['collection active', 'question de collègues en 30 jours', 'collègues aidés', 'signalement à traiter'])
  })
})

describe('tuilesAccueil', () => {
  const EXEMPLE = { name: 'code-route', titre: 'Code de la route', question: 'Quelle sanction pour un feu rouge ?', autres: true }
  const CHIFFRES = { collections: 27, categories: 6, documents: 0 }
  it('exactement quatre tuiles, dans l\'ordre décidé', () => {
    expect(tuilesAccueil({ assistants: false }, BILAN, EXEMPLE, CHIFFRES).map(t => t.titre)).toEqual([
      'Découvrir',
      'Explorer le catalogue',
      'Gérer mes collections',
      'Créer une nouvelle collection',
    ])
  })
  it('« & assistants » seulement si le drapeau est vrai', () => {
    const t = tuilesAccueil({ assistants: true }, BILAN, EXEMPLE, CHIFFRES)
    expect(t[2]!.titre).toBe('Gérer mes collections & assistants')
    expect(t[3]!.titre).toBe('Créer une nouvelle collection & assistant')
    expect(tuilesAccueil({ assistants: false }, BILAN, EXEMPLE, CHIFFRES).some(x => x.titre.includes('assistant'))).toBe(false)
  })
  it('les cibles : bac à sable prérempli, catalogue, mes collections, création', () => {
    const [decouvrir, explorer, gerer, creer] = tuilesAccueil({ assistants: false }, BILAN, EXEMPLE, CHIFFRES)
    expect(decouvrir!.vers).toEqual({ path: '/c/code-route/playground', query: { q: 'Quelle sanction pour un feu rouge ?' } })
    expect(decouvrir!.action).toBe('Essayer cette question')
    expect(explorer!.vers).toBe('/admin/catalog')
    expect(gerer!.vers).toBe('/mes-collections')
    expect(creer!.vers).toBe('/admin/create')
    expect(creer!.mention).toBe('Aucune compétence technique requise.')
  })
  it('sans exemple, Découvrir mène au catalogue', () => {
    const t = tuilesAccueil({ assistants: false }, null, null, null)[0]!
    expect(t.vers).toBe('/admin/catalog')
    expect(t.action).toBe('Voir le catalogue')
  })
  it('le nombre de collections à interroger, quand il est connu', () => {
    expect(tuilesAccueil({ assistants: false }, null, null, CHIFFRES)[1]!.kpis).toEqual([{ valeur: 27, libelle: 'collections à interroger' }])
    expect(tuilesAccueil({ assistants: false }, null, null, null)[1]!.kpis).toEqual([])
  })
  it('la tuile Gérer porte les indicateurs de gestion', () => {
    expect(tuilesAccueil({ assistants: false }, BILAN, null, null)[2]!.kpis).toEqual(indicateursDeGestion(BILAN))
    expect(tuilesAccueil({ assistants: false }, null, null, null)[2]!.kpis).toEqual([])
  })
  it('aucune tuile ne parle d\'une donnée manquante', () => {
    const textes = tuilesAccueil({ assistants: true }, BILAN, EXEMPLE, CHIFFRES).map(t => `${t.titre} ${t.description} ${t.action} ${t.mention || ''}`).join(' ')
    expect(textes).not.toMatch(/manque|demande/i)
  })
})
