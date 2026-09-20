import { describe, it, expect } from 'vitest'
import { avertissementLecture, libellePlage, libelleType, texteDuDocument } from '../../utils/corpus'

describe('libelleType', () => {
  it('nomme les types courants', () => {
    expect(libelleType({ type: 'application/pdf', fichier: 'a.pdf' })).toBe('PDF')
    expect(libelleType({ type: 'text/markdown', fichier: '' })).toBe('Markdown')
  })
  it('se replie sur l’extension, puis sur le type brut, puis sur un tiret', () => {
    expect(libelleType({ type: '', fichier: 'note.odt' })).toBe('ODT')
    expect(libelleType({ type: 'application/x-inconnu', fichier: 'sans-extension' })).toBe('application/x-inconnu')
    expect(libelleType({ type: '', fichier: '' })).toBe('—')
  })
})

describe('texteDuDocument', () => {
  it('met les morceaux bout à bout', () => {
    expect(texteDuDocument({ morceaux: [{ id: '1', texte: ' a ', page: null }, { id: '2', texte: 'b', page: null }] })).toBe('a\n\nb')
  })
  it('pose un repère quand la page change, et seulement s’il y a plusieurs pages', () => {
    const t = texteDuDocument({ morceaux: [{ id: '1', texte: 'a', page: 1 }, { id: '2', texte: 'b', page: 1 }, { id: '3', texte: 'c', page: 2 }] })
    expect(t).toBe('*— page 1 —*\n\na\n\nb\n\n*— page 2 —*\n\nc')
    expect(texteDuDocument({ morceaux: [{ id: '1', texte: 'a', page: 1 }, { id: '2', texte: 'b', page: 1 }] })).toBe('a\n\nb')
  })
  it('tolère un document vide', () => {
    expect(texteDuDocument({ morceaux: [] })).toBe('')
  })
})

describe('avertissementLecture', () => {
  const m = [{ id: '1', texte: 'a', page: null }]
  it('ne dit rien quand tout a été lu', () => {
    expect(avertissementLecture({ morceaux: m, total_morceaux: 1, illisibles: 0, tronque: false })).toBe('')
  })
  it('dit ce qui manque', () => {
    expect(avertissementLecture({ morceaux: m, total_morceaux: 90, illisibles: 0, tronque: true })).toContain('1 premiers passages sur 90')
    expect(avertissementLecture({ morceaux: m, total_morceaux: 2, illisibles: 1, tronque: false })).toBe("1 passage n'a pas pu être relu.")
    expect(avertissementLecture({ morceaux: m, total_morceaux: 4, illisibles: 3, tronque: false })).toBe("3 passages n'ont pas pu être relus.")
    expect(avertissementLecture({ morceaux: [], total_morceaux: 3, illisibles: 3, tronque: false })).toContain("n'a pas pu être relu")
  })
})

describe('libellePlage', () => {
  it('écrit la plage en français', () => {
    expect(libellePlage({ total: 3585, page: 1, par_page: 50 }, 50)).toBe('1–50 sur 3 585')
    expect(libellePlage({ total: 3585, page: 72, par_page: 50 }, 35)).toBe('3 551–3 585 sur 3 585')
  })
  it('dit quand il n’y a rien', () => {
    expect(libellePlage({ total: 0, page: 1, par_page: 50 }, 0)).toBe('Aucun document')
  })
})
