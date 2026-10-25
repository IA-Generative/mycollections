import { describe, expect, it } from 'vitest'
import { compatible, couleurPlafond, estCollectionFichiers, libelleInstance, niveauxPermis, rang, sourceImportee } from '../../utils/fichiers'
import { titrePageDocuments } from '../../utils/resana'

describe('le plafond de sensibilité', () => {
  it('l\'échelle va du moins au plus protégé', () => {
    expect(rang('public')).toBe(0)
    expect(rang('restricted')).toBe(5)
    expect(compatible('public', 'internal')).toBe(true)
    expect(compatible('personal', 'internal')).toBe(false)
  })
  it('un niveau inconnu se range au plus protecteur', () => {
    expect(rang('inconnu')).toBe(rang('restricted'))
  })
  it('une collection peut prendre le plafond de son instance, ou plus haut', () => {
    expect(niveauxPermis('internal').map(n => n.valeur)).toEqual(['internal', 'personal', 'personal_sensitive', 'controlled', 'restricted'])
    expect(niveauxPermis('restricted').map(n => n.libelle)).toEqual(['Diffusion restreinte'])
  })
  it('la couleur du plafond monte avec le niveau', () => {
    expect(couleurPlafond('public')).toBe('fr-badge--success')
    expect(couleurPlafond('internal')).toBe('fr-badge--info')
    expect(couleurPlafond('personal')).toBe('fr-badge--warning')
    expect(couleurPlafond('restricted')).toBe('fr-badge--error')
  })
})

describe('les collections importées', () => {
  it('reconnaît Fichiers et Résana, pas les autres', () => {
    expect(estCollectionFichiers({ source_type: 'fichiers' })).toBe(true)
    expect(sourceImportee({ source_type: 'fichiers' })).toBe('fichiers')
    expect(sourceImportee({ source_type: 'resana' })).toBe('resana')
    for (const f of [{ source_type: 'drive' }, { source_type: null }, null, undefined]) {
      expect(sourceImportee(f)).toBeNull()
    }
  })
  it('une collection Fichiers se gère par ses dossiers', () => {
    expect(titrePageDocuments({ source_type: 'fichiers' })).toBe('Gérer les documents')
  })
  it('une instance se reconnaît à son nom et à sa zone', () => {
    expect(libelleInstance({ titre: 'Mes fichiers (bêta)', zone: 'internet, bêta', hote: 'x' })).toBe('Mes fichiers (bêta) · internet, bêta')
    expect(libelleInstance({ titre: 'Fichiers', zone: '', hote: 'fichiers.fake-domain.name' })).toBe('Fichiers · fichiers.fake-domain.name')
  })
})
