import { describe, expect, it } from 'vitest'
import { bilanImport, erreurImport, nomFichierFiche, refusFichierFiche, TAILLE_MAX_FICHE_YAML } from '../../utils/ficheYaml'

describe('refusFichierFiche', () => {
  it('un fichier .yaml ou .yml de taille raisonnable peut partir', () => {
    expect(refusFichierFiche({ name: 'sejour.yaml', size: 800 })).toBeNull()
    expect(refusFichierFiche({ name: 'SEJOUR.YML', size: TAILLE_MAX_FICHE_YAML })).toBeNull()
  })
  it('refuse une autre extension, un fichier vide ou trop gros', () => {
    expect(refusFichierFiche({ name: 'fiche.json', size: 10 })).toMatch(/\.yaml/)
    expect(refusFichierFiche({ name: 'fiche.yaml', size: 0 })).toMatch(/vide/)
    expect(refusFichierFiche({ name: 'fiche.yaml', size: TAILLE_MAX_FICHE_YAML + 1 })).toMatch(/64 Kio/)
  })
})

describe('erreurImport', () => {
  it('un fichier invalide : le message et une ligne par champ', () => {
    const corps = { detail: { message: 'Le fichier n\'est pas une fiche d\'assistant valide.', erreurs: [{ champ: 'seuil_fiable', message: 'doit être inférieur ou égal à 1.0' }, { champ: '', message: 'sans champ' }] } }
    expect(erreurImport(new Error(`API error 422: ${JSON.stringify(corps)}`))).toEqual({
      message: 'Le fichier n\'est pas une fiche d\'assistant valide.',
      erreurs: ['seuil_fiable : doit être inférieur ou égal à 1.0', 'sans champ'],
    })
  })
  it('un autre refus : le détail du serveur, sans liste', () => {
    const e = new Error('API error 400: {"detail":"Ce fichier décrit l\'assistant « autre », pas « abc »"}')
    expect(erreurImport(e)).toEqual({ message: 'Ce fichier décrit l\'assistant « autre », pas « abc »', erreurs: [] })
  })
  it('un service injoignable se dit en mots simples', () => {
    expect(erreurImport(new TypeError('Failed to fetch')).message).toMatch(/ne répond pas/)
  })
})

describe('bilanImport et nomFichierFiche', () => {
  it('le bilan rappelle de publier et montre le début de l\'empreinte', () => {
    expect(bilanImport({ empreinte: 'a'.repeat(64) })).toBe('Fichier importé dans le brouillon. Publiez pour en faire une version. Empreinte : aaaaaaaaaaaa…')
    expect(bilanImport({})).not.toMatch(/Empreinte/)
  })
  it('le fichier porte le nom de l\'assistant', () => {
    expect(nomFichierFiche('sejour-des-etrangers')).toBe('sejour-des-etrangers.yaml')
  })
})
