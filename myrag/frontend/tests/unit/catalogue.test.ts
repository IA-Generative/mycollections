import { describe, expect, it } from 'vitest'
import { cleDepuisLibelle, COLONNES_CATALOGUE, filtrerCollections, grouperParCategorie, ilYa, libelleAvis, ligneCatalogue, lireDate, NON_CLASSEES, titreDe, titreDepuisNom, trierCollections } from '../../utils/catalogue'

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
  it('à défaut, rend l\'identifiant lisible sans son préfixe de provenance', () => {
    expect(titreDe(COLS[3])).toBe('Teletravail')
    expect(titreDepuisNom('amorce-ta-caa-ceseda')).toBe('TA CAA CESEDA')
    expect(titreDepuisNom('dgef-sdst-faq')).toBe('DGEF SDST FAQ')
  })
  it('ne retire pas un préfixe s\'il ne reste rien, et tolère le vide', () => {
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
  it('trouve par le titre, par l\'identifiant ou par la description', () => {
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
  it('suit l\'ordre de l\'administration et trie par titre dans une rubrique', () => {
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

describe('cOLONNES_CATALOGUE', () => {
  it('les six colonnes de la maquette, dans l\'ordre, ni Source ni Actions', () => {
    expect([...COLONNES_CATALOGUE]).toEqual(['Collection', 'État', 'Créée le', 'Mise à jour', 'Avis des usagers', 'Responsable'])
    expect(COLONNES_CATALOGUE).not.toContain('Source')
    expect(COLONNES_CATALOGUE).not.toContain('Actions')
  })
})

describe('ilYa', () => {
  const maintenant = new Date('2026-10-19T12:00:00Z')
  const avant = (jours: number) => new Date(maintenant.getTime() - jours * 86_400_000)
  it.each([
    [0, 'aujourd\'hui'],
    [1, 'hier'],
    [6, 'il y a 6 jours'],
    [7, 'il y a 1 semaine'],
    [19, 'il y a 2 semaines'],
    [30, 'il y a 4 semaines'],
    [31, 'il y a 1 mois'],
    [125, 'il y a 4 mois'],
  ])('%i jours → %s', (jours, attendu) => {
    expect(ilYa(avant(jours), maintenant)).toBe(attendu)
  })
  it('une date dans le futur se lit « aujourd\'hui »', () => {
    expect(ilYa(new Date('2026-10-20T12:00:00Z'), maintenant)).toBe('aujourd\'hui')
  })
})

describe('lireDate', () => {
  it('une date sans fuseau est lue en UTC', () => {
    expect(lireDate('2026-10-19T08:00:00')?.toISOString()).toBe('2026-10-19T08:00:00.000Z')
    expect(lireDate('2026-10-19T08:00:00+02:00')?.toISOString()).toBe('2026-10-19T06:00:00.000Z')
  })
  it('absente ou illisible : null', () => {
    expect(lireDate(null)).toBeNull()
    expect(lireDate('')).toBeNull()
    expect(lireDate('pas une date')).toBeNull()
  })
})

describe('libelleAvis', () => {
  it('« Pas encore d\'avis » à total 0', () => {
    expect(libelleAvis({ total: 0, satisfaction_rate: null })).toEqual({ taux: null, detail: 'Pas encore d\'avis' })
    expect(libelleAvis(undefined)).toEqual({ taux: null, detail: 'Pas encore d\'avis' })
  })
  it('un taux arrondi et le nombre d\'avis', () => {
    expect(libelleAvis({ total: 84, satisfaction_rate: 0.9166 })).toEqual({ taux: '92 %', detail: '84 avis' })
    expect(libelleAvis({ total: 22, satisfaction_rate: 0.6363 })).toEqual({ taux: '64 %', detail: '22 avis' })
    expect(libelleAvis({ total: 1, satisfaction_rate: 0 })).toEqual({ taux: '0 %', detail: '1 avis' })
  })
})

describe('ligneCatalogue', () => {
  const maintenant = new Date('2026-10-19T12:00:00Z')
  it('ce qu\'une ligne affiche', () => {
    const l = ligneCatalogue({
      name: 'code-exemple',
      titre: 'Code d\'exemple',
      description: 'Pour la démonstration.',
      created_at: '2026-03-12T09:00:00',
      updated_at: '2026-10-01T09:00:00',
      derniere_mise_a_jour: '2026-10-15T09:00:00',
      avis: { total: 84, satisfaction_rate: 0.92 },
      contact_name: 'Mission d\'exemple',
      contact_email: 'contact@fake-domain.name',
      publication: { state: 'published', targets: [{ app: 'assistant', model_id: 'openrag-code-exemple' }] },
    }, maintenant)
    expect(l.titre).toBe('Code d\'exemple')
    expect(l.etat).toEqual({ libelle: 'Publiée', classe: 'fr-badge--success' })
    expect(l.creeeLe).toBe('12 mars 2026')
    expect(l.miseAJour).toEqual({ date: '15 oct. 2026', ilYa: 'il y a 4 jours' })
    expect(l.avis.taux).toBe('92 %')
    expect(l.responsable).toEqual({ nom: 'Mission d\'exemple', courriel: 'contact@fake-domain.name' })
  })
  it('archivée l\'emporte sur l\'état de partage ; sans date, un tiret', () => {
    const l = ligneCatalogue({ name: 'x', archived_at: '2026-10-01T00:00:00', publication: { state: 'published' } }, maintenant)
    expect(l.etat.libelle).toBe('Archivée')
    expect(l.creeeLe).toBe('—')
    expect(l.miseAJour).toEqual({ date: '—', ilYa: null })
  })
})

describe('trierCollections', () => {
  const c = (name: string, maj: string | null, total: number, rate: number | null, titre = name) =>
    ({ name, titre, derniere_mise_a_jour: maj, avis: { total, satisfaction_rate: rate } })
  const LISTE = [
    c('a', '2026-10-01T00:00:00', 10, 0.5, 'Bravo'),
    c('b', '2026-10-18T00:00:00', 0, null, 'alpha'),
    c('c', null, 4, 0.9, 'Charlie'),
    c('d', '2026-10-18T00:00:00', 3, 0.5, 'Delta'),
  ]
  it('mise à jour récente : la plus récente d\'abord, sans date en dernier, stable à égalité', () => {
    expect(trierCollections(LISTE, 'recente').map(x => x.name)).toEqual(['b', 'd', 'a', 'c'])
  })
  it('satisfaction : la meilleure d\'abord, les collections sans avis en dernier, stable', () => {
    expect(trierCollections(LISTE, 'satisfaction').map(x => x.name)).toEqual(['c', 'a', 'd', 'b'])
  })
  it('titre : ordre alphabétique, sans tenir compte de la casse', () => {
    expect(trierCollections(LISTE, 'titre').map(x => x.name)).toEqual(['b', 'a', 'c', 'd'])
  })
  it('ne modifie pas la liste reçue', () => {
    const copie = [...LISTE]
    trierCollections(LISTE, 'titre')
    expect(LISTE).toEqual(copie)
  })
})
