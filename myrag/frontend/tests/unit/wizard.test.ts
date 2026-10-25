import { describe, expect, it } from 'vitest'
import { REGLES_PAR_DEFAUT } from '../../utils/collectionName'
import { bilanVerification, cartesDeSource, chargeAuJeu, completerQuestions, ETAPES_ASSISTANT, etapesEnPhrase, etapeSuivante, identifiantPropose, lienEtape, ligneBientot, plierQuestion, questionsSuggerees, REGLAGES_AVANCES_DEFAUT, reglagesAvancesDefaut, replierReglagesAvances, resumeCreation, SOURCES, trouverQuestion, verdictTechnique } from '../../utils/wizard'

describe('les étapes de l\'assistant', () => {
  it('les cinq libellés, dans l\'ordre', () => {
    expect([...ETAPES_ASSISTANT]).toEqual(['Source', 'Identification', 'Documents', 'Vérifier les réponses', 'Partage'])
  })
  it('« Étape suivante » de chaque étape, rien après la cinquième', () => {
    expect([1, 2, 3, 4, 5].map(etapeSuivante)).toEqual(['Identification', 'Documents', 'Vérifier les réponses', 'Partage', null])
    expect(etapeSuivante(0)).toBe('Source')
  })
  it('en phrase, pour l\'accueil et l\'administration', () => {
    expect(etapesEnPhrase()).toBe('source, identification, documents, vérifier les réponses, partage')
  })
})

describe('les sources', () => {
  it('seules les sources disponibles sont des cartes', () => {
    expect(cartesDeSource().map(s => s.cle)).toEqual(['file', 'directory'])
    expect(cartesDeSource().every(s => s.disponible)).toBe(true)
  })
  it('la ligne « Bientôt » liste toutes les autres, et seulement elles', () => {
    expect(ligneBientot()).toBe('Bientôt : Légifrance, Fichiers, Nextcloud, Résana, un site web, un outil MCP.')
    const autres = SOURCES.filter(s => !s.disponible).length
    expect(cartesDeSource().length + autres).toBe(SOURCES.length)
  })
  it('une source branchée quitte la ligne et devient une carte', () => {
    const branchee = SOURCES.map(s => (s.cle === 'nextcloud' ? { ...s, disponible: true } : s))
    expect(cartesDeSource(branchee).map(s => s.cle)).toContain('nextcloud')
    expect(ligneBientot(branchee)).not.toContain('Nextcloud')
  })
  it('rien à annoncer : pas de ligne', () => {
    expect(ligneBientot(SOURCES.map(s => ({ ...s, disponible: true })))).toBe('')
  })
})

describe('replierReglagesAvances', () => {
  it('replié aux valeurs par défaut', () => {
    expect(replierReglagesAvances({ ...REGLAGES_AVANCES_DEFAUT }, {})).toBe(true)
    expect(replierReglagesAvances({}, {})).toBe(true)
  })
  it.each([
    ['profil', 'juridique'],
    ['sensitivity', 'internal'],
    ['graph_enabled', true],
    ['ai_summary_enabled', true],
    ['identifiant_manuel', true],
  ])('ouvert si « %s » diffère du défaut', (champ, valeur) => {
    expect(replierReglagesAvances({ ...REGLAGES_AVANCES_DEFAUT, [champ]: valeur }, {})).toBe(false)
  })
  it('ouvert sur une erreur d\'un de ses champs, pas sur celle d\'un autre', () => {
    expect(replierReglagesAvances(REGLAGES_AVANCES_DEFAUT, { name: 'Cet identifiant est déjà pris.' })).toBe(false)
    expect(replierReglagesAvances(REGLAGES_AVANCES_DEFAUT, { titre: 'Donnez un titre.' })).toBe(true)
    expect(replierReglagesAvances(REGLAGES_AVANCES_DEFAUT, { name: '' })).toBe(true)
  })
  it('le défaut dépend de la source : un dossier est un corpus', () => {
    const defaut = reglagesAvancesDefaut('directory')
    expect(defaut.profil).toBe('corpus')
    expect(replierReglagesAvances({ ...defaut }, {}, defaut)).toBe(true)
    expect(reglagesAvancesDefaut('file').profil).toBe('generique')
  })
})

describe('identifiantPropose', () => {
  it('d\'après le titre, conforme aux règles', () => {
    expect(identifiantPropose('Codes NATINF', [])).toBe('codes-natinf')
  })
  it('suffixé s\'il est pris, au premier suffixe libre', () => {
    expect(identifiantPropose('Codes NATINF', ['codes-natinf'])).toBe('codes-natinf-2')
    expect(identifiantPropose('Codes NATINF', new Set(['codes-natinf', 'codes-natinf-2']))).toBe('codes-natinf-3')
  })
  it('le suffixe tient dans la longueur permise', () => {
    const titre = 'Recueil des circulaires relatives aux procédures administratives'
    const base = identifiantPropose(titre, [])
    const suffixe = identifiantPropose(titre, [base])
    expect(suffixe.length).toBeLessThanOrEqual(REGLES_PAR_DEFAUT.max)
    expect(suffixe.endsWith('-2')).toBe(true)
  })
  it('un titre qui ne donne rien d\'acceptable ne propose rien', () => {
    expect(identifiantPropose('', [])).toBe('')
    expect(identifiantPropose('!!', [])).toBe('')
  })
})

describe('questionsSuggerees', () => {
  it('trois au plus, sans vide ni doublon', () => {
    expect(questionsSuggerees({ questions: [' A quoi sert ? ', 'A quoi sert ?', '', 'x', 'Q2 ?', 'Q3 ?', 'Q4 ?'] })).toEqual(['A quoi sert ?', 'Q2 ?', 'Q3 ?'])
  })
  it('une réponse inattendue ne casse rien', () => {
    expect(questionsSuggerees(null)).toEqual([])
    expect(questionsSuggerees({ questions: 'pas une liste' })).toEqual([])
    expect(questionsSuggerees({ questions: [1, null, 'Vraie question ?'] })).toEqual(['Vraie question ?'])
  })
})

describe('verdictTechnique', () => {
  it('répond : un texte, au moins un passage, pas de refus', () => {
    expect(verdictTechnique({ response: 'Le délai est de deux mois.', source_names: ['note.md'] }).cle).toBe('repond')
    expect(verdictTechnique({ response: 'Deux mois.', sources: [{}] }).cle).toBe('repond')
  })
  it('ne répond pas sans passage, et dit pourquoi', () => {
    const v = verdictTechnique({ response: 'Deux mois.', source_names: [] })
    expect(v.cle).toBe('ne_repond_pas')
    expect(v.aide).toContain('indexation')
  })
  it('ne répond pas sur un refus, même avec des passages', () => {
    const v = verdictTechnique({ response: 'Je ne trouve pas cette information dans les documents.', source_names: ['note.md'] })
    expect(v.cle).toBe('ne_repond_pas')
    expect(v.aide).toContain('sort peut-être')
    expect(verdictTechnique({ response: 'Les documents ne contiennent pas de réponse.', source_names: ['a'] }).cle).toBe('ne_repond_pas')
  })
  it('ne répond pas sans texte', () => {
    expect(verdictTechnique({ response: '  ', source_names: ['a'] }).cle).toBe('ne_repond_pas')
    expect(verdictTechnique(null).cle).toBe('ne_repond_pas')
  })
})

describe('chargeAuJeu', () => {
  it('une question posée entre au jeu « à relire », sans réponse de référence', () => {
    expect(chargeAuJeu('  Quel délai ?  ')).toEqual({ question: 'Quel délai ?', relecture: 'brut' })
  })
  it('rien pour une question trop courte', () => {
    expect(chargeAuJeu('ab')).toBeNull()
    expect(chargeAuJeu('')).toBeNull()
  })
})

describe('completerQuestions', () => {
  it('remplit les cases vides avec les suggestions, dans l\'ordre', () => {
    expect(completerQuestions(['', '', ''], ['A ?', 'B ?'])).toEqual(['A ?', 'B ?', ''])
  })
  it('garde une question déjà tapée quand la suggestion arrive après', () => {
    expect(completerQuestions(['Ma question ?', ' ', ''], ['A ?', 'B ?', 'C ?'])).toEqual(['Ma question ?', 'B ?', 'C ?'])
  })
})

describe('lienEtape', () => {
  it('une collection ordinaire suit les étapes 3 à 5 de l\'assistant', () => {
    expect(lienEtape(3, 'ma-collection')).toBe('/admin/create/step-3?collection=ma-collection')
    expect(lienEtape(5, 'ma-collection', 'drive')).toBe('/admin/create/step-5?collection=ma-collection')
  })

  it('une collection Fichiers suit son indexation à l\'étape 3 et garde sa source jusqu\'au partage', () => {
    expect(lienEtape(3, 'fichiers-beta-d1', 'fichiers')).toBe('/admin/create/fichiers?collection=fichiers-beta-d1')
    expect(lienEtape(5, 'fichiers-beta-d1', 'fichiers')).toBe('/admin/create/step-5?collection=fichiers-beta-d1&source=fichiers')
  })

  it('une collection Résana suit son indexation à l\'étape 3 et garde sa source jusqu\'au partage', () => {
    expect(lienEtape(3, 'resana-206', 'resana')).toBe('/admin/create/resana?collection=resana-206')
    expect(lienEtape(4, 'resana-206', 'resana')).toBe('/admin/create/step-4?collection=resana-206&source=resana')
    expect(lienEtape(5, 'resana-206', 'resana')).toBe('/admin/create/step-5?collection=resana-206&source=resana')
  })
})

describe('étape 4 : bilan et retrouvailles', () => {
  const repond = { cle: 'repond' as const, libelle: 'La collection répond' }
  const non = { cle: 'ne_repond_pas' as const, libelle: 'La collection ne répond pas' }

  it('sans question posée, le bilan invite sans bloquer', () => {
    const b = bilanVerification([])
    expect(b.posees).toBe(0)
    expect(b.phrase).toContain('aucune question')
  })

  it('compte les avis et les sans-avis', () => {
    const b = bilanVerification([
      { verdict: repond, validation: 'oui' },
      { verdict: repond, validation: 'non' },
      { verdict: non, validation: null },
      { verdict: null, validation: null },
    ])
    expect([b.posees, b.repondent, b.oui, b.non, b.sansAvis]).toEqual([3, 2, 1, 1, 1])
    expect(b.phrase).toBe('3 questions posées : 1 réponse jugée bonne, 1 insuffisante, 1 sans avis. Tout est dans le jeu de questions de la collection.')
  })

  it('accorde au pluriel quand toutes sont validées', () => {
    expect(bilanVerification([{ verdict: repond, validation: 'oui' }, { verdict: repond, validation: 'oui' }]).phrase)
      .toContain('2 réponses jugées bonnes, 0 insuffisante, 0 sans avis')
  })

  it('retrouve une question sans tenir compte des accents, de la casse ni de la ponctuation', () => {
    expect(plierQuestion('  Quel est le DÉLAI, exactement ?! ')).toBe('quel est le delai exactement')
    const liste = [{ id: 'a', question: 'Quel est le délai ?' }, { id: 'b', question: 'Autre' }]
    expect(trouverQuestion(liste, 'quel est le delai')?.id).toBe('a')
    expect(trouverQuestion(liste, 'inconnue')).toBeNull()
  })
})

describe('resumeCreation', () => {
  it('une collection de fichiers, sans question ni partage', () => {
    const r = resumeCreation({ titre: 'Essai', documents: 12, questions: { total: 0, validees: 0 } })
    expect(r.faits).toEqual(['Collection « Essai » créée.', '12 documents indexés.', 'Aucune question posée pour l\'instant.'])
    expect(r.aFaire[0]).toContain('Partager')
    expect(r.aFaire.some(a => a.includes('grille de contrôle'))).toBe(true)
  })

  it('une collection Résana en cours d\'import, partagée', () => {
    const r = resumeCreation({ titre: 'Alpha', documents: null, resana: { documents: 50, etat: 'en_cours', total: 783 }, questions: { total: 3, validees: 2 }, sensibilite: 'Interne', groupes: ['/g/equipe'] })
    expect(r.faits).toContain('Import Résana en cours : 50 documents déjà indexés sur 783.')
    expect(r.faits).toContain('3 questions posées, 2 réponses validées.')
    expect(r.faits).toContain('Partagée dans le chat MirAI avec le groupe « /g/equipe ».')
    expect(r.aFaire.some(a => a.includes('Partager'))).toBe(false)
    expect(r.aFaire.some(a => a.includes('fin de l\'indexation'))).toBe(true)
    expect(r.aFaire.some(a => a.includes('grille de contrôle'))).toBe(false)
  })
})
