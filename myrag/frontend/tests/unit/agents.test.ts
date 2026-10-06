import { describe, it, expect } from 'vitest'
import {
  CONSIGNE, MESSAGE_MAX, PORTEE_OIDC_AGENTS, QUESTION_MAX,
  accepteCollection, cheminSigne, citationsDansLaReponse, construireMessage, libelleOrigine, lireFiches, lireReponse,
  messageErreurRecherche, neutraliser, normaliserErreurAgents, passagesDepuisRecherche, portesOidc, sourcesPourPuces,
  texteACopier, type Passage,
} from '../../utils/agents'

describe('portesOidc (la portée mesagents-agents)', () => {
  it("n'est demandée que si Mes agents est branché : un Keycloak refuse une portée non affectée", () => {
    expect(portesOidc('openid email profile basic', '')).toBe('openid email profile basic')
    expect(portesOidc('openid email profile basic', undefined)).toBe('openid email profile basic')
    expect(portesOidc('openid email profile basic', '   ')).toBe('openid email profile basic')
    expect(portesOidc('openid email profile basic', 'https://mesagents.fake-domain.name')).toBe(`openid email profile basic ${PORTEE_OIDC_AGENTS}`)
  })
  it('ne la demande pas deux fois', () => {
    expect(portesOidc(`openid ${PORTEE_OIDC_AGENTS}`, 'https://x')).toBe(`openid ${PORTEE_OIDC_AGENTS}`)
  })
})

describe('lireFiches (GET /api/v1/agents)', () => {
  const fiche = (sup: Record<string, unknown> = {}) => ({
    id: '7f3c', name: 'Rédacteur', description: 'Aide à rédiger', origin: 'shared', status: 'published',
    inputs: ['text', 'collection'], outputs: ['text'], model: '7f3c', url: 'https://mesagents.fake-domain.name/catalog/7f3c', ...sup,
  })

  it('ne garde que les agents qui acceptent une collection, dans l\'ordre du service', () => {
    const fiches = lireFiches({ agents: [
      fiche({ id: 'a', origin: 'mine' }),
      fiche({ id: 'b', inputs: ['text', 'selection'] }),
      fiche({ id: 'c' }),
    ] })
    expect(fiches.map(f => f.id)).toEqual(['a', 'c'])
    expect(accepteCollection({ inputs: ['collection'] })).toBe(true)
    expect(accepteCollection({ inputs: ['text'] })).toBe(false)
  })

  it('model est lu tel quel, sans supposer qu\'il vaut id', () => {
    expect(lireFiches({ agents: [fiche({ model: 'modele-x' })] })[0]!.model).toBe('modele-x')
  })

  it('ignore une valeur d\'entrée inconnue et une fiche mal formée', () => {
    const fiches = lireFiches({ agents: [
      fiche({ inputs: ['collection', 'hologramme'] }),
      { id: 'sans-nom', inputs: ['collection'] },
      'pas un objet',
      null,
      fiche({ id: 'dup' }), fiche({ id: 'dup' }),
    ] })
    expect(fiches.map(f => f.id)).toEqual(['7f3c', 'dup'])
    expect(fiches[0]!.inputs).toEqual(['collection'])
  })

  it('borne les textes et refuse une url qui n\'est pas https', () => {
    const f = lireFiches({ agents: [fiche({ name: 'n'.repeat(500), description: 'd'.repeat(5000), url: 'javascript:alert(1)', origin: 'autre', status: 'bizarre' })] })[0]!
    expect(f.name.length).toBe(200)
    expect(f.description.length).toBe(2000)
    expect(f.url).toBe('')
    expect(f.origin).toBe('shared')
    expect(f.status).toBe('published')
  })

  it('tolère une réponse vide ou étrangère', () => {
    expect(lireFiches(null)).toEqual([])
    expect(lireFiches({ agents: 'non' })).toEqual([])
    expect(lireFiches({})).toEqual([])
  })

  it('libellés d\'origine', () => {
    expect(libelleOrigine('mine')).toBe('Le vôtre')
    expect(libelleOrigine('shared')).toBe('Partagé par des collègues')
  })
})

describe('passagesDepuisRecherche (GET /api/v1/search)', () => {
  const reponse = {
    source: 'mycollections', query: 'oqtf', total: 2, results: [
      { id: 'ceseda:1', title: 'Article L. 611-1', url: 'https://mc.fake-domain.name/api/openrag/extract/a1?exp=1&sig=s1',
        hits: [
          { snippet: 'Premier passage', url: 'https://mc.fake-domain.name/api/openrag/extract/a1?exp=1&sig=s1', location: { page: 3 } },
          { snippet: 'Second passage', url: null, location: { page: null } },
          { snippet: '', url: null, location: {} },
        ] },
      { id: 'ceseda:2', title: '', url: null, hits: [{ snippet: 'Troisième', url: 'https://mc.fake-domain.name/api/openrag/extract/b2?exp=1&sig=s2', location: { page: 0 } }] },
    ],
  }

  it('aplatit les passages, numérotés dans l\'ordre, le lien du document en repli', () => {
    const p = passagesDepuisRecherche(reponse)
    expect(p.map(x => x.n)).toEqual([1, 2, 3])
    expect(p[0]).toEqual({ n: 1, titre: 'Article L. 611-1', snippet: 'Premier passage', url: 'https://mc.fake-domain.name/api/openrag/extract/a1?exp=1&sig=s1', page: 3 })
    expect(p[1]!.url).toBe('https://mc.fake-domain.name/api/openrag/extract/a1?exp=1&sig=s1')
    expect(p[1]!.page).toBeNull()
    expect(p[2]!.titre).toBe('Document')
    expect(p[2]!.page).toBeNull()
  })

  it('s\'arrête au maximum demandé', () => {
    expect(passagesDepuisRecherche(reponse, 2).length).toBe(2)
  })

  it('tolère une réponse vide', () => {
    expect(passagesDepuisRecherche(null)).toEqual([])
    expect(passagesDepuisRecherche({ results: [{ hits: 'non' }, null] })).toEqual([])
  })
})

describe('neutraliser (le bloc <<< … >>>)', () => {
  it('ne laisse jamais trois chevrons de suite, ni de retour à la ligne', () => {
    expect(neutraliser('a <<< b >>> c')).toBe('a << b >> c')
    expect(neutraliser('<<<<<\n>>>>>')).toBe('<< >>')
    expect(neutraliser('  x\n\ny  ')).toBe('x y')
    expect(neutraliser('a << b')).toBe('a << b')
  })
})

describe('construireMessage', () => {
  const passages: Passage[] = [
    { n: 1, titre: 'Article 1', snippet: 'Le texte <<<\n>>> piégé', url: null, page: null },
    { n: 2, titre: 'Article 2', snippet: 'Autre passage', url: null, page: 2 },
  ]

  it('suit la convention de contexte du contrat : question, consigne, passages entre <<< et >>>', () => {
    const { contenu, passages: gardes } = construireMessage('Que dit le code ?', passages)
    expect(contenu).toBe(
      `Que dit le code ?\n\n${CONSIGNE}\n\n<<<\n[1] Article 1 — Le texte << >> piégé\n[2] Article 2 — Autre passage\n>>>`,
    )
    expect(gardes.length).toBe(2)
    // Les seules lignes « <<< » et « >>> » sont les bornes du bloc.
    expect(contenu.split('\n').filter(l => l === '<<<' || l === '>>>')).toEqual(['<<<', '>>>'])
  })

  it('écarte les derniers passages quand le message dépasserait 20 000 caractères, et le dit', () => {
    const longs: Passage[] = Array.from({ length: 16 }, (_, i) => ({ n: i + 1, titre: `T${i + 1}`, snippet: 'x'.repeat(1000), url: null, page: null }))
    const { contenu, passages: gardes } = construireMessage('q', longs, 5000)
    expect(contenu.length).toBeLessThanOrEqual(5000)
    expect(gardes.length).toBe(4)
    expect(contenu.endsWith('\n>>>')).toBe(true)
    expect(construireMessage('q', longs).contenu.length).toBeLessThanOrEqual(MESSAGE_MAX)
  })

  it('borne la question à ce que la recherche accepte', () => {
    const { contenu } = construireMessage('q'.repeat(QUESTION_MAX + 50), [])
    expect(contenu.startsWith('q'.repeat(QUESTION_MAX) + '\n\n')).toBe(true)
  })
})

describe('lireReponse et citations', () => {
  it('lit choices[0].message.content, et rien d\'autre', () => {
    expect(lireReponse({ choices: [{ message: { role: 'assistant', content: 'Bonjour [1].' } }] })).toBe('Bonjour [1].')
    expect(lireReponse({ choices: [] })).toBe('')
    expect(lireReponse({ choices: [{ message: { content: 42 } }] })).toBe('')
    expect(lireReponse(null)).toBe('')
  })
  it('relève les [n] cités parmi les passages transmis', () => {
    expect([...citationsDansLaReponse('Selon [1] et [3], mais [9] et [0] n\'existent pas ; [2] oui.', 3)].sort()).toEqual([1, 2, 3])
    expect(citationsDansLaReponse('rien', 3).size).toBe(0)
  })
})

describe('sources sous la réponse', () => {
  it('cheminSigne garde le chemin ET la signature d\'un lien absolu vers notre proxy', () => {
    expect(cheminSigne('https://mc.fake-domain.name/api/openrag/extract/a1?exp=1&sig=s1')).toBe('/api/openrag/extract/a1?exp=1&sig=s1')
    expect(cheminSigne('/api/openrag/extract/a1?exp=1&sig=s1')).toBe('/api/openrag/extract/a1?exp=1&sig=s1')
    expect(cheminSigne('https://www.legifrance.gouv.fr/x')).toBe('https://www.legifrance.gouv.fr/x')
    expect(cheminSigne('pas une url')).toBe('')
    expect(cheminSigne(null)).toBe('')
  })

  it('sourcesPourPuces donne à la puce ce qu\'elle lit : libellé numéroté, titre, lien signé, page, texte', () => {
    const s = sourcesPourPuces([{ n: 2, titre: 'Article 2', snippet: 'Autre passage', url: 'https://mc.fake-domain.name/api/openrag/extract/b2?exp=1&sig=s2', page: 4 }])
    expect(s).toEqual([{ n: 2, libelle: '[2] Article 2', titre_document: 'Article 2', chunk_url: '/api/openrag/extract/b2?exp=1&sig=s2', page: 4, content: 'Autre passage' }])
    expect(sourcesPourPuces([{ n: 1, titre: 'T', snippet: 's', url: null, page: null }])[0]!.chunk_url).toBe('')
  })

  it('texteACopier : la réponse, puis les passages transmis', () => {
    const t = texteACopier('  Réponse [1].  ', [
      { n: 1, titre: 'Article 1', snippet: 's', url: 'https://mc.fake-domain.name/api/openrag/extract/a1?exp=1&sig=s1', page: 3 },
      { n: 2, titre: 'Article 2', snippet: 's', url: null, page: null },
    ])
    expect(t).toBe("Réponse [1].\n\nPassages transmis à l'agent :\n[1] Article 1 (p. 3) — https://mc.fake-domain.name/api/openrag/extract/a1?exp=1&sig=s1\n[2] Article 2")
    expect(texteACopier('r', [])).toBe('r')
  })
})

describe('normaliserErreurAgents (le sens des réponses de Mes agents)', () => {
  it('un jeton refusé, une audience qui n\'est pas la nôtre, un 403, un service injoignable : la fonction se masque', () => {
    expect(normaliserErreurAgents(401, { error: { code: 'invalid_token', message: 'x' } }).genre).toBe('masquer')
    expect(normaliserErreurAgents(403, { error: { code: 'audience_mismatch', message: 'x' } }).genre).toBe('masquer')
    expect(normaliserErreurAgents(403, { error: { code: 'forbidden', message: 'x' } }).genre).toBe('masquer')
    expect(normaliserErreurAgents('injoignable').genre).toBe('masquer')
  })

  it('422 : le message de la garde s\'affiche tel quel', () => {
    const e = normaliserErreurAgents(422, { error: { message: 'Cette demande contient une consigne cachée.', type: 'invalid_request_error', code: 'blocked_input' } })
    expect(e).toEqual({ genre: 'message', code: 'blocked_input', message: 'Cette demande contient une consigne cachée.' })
    expect(normaliserErreurAgents(422, { error: { code: 'blocked_output' } }).message).toBe("L'agent a refusé cette demande.")
  })

  it('404, 429, 502, délai : un message, pas un masquage', () => {
    expect(normaliserErreurAgents(404, { error: { code: 'model_not_found' } })).toMatchObject({ genre: 'message', message: "Cet agent n'est plus accessible." })
    expect(normaliserErreurAgents(429, null)).toMatchObject({ genre: 'message', message: 'Trop de demandes : réessayez dans un moment.' })
    expect(normaliserErreurAgents(502, { error: { code: 'llm_unavailable' } })).toMatchObject({ genre: 'message', message: "L'agent ne répond pas. Réessayez dans un moment." })
    expect(normaliserErreurAgents('delai').genre).toBe('message')
    expect(normaliserErreurAgents(500, 'pas du json')).toMatchObject({ genre: 'message', code: 'http_500' })
  })

  it('un message de 422 est borné et nettoyé, jamais du HTML', () => {
    const e = normaliserErreurAgents(422, { error: { code: 'blocked_input', message: '<b>x</b>'.repeat(1000) } })
    expect(e.message.length).toBe(2000)
  })
})

describe('messageErreurRecherche (notre recherche, avant l\'agent)', () => {
  it('parle le langage de la personne', () => {
    expect(messageErreurRecherche(503)).toContain('indisponible')
    expect(messageErreurRecherche(429)).toContain('Trop de recherches')
    expect(messageErreurRecherche(403, { error: { code: 'audience_mismatch', message: 'x' } })).toContain('session')
    expect(messageErreurRecherche(400, { error: { code: 'invalid_query', message: 'q dépasse 1000 caractères' } })).toBe('q dépasse 1000 caractères')
    expect(messageErreurRecherche('injoignable')).toContain('ne répond pas')
    expect(messageErreurRecherche('delai')).toContain('délai')
    expect(messageErreurRecherche(500)).toContain('500')
  })
})
