import { describe, expect, it } from 'vitest'
import { annonceResultats, filtrerOptions, indexSuivant } from '../../utils/listeRiche'

const options = [
  { value: '1', label: 'Instances de gouvernance régionale', hint: 'Préfecture fictive de l\'Est' },
  { value: '2', label: 'Instances de gouvernance régionale', hint: 'Préfecture fictive de l\'Ouest' },
  { value: '3', label: 'Équipe projet' },
]

describe('la liste déroulante riche', () => {
  it('filtre sur le libellé et la précision, chaque mot, sans accents ni casse', () => {
    expect(filtrerOptions(options, 'equipe').map(o => o.value)).toEqual(['3'])
    expect(filtrerOptions(options, 'gouvernance OUEST').map(o => o.value)).toEqual(['2'])
    expect(filtrerOptions(options, '   ')).toHaveLength(3)
    expect(filtrerOptions(options, 'rien')).toEqual([])
  })
  it('les flèches bouclent', () => {
    expect(indexSuivant(-1, 3, 1)).toBe(0)
    expect(indexSuivant(-1, 3, -1)).toBe(2)
    expect(indexSuivant(2, 3, 1)).toBe(0)
    expect(indexSuivant(0, 3, -1)).toBe(2)
    expect(indexSuivant(0, 0, 1)).toBe(-1)
  })
  it('annonce le nombre de résultats', () => {
    expect(annonceResultats(0)).toBe('Aucun résultat.')
    expect(annonceResultats(1)).toBe('1 résultat, flèches haut et bas pour parcourir.')
  })
})
