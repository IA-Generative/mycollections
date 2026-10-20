import type { Consigne, PlanAssistant, QuestionSource } from '../../utils/assistants'
import { describe, expect, it } from 'vitest'
import {
  candidatesFiables,
  consignePourEnvoi,
  consigneVide,
  deplacer,
  exemplesDepuisTexte,
  libelleQuand,
  libelleServie,
  libelleSeuil,
  lienQualite,
  ordonnerEtapes,
  phraseFiable,
  QUAND_TOUJOURS,
  reponsesFiables,
  resumeConsigne,
  resumeQualiteSource,
  sourceDuPassage,
  traceDuPlan,
  validerConsigne,
} from '../../utils/assistants'

const SOURCES = ['ceseda', 'guide-titres', 'accords']

function consigne (champs: Partial<Consigne> = {}): Consigne {
  return { id: 'pays-a-accord', quand: 'La personne vient d\'un pays lié par un accord', exemples: [], chercher: [{ source: 'accords' }], repondre: '', ...champs }
}

/** Une liste de N exemples distincts, construite case par case (pas de `.fill` d'un objet partagé). */
function exemples (n: number, longueur = 10): string[] {
  const liste: string[] = []
  for (let i = 0; i < n; i++) {
    liste.push(`${i}`.padEnd(longueur, 'x'))
  }
  return liste
}

describe('consigneVide', () => {
  it('une consigne vide, d\'identifiant conforme au contrat', () => {
    expect(consigneVide()).toEqual({ id: 'consigne-1', quand: '', exemples: [], chercher: [], repondre: '' })
  })
  it('un identifiant libre parmi ceux de la fiche', () => {
    expect(consigneVide([{ id: 'consigne-2' }, { id: 'autre' }]).id).toBe('consigne-3')
    expect(consigneVide([{ id: 'consigne-1' }]).id).toBe('consigne-2')
  })
  it('chaque appel rend un objet neuf (listes non partagées)', () => {
    const a = consigneVide()
    const b = consigneVide()
    a.exemples.push('x')
    expect(b.exemples).toEqual([])
  })
})

describe('libelleQuand', () => {
  it('la valeur réservée « toujours » se dit « Pour toute question »', () => {
    expect(libelleQuand(QUAND_TOUJOURS)).toBe('Pour toute question')
    expect(libelleQuand(' toujours ')).toBe('Pour toute question')
  })
  it('sinon la phrase, rognée', () => {
    expect(libelleQuand('  La question porte sur un titre de séjour ')).toBe('La question porte sur un titre de séjour')
    expect(libelleQuand(null)).toBe('')
  })
})

describe('validerConsigne', () => {
  it('une consigne complète est conforme', () => {
    expect(validerConsigne(consigne({ exemples: ['Mon conjoint est algérien'], chercher: [{ source: 'accords' }, { source: 'ceseda', avec: 'article_trouve' }], repondre: 'Citez l\'article.' }), SOURCES)).toEqual({})
  })
  it('« quand » est exigé, 500 caractères au plus', () => {
    expect(validerConsigne(consigne({ quand: '  ' }), SOURCES).quand).toBeTruthy()
    expect(validerConsigne(consigne({ quand: 'x'.repeat(501) }), SOURCES).quand).toContain('500')
    expect(validerConsigne(consigne({ quand: 'x'.repeat(500) }), SOURCES)).toEqual({})
  })
  it('dix exemples au plus, chacun de 1 à 500 caractères', () => {
    expect(validerConsigne(consigne({ exemples: exemples(10) }), SOURCES)).toEqual({})
    expect(validerConsigne(consigne({ exemples: exemples(11) }), SOURCES).exemples).toContain('10')
    expect(validerConsigne(consigne({ exemples: ['   '] }), SOURCES).exemples).toBeTruthy()
    expect(validerConsigne(consigne({ exemples: exemples(1, 501) }), SOURCES).exemples).toContain('500')
  })
  it('« avec » refusé sur la première étape (le contrat le refuse)', () => {
    const e = validerConsigne(consigne({ chercher: [{ source: 'accords', avec: 'article_trouve' }] }), SOURCES)
    expect(e.chercher).toContain('première étape')
  })
  it('« avec » suit le motif du relais', () => {
    expect(validerConsigne(consigne({ chercher: [{ source: 'accords' }, { source: 'ceseda', avec: 'Article trouvé' }] }), SOURCES).chercher).toContain('minuscules')
    expect(validerConsigne(consigne({ chercher: [{ source: 'accords' }, { source: 'ceseda', avec: '' }] }), SOURCES)).toEqual({})
  })
  it('une étape cherche dans une source de l\'assistant', () => {
    expect(validerConsigne(consigne({ chercher: [{ source: 'inconnue' }] }), SOURCES).chercher).toContain('Étape 1')
    expect(validerConsigne(consigne({ chercher: [{ source: '' }] }), SOURCES).chercher).toBeTruthy()
  })
  it('consigne de rédaction : 4000 caractères au plus', () => {
    expect(validerConsigne(consigne({ repondre: 'x'.repeat(4001) }), SOURCES).repondre).toContain('4000')
  })
  it('une seule consigne « pour toute question », des identifiants distincts', () => {
    const autre = consigne({ id: 'generale', quand: QUAND_TOUJOURS })
    expect(validerConsigne(consigne({ quand: QUAND_TOUJOURS }), SOURCES, [autre]).quand).toContain('Une seule')
    expect(validerConsigne(consigne({ id: 'generale' }), SOURCES, [autre]).id).toBeTruthy()
    expect(validerConsigne(consigne({ id: 'Pas Bon' }), SOURCES).id).toBeTruthy()
  })
})

describe('ordonnerEtapes', () => {
  const ETAPES = [{ source: 'accords' }, { source: 'ceseda', avec: 'article_trouve' }, { source: 'guide-titres' }]
  it('déplace une étape, sans toucher la liste reçue', () => {
    const r = ordonnerEtapes(ETAPES, 2, 0)
    expect(r.map(e => e.source)).toEqual(['guide-titres', 'accords', 'ceseda'])
    expect(ETAPES.map(e => e.source)).toEqual(['accords', 'ceseda', 'guide-titres'])
  })
  it('la nouvelle première étape perd son « avec »', () => {
    const r = ordonnerEtapes(ETAPES, 1, 0)
    expect(r[0]).toEqual({ source: 'ceseda', avec: null })
    expect(ETAPES[1]!.avec).toBe('article_trouve')
  })
  it('hors bornes : la liste, inchangée', () => {
    expect(ordonnerEtapes(ETAPES, 0, 5)).toEqual(ETAPES)
    expect(ordonnerEtapes(ETAPES, -1, 0)).toEqual(ETAPES)
  })
  it('après le retrait de la première étape, la nouvelle première perd aussi son « avec »', () => {
    expect(ordonnerEtapes(ETAPES.slice(1), 0, 0)[0]).toEqual({ source: 'ceseda', avec: null })
  })
})

describe('deplacer', () => {
  it('d\'un cran, sans effet aux bords', () => {
    expect(deplacer(['a', 'b', 'c'], 1, -1)).toEqual(['b', 'a', 'c'])
    expect(deplacer(['a', 'b', 'c'], 2, 1)).toEqual(['a', 'b', 'c'])
    expect(deplacer(['a', 'b', 'c'], 0, -1)).toEqual(['a', 'b', 'c'])
  })
})

describe('saisie et envoi', () => {
  it('les exemples, un par ligne', () => {
    expect(exemplesDepuisTexte(' Première question \n\n  Deuxième\n')).toEqual(['Première question', 'Deuxième'])
  })
  it('la consigne envoyée : textes rognés, « avec » vide ou en première étape retiré, gabarit gardé', () => {
    const c = consignePourEnvoi(consigne({
      quand: ' Pays à accord ',
      exemples: [' a ', ''],
      chercher: [{ source: 'accords', avec: 'x_y' }, { source: 'ceseda', avec: ' ' }, { source: 'guide-titres', avec: 'article_trouve' }],
      repondre: ' Citez. ',
      gabarit: 'juridique',
    }))
    expect(c).toEqual({
      id: 'pays-a-accord',
      quand: 'Pays à accord',
      exemples: ['a'],
      chercher: [{ source: 'accords' }, { source: 'ceseda' }, { source: 'guide-titres', avec: 'article_trouve' }],
      repondre: 'Citez.',
      gabarit: 'juridique',
    })
  })
  it('le résumé d\'une consigne', () => {
    const titres: Record<string, string> = { accords: 'Accords', ceseda: 'Code' }
    expect(resumeConsigne(consigne({ exemples: ['a', 'b'], chercher: [{ source: 'accords' }, { source: 'ceseda' }] }), id => titres[id] || id)).toBe('2 exemples · Accords → Code')
    expect(resumeConsigne(consigne({ chercher: [] }))).toBe('Sources choisies par l\'assistant')
  })
})

describe('traceDuPlan', () => {
  const PLAN: PlanAssistant = {
    assistant: 'sejour',
    version: 1,
    planificateur: 'regles',
    consigne: 'pays-a-accord',
    score_consigne: 0.83,
    reponse_fiable: null,
    etapes: [
      { n: 2, source: 'ceseda', question: 'q', attend: [] },
      { n: 1, source: 'accords', question: 'q', attend: [] },
      { n: 3, source: 'guide-titres', question: 'q', attend: [1, 2], avec: 'article_trouve' },
    ],
    sources_ignorees: 1,
  }
  const FICHE = {
    sources: [{ id: 'accords', type: 'collection' as const, regime: 'toujours' as const }, { id: 'ceseda', type: 'collection' as const, regime: 'selon_question' as const }, { id: 'guide-titres', type: 'collection' as const, regime: 'selon_question' as const }, { id: 'faq', type: 'collection' as const, regime: 'sur_consigne' as const }],
    consignes: [consigne()],
  }
  const titres: Record<string, string> = { accords: 'Accords', ceseda: 'Code', faq: 'Questions fréquentes' }
  const titre = (id: string) => titres[id] || id

  it('la consigne retenue, dite par son « quand », et sa confiance', () => {
    const t = traceDuPlan(PLAN, FICHE, titre)
    expect(t.methode).toBe('Selon les consignes')
    expect(t.consigne).toEqual({ id: 'pays-a-accord', libelle: 'La personne vient d\'un pays lié par un accord', score: 83 })
  })
  it('les étapes dans l\'ordre, ce dont elles partent, leurs passages', () => {
    const t = traceDuPlan(PLAN, FICHE, titre, { duree_ms: 412, passages: [{ source: 'accords', etape: 1, rang: 1, document: 'd', texte: 't' }, { source: 'accords', etape: 1, rang: 2, document: 'd', texte: 't' }] })
    expect(t.etapes.map(e => [e.n, e.titre, e.passages])).toEqual([[1, 'Accords', 2], [2, 'Code', 0], [3, 'guide-titres', 0]])
    expect(t.etapes[2]).toMatchObject({ apres: [1, 2], avec: 'article_trouve' })
    expect(t.duree).toBe('0,4 s')
  })
  it('les sources non interrogées sont nommées ; les écartées (hors droit) seulement comptées', () => {
    const t = traceDuPlan(PLAN, FICHE, titre)
    expect(t.nonInterrogees).toEqual(['Questions fréquentes'])
    expect(t.ecartees).toBe(1)
  })
  it('sans consigne, sans fiche, une consigne inconnue de la fiche', () => {
    expect(traceDuPlan({ ...PLAN, consigne: null }, null).consigne).toBeNull()
    expect(traceDuPlan(PLAN, null).nonInterrogees).toEqual([])
    expect(traceDuPlan({ ...PLAN, consigne: 'autre', score_consigne: null }, FICHE).consigne).toEqual({ id: 'autre', libelle: 'autre', score: null })
  })
  it('une réponse fiable retenue', () => {
    expect(traceDuPlan({ ...PLAN, etapes: [], reponse_fiable: { id: 'qa-1', score: 0.95 } }, FICHE).reponseFiable).toBe(true)
  })
})

describe('sourceDuPassage', () => {
  it('un passage devient une puce : titre, source, page, texte, lien', () => {
    expect(sourceDuPassage({ source: 'ceseda', etape: 1, rang: 1, document: 'art-l423', titre: 'Article L423-1', page: 3, texte: 'Texte', url: null }, () => 'Code')).toEqual({
      original_filename: 'ceseda/art-l423',
      libelle: 'Article L423-1',
      titre_document: 'Article L423-1 — Code',
      page: 3,
      content: 'Texte',
      chunk_url: undefined,
    })
  })
  it('sans titre : le document', () => {
    expect(sourceDuPassage({ source: 's', etape: 1, rang: 1, document: 'doc', texte: '' }).libelle).toBe('doc')
  })
})

describe('réponses fiables et qualité d\'un assistant', () => {
  const q = (champs: Partial<QuestionSource> = {}): QuestionSource => ({
    id: 'q1',
    collection: 'col-a',
    collection_titre: 'Collection A',
    peut_gerer: true,
    question: 'Quel délai ?',
    reponse: 'Trente jours.',
    relecture: 'valide',
    hors_sujet: false,
    fiable: false,
    servie_fois: 0,
    dernier_verdict: null,
    ...champs,
  })

  it('le seuil se dit en mots', () => {
    expect(libelleSeuil(0.9)).toContain('au moins 90 %')
    expect(libelleSeuil(0.755)).toContain('au moins 76 %')
    expect(libelleSeuil(undefined)).toContain('90 %')
  })
  it('combien de fois servie', () => {
    expect(libelleServie(0)).toBe('Jamais servie')
    expect(libelleServie(1)).toBe('Servie 1 fois')
    expect(libelleServie(12)).toBe('Servie 12 fois')
  })
  it('les réponses fiables : les plus servies d\'abord', () => {
    const l = reponsesFiables([q({ id: 'a', fiable: true, servie_fois: 1 }), q({ id: 'b' }), q({ id: 'c', fiable: true, servie_fois: 5 })])
    expect(l.map(x => x.id)).toEqual(['c', 'a'])
  })
  it('les candidates : validées, avec réponse, ni hors sujet ni déjà fiables', () => {
    const l = candidatesFiables([
      q({ id: 'ok' }),
      q({ id: 'fiable', fiable: true }),
      q({ id: 'brut', relecture: 'brut' }),
      q({ id: 'rejete', relecture: 'rejete' }),
      q({ id: 'hs', hors_sujet: true }),
      q({ id: 'vide', reponse: '  ' }),
    ])
    expect(l.map(x => x.id)).toEqual(['ok'])
  })
  it('la phrase de la trace', () => {
    expect(phraseFiable(95)).toBe('Réponse fiable retenue (ressemblance 95 %) : aucune recherche')
    expect(phraseFiable(null)).toBe('Réponse fiable retenue : aucune recherche')
  })
  it('la trace d\'une réponse fiable porte la ressemblance en pourcentage', () => {
    const plan: PlanAssistant = { assistant: 'a', version: 1, planificateur: 'regles', reponse_fiable: { id: 'qa-1', score: 0.946 }, etapes: [] }
    expect(traceDuPlan(plan, null).scoreFiable).toBe(95)
    expect(traceDuPlan({ ...plan, reponse_fiable: null }, null).scoreFiable).toBeNull()
  })
  it('le lien vers la page Qualité d\'une collection', () => {
    expect(lienQualite('ma-col')).toBe('/c/ma-col/qualite')
  })
  it('le résumé d\'une source, au singulier comme au pluriel', () => {
    expect(resumeQualiteSource({ reponses_fiables: 0, servie_fois: 0, synthese: { questions: { total: 0 } } })).toBe('Aucune question de référence ; aucune réponse fiable.')
    expect(resumeQualiteSource({ reponses_fiables: 2, servie_fois: 3, synthese: { questions: { total: 4, par_relecture: { valide: 3 } } } }))
      .toBe('4 questions de référence, dont 3 validées ; 2 réponses fiables (servie 3 fois au total).')
  })
})
