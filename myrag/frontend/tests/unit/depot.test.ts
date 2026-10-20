import { describe, expect, it } from 'vitest'
import { ACCEPT, bilan, etatAfficheDepuis, etatDepot, etatDuTravail, libelleEtatDepot, natureFichier, nomDepuisChemin, passages, trier } from '../../utils/depot'

describe('formats', () => {
  it('distingue texte et documents, refuse le reste', () => {
    expect(natureFichier('note.MD')).toBe('texte')
    expect(natureFichier('rapport.pdf')).toBe('document')
    expect(natureFichier('Dossier/compte-rendu.docx')).toBe('document')
    expect(natureFichier('programme.exe')).toBeNull()
    expect(natureFichier('sans-extension')).toBeNull()
  })
  it('annonce les mêmes extensions au sélecteur de fichiers', () => {
    expect(ACCEPT.split(',')).toEqual(expect.arrayContaining(['.md', '.pdf', '.docx', '.pptx']))
  })
})

describe('dossiers', () => {
  it('nomme un fichier par son chemin dans le dossier choisi', () => {
    expect(nomDepuisChemin('Notes du service/RH/mobilite.md')).toBe('RH--mobilite.md')
    expect(nomDepuisChemin('Notes du service/guide.pdf')).toBe('guide.pdf')
    expect(nomDepuisChemin('seul.md')).toBe('seul.md')
  })
  it('écarte, avec la raison, ce qui ne sera pas déposé', () => {
    const { retenus, ecartes } = trier([
      { nom: 'a.md', taille: 10, chemin: 'D/a.md' },
      { nom: 'a.md', taille: 10, chemin: 'D/RH/a.md' },
      { nom: '.DS_Store', taille: 10, chemin: 'D/.DS_Store' },
      { nom: 'cfg', taille: 10, chemin: 'D/.git/cfg' },
      { nom: 'b.exe', taille: 10, chemin: 'D/b.exe' },
      { nom: 'vide.pdf', taille: 0, chemin: 'D/vide.pdf' },
      { nom: 'c.pdf', taille: 10, chemin: 'D/c.pdf' },
    ])
    expect(retenus.map(r => [r.nomDepot, r.nature])).toEqual([['a.md', 'texte'], ['RH--a.md', 'texte'], ['c.pdf', 'document']])
    expect(ecartes.map(e => e.raison)).toEqual(['fichier caché', 'fichier caché', 'format non pris en charge', 'fichier vide'])
  })
  it('ne dépose pas deux fois le même nom', () => {
    const { retenus, ecartes } = trier([{ nom: 'a.md', taille: 1 }, { nom: 'a.md', taille: 1 }])
    expect(retenus.length).toBe(1)
    expect(ecartes[0].raison).toBe('en double')
  })
})

describe('suivi', () => {
  it('traduit l\'état du travail', () => {
    expect(etatDuTravail({ status: 'uploading' })).toBe('indexation')
    expect(etatDuTravail({ status: 'done' })).toBe('indexe')
    expect(etatDuTravail({ status: 'done_with_errors', failed_chunks: 1, total_chunks: 1 })).toBe('echec')
    expect(etatDuTravail({ status: 'done_with_errors', failed_chunks: 1, total_chunks: 9 })).toBe('indexe')
  })
  it('fait le bilan', () => {
    expect(bilan(['indexe', 'indexe', 'echec', 'attente', 'indexation'])).toBe('2 indexés, 1 en échec, 2 en cours')
  })
})

describe('etatDepot', () => {
  it.each([
    [null, 'attente', 'en attente'],
    [{ status: 'chunking' }, 'decoupage', 'découpage en cours'],
    [{ status: 'chunking_done' }, 'decoupage', 'découpage en cours'],
    [{ status: 'uploading', total_chunks: 4 }, 'decoupage', 'découpage en cours'],
    [{ status: 'done', total_chunks: 4 }, 'pret', 'prêt'],
    [{ status: 'done_with_errors', total_chunks: 4, failed_chunks: 1 }, 'pret', 'prêt'],
    [{ status: 'done_with_errors', total_chunks: 4, failed_chunks: 4 }, 'echec', 'en échec'],
    [{ status: 'interrupted' }, 'echec', 'en échec'],
  ])('%o → %s', (job, etat, libelle) => {
    expect(etatDepot(job as never)).toBe(etat)
    expect(libelleEtatDepot(etatDepot(job as never))).toBe(libelle)
  })
  it('chaque état de la zone de dépôt a son état affiché', () => {
    expect((['attente', 'envoi', 'indexation', 'indexe', 'echec'] as const).map(etatAfficheDepuis)).toEqual(['attente', 'decoupage', 'decoupage', 'pret', 'echec'])
  })
})

describe('passages', () => {
  it('affichés seulement quand ils sont connus', () => {
    expect(passages(312)).toBe('312 passages')
    expect(passages(1)).toBe('1 passage')
    expect(passages(0)).toBeNull()
    expect(passages(undefined)).toBeNull()
  })
})
