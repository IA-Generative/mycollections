import { describe, it, expect } from 'vitest'
import { decouperMorceau, lireExtrait, nomDeFichier, pageAutonome } from '../../utils/extrait'

describe('lireExtrait', () => {
  it('lit le contenu à plat', () => {
    const r = lireExtrait({ page_content: '# Titre', original_filename: 'a.md', page: 1 })
    expect(r.contenu).toBe('# Titre')
    expect(r.meta.original_filename).toBe('a.md')
  })
  it('lit les métadonnées imbriquées', () => {
    const r = lireExtrait({ page_content: 'x', metadata: { partition: 'demo', page: 2 } })
    expect(r.meta.partition).toBe('demo')
    expect(r.meta.metadata).toBeUndefined()
  })
  it('tolère une réponse vide', () => {
    expect(lireExtrait(null)).toEqual({ contenu: '', meta: {} })
  })
})

describe('nomDeFichier', () => {
  it('retire accents, extension et ponctuation', () => {
    expect(nomDeFichier('Section — éloignement (OQTF).md', 'doc')).toBe('section-eloignement-oqtf.doc')
  })
  it('a un repli', () => {
    expect(nomDeFichier('', 'pdf')).toBe('extrait.pdf')
  })
})

describe('pageAutonome', () => {
  it('échappe le titre et les métadonnées, garde le corps assaini', () => {
    const html = pageAutonome({ titre: '<b>x</b>', meta: [['Page', '1']], contenu: '' }, '<p>ok</p>', true)
    expect(html).toContain('&lt;b&gt;x&lt;/b&gt;')
    expect(html).toContain('<p>ok</p>')
    expect(html).toContain('urn:schemas-microsoft-com:office:word')
  })
})

describe('decouperMorceau', () => {
  const relu = `[CONTEXT]

Ce document présente l'article R. 532-28-3 du CESEDA.

* filename: CESEDA-R532-28-3__LEGIARTI000043250462.md

[CHUNK_START]

Article R. 532-28-3 du CESEDA (partie 1/3).

Source : https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000043250462

[CHUNK_END]`

  it('sépare le résumé, le fichier et le texte', () => {
    const m = decouperMorceau(relu)
    expect(m.contexte).toBe("Ce document présente l'article R. 532-28-3 du CESEDA.")
    expect(m.fichier).toBe('CESEDA-R532-28-3__LEGIARTI000043250462.md')
    expect(m.corps.startsWith('Article R. 532-28-3')).toBe(true)
    expect(m.corps.endsWith('LEGIARTI000043250462')).toBe(true)
  })
  it('ne laisse aucune balise technique', () => {
    const m = decouperMorceau(relu)
    expect(m.corps + m.contexte).not.toMatch(/\[(CONTEXT|CHUNK_START|CHUNK_END)\]|filename/)
  })
  it('rend tel quel un texte sans balise', () => {
    expect(decouperMorceau('  # Titre\n\ntexte ')).toEqual({ contexte: '', fichier: '', corps: '# Titre\n\ntexte' })
  })
  it('tolère un morceau sans fin ni résumé', () => {
    const m = decouperMorceau('[CHUNK_START]\ntexte coupé')
    expect(m).toEqual({ contexte: '', fichier: '', corps: 'texte coupé' })
  })
  it('tolère le vide', () => {
    expect(decouperMorceau(null)).toEqual({ contexte: '', fichier: '', corps: '' })
  })
})
