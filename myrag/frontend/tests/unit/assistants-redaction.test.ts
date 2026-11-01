import type { PassageAssistant } from '../../utils/assistants'
import { describe, expect, it } from 'vitest'
import { lierCitations, numeroCitation, reponseAffichee, texteSansReponse } from '../../utils/assistants'

function passage (n: number, extra: Partial<PassageAssistant> = {}): PassageAssistant {
  return {
    source: 'methodes',
    etape: 1,
    rang: n,
    document: `doc-${n}`,
    titre: `Document ${n}`,
    texte: `Texte ${n}`,
    url: `https://mycollections.fake-domain.name/api/openrag/extract/m-${n}?exp=1&sig=abc`,
    ...extra,
  }
}
const PASSAGES = [passage(1), passage(2, { titre: 'Délibération "budget" <2024>' }), passage(3, { url: null })]

describe('lierCitations', () => {
  it('un renvoi [n] devient un lien vers le passage n, marqué data-citation', () => {
    const html = lierCitations('Voté en séance [1].', PASSAGES)
    expect(html).toBe('Voté en séance <a href="https://mycollections.fake-domain.name/api/openrag/extract/m-1?exp=1&amp;sig=abc" class="assistant-citation" data-citation="1" title="Document 1">[1]</a>.')
  })
  it('le titre et l\'adresse sont échappés ; un passage sans lien renvoie à « # »', () => {
    expect(lierCitations('[2]', PASSAGES)).toContain('title="Délibération &quot;budget&quot; &lt;2024&gt;"')
    expect(lierCitations('[3]', PASSAGES)).toContain('href="#"')
  })
  it('un renvoi sans passage reste du texte, un lien Markdown n\'est pas touché', () => {
    expect(lierCitations('Voir [9] et [0].', PASSAGES)).toBe('Voir [9] et [0].')
    expect(lierCitations('[1](https://fake-domain.name)', PASSAGES)).toBe('[1](https://fake-domain.name)')
  })
})

describe('reponseAffichee et texteSansReponse', () => {
  it('une réponse rédigée a ses renvois liés ; une réponse fiable est servie telle quelle', () => {
    expect(reponseAffichee({ reponse: ' Oui [1]. ', passages: PASSAGES, redaction: 'faite' })).toContain('data-citation="1"')
    expect(reponseAffichee({ reponse: 'Réponse vérifiée [1].', passages: [], redaction: null })).toBe('Réponse vérifiée [1].')
    expect(reponseAffichee({ reponse: null, passages: PASSAGES, redaction: 'indisponible' })).toBe('')
  })
  it('sans réponse : la rédaction en panne le dit, sinon les passages trouvés, ou rien', () => {
    expect(texteSansReponse({ passages: PASSAGES, redaction: 'indisponible' })).toBe('La réponse n\'a pas pu être rédigée pour le moment. Voici les 3 passages trouvés : ouvrez-les ci-dessous.')
    expect(texteSansReponse({ passages: [passage(1)], redaction: 'indisponible' })).toContain('Voici le 1 passage trouvé :')
    expect(texteSansReponse({ passages: PASSAGES })).toBe('L\'assistant a trouvé 3 passages, sans rédiger de réponse : ouvrez-les ci-dessous.')
    expect(texteSansReponse({ passages: [], redaction: 'aucun_passage' })).toBe('L\'assistant n\'a rien trouvé pour cette question.')
  })
})

describe('numeroCitation', () => {
  const cible = (valeur: string | null) => ({ closest: (s: string) => s === 'a[data-citation]' && valeur !== null ? { getAttribute: () => valeur } : null })
  it('le numéro du lien cliqué', () => {
    expect(numeroCitation({ target: cible('2'), button: 0 })).toBe(2)
  })
  it('null hors d\'un renvoi, pour un numéro invalide, ou un clic laissé au navigateur', () => {
    expect(numeroCitation({ target: cible(null) })).toBeNull()
    expect(numeroCitation({ target: cible('abc') })).toBeNull()
    expect(numeroCitation({ target: null })).toBeNull()
    expect(numeroCitation({ target: cible('2'), ctrlKey: true })).toBeNull()
    expect(numeroCitation({ target: cible('2'), metaKey: true })).toBeNull()
    expect(numeroCitation({ target: cible('2'), button: 1 })).toBeNull()
  })
})
