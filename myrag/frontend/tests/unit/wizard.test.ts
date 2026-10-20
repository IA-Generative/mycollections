import { describe, expect, it } from 'vitest'
import { REGLES_PAR_DEFAUT } from '../../utils/collectionName'
import { cartesDeSource, chargeAuJeu, completerQuestions, ETAPES_ASSISTANT, etapesEnPhrase, etapeSuivante, identifiantPropose, ligneBientot, questionsSuggerees, REGLAGES_AVANCES_DEFAUT, reglagesAvancesDefaut, replierReglagesAvances, SOURCES, verdictTechnique } from '../../utils/wizard'

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
    expect(ligneBientot()).toBe('Bientôt : Légifrance, Drive, Nextcloud, Resana, un site web, un outil MCP.')
    const autres = SOURCES.filter(s => !s.disponible).length
    expect(cartesDeSource().length + autres).toBe(SOURCES.length)
  })
  it('une source branchée quitte la ligne et devient une carte', () => {
    const branchee = SOURCES.map(s => (s.cle === 'drive' ? { ...s, disponible: true } : s))
    expect(cartesDeSource(branchee).map(s => s.cle)).toContain('drive')
    expect(ligneBientot(branchee)).not.toContain('Drive')
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
