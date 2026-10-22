import { describe, expect, it } from 'vitest'
import { CAPACITES_DEFAUT, normaliserCapacites } from '../../utils/capacites'
import { erreurResana, libelleTravail, preparation, resumeApercu, travailEnCours } from '../../utils/resana'
import { cartesDeSource, ligneBientot, SOURCES, sourcesSelon } from '../../utils/wizard'

describe('les erreurs du service Résana', () => {
  it('session absente : la phrase et le lien de connexion', () => {
    const e = erreurResana(new Error('API error 409: {"detail":{"code":"session_absente","message":"Connectez-vous à Résana.","reessayable":false,"url_connexion":"https://monassistant.fake-domain.name/resana"}}'))
    expect(e).toEqual({ message: 'Connectez-vous à Résana.', code: 'session_absente', urlConnexion: 'https://monassistant.fake-domain.name/resana', reessayable: false })
  })
  it('un lien qui n\'est pas en https n\'est pas proposé', () => {
    expect(erreurResana('API error 409: {"detail":{"code":"session_absente","message":"x","url_connexion":"javascript:alert(1)"}}').urlConnexion).toBeUndefined()
  })
  it('un détail en phrase, ou illisible', () => {
    expect(erreurResana('API error 404: {"detail":"Collection \'x\' not found"}').message).toBe('Collection \'x\' not found')
    expect(erreurResana('API error 502: <html>').reessayable).toBe(true)
    expect(erreurResana(new Error('Failed to fetch')).message).toContain('Résana')
  })
})

describe('l\'avancement', () => {
  it('en cours, terminé, à jour, échec, interrompu', () => {
    expect(libelleTravail({ etat: 'en_cours', action: 'import', total: 40, faits: 12 })).toBe('Import en cours : 12 sur 40 documents lus.')
    expect(libelleTravail({ etat: 'termine', action: 'synchronisation', ajoutes: 1, modifies: 2, retires: 0, ecartes: 1 }))
      .toBe('Synchronisation terminée : 1 ajouté, 2 modifiés, 0 retiré, 1 écarté. L\'indexation se poursuit en tâche de fond.')
    expect(libelleTravail({ etat: 'a_jour' })).toContain('Rien n\'a changé')
    expect(libelleTravail({ etat: 'echec', action: 'import', message: 'Résana ne répond pas.' })).toBe('Import arrêté : Résana ne répond pas.')
    expect(libelleTravail({ etat: 'interrompu', action: 'synchronisation' })).toContain('Relancez')
    expect(libelleTravail(null)).toBe('')
    expect(travailEnCours({ etat: 'en_cours' })).toBe(true)
    expect(travailEnCours({ etat: 'termine' })).toBe(false)
  })
  it('un grand dossier se prépare, un travail s\'arrête en route', () => {
    expect(libelleTravail({ etat: 'en_cours', phase: 'preparation', dossiers_lus: 12, dossiers: 40 }))
      .toBe('Résana prépare la liste du dossier : 12 dossiers lus sur 40. Un grand dossier peut demander plusieurs minutes.')
    expect(preparation(null, 40)).toBe('')
    expect(preparation(1, 3)).toBe(' : 1 dossier lu sur 3')
    expect(libelleTravail({ etat: 'partiel', action: 'import', ajoutes: 30, modifies: 0, message: 'Votre session a expiré.' }))
      .toBe('Import arrêté en route : Votre session a expiré. 30 documents reçus sont gardés ; synchronisez de nouveau pour continuer.')
    expect(travailEnCours({ etat: 'partiel' })).toBe(false)
  })
  it('l\'aperçu d\'un dossier', () => {
    expect(resumeApercu({ total: 40, taille_approx_mo: 119.6 })).toBe('40 documents, environ 120 Mo')
    expect(resumeApercu({ total: 1, taille_approx_mo: 0.2 })).toBe('1 document, moins de 1 Mo')
    expect(resumeApercu({ total: 3, taille_approx_mo: null })).toBe('3 documents')
  })
})

describe('la carte Résana suit la capacité', () => {
  it('éteinte (défaut) : annoncée « Bientôt », pas de carte', () => {
    const sources = sourcesSelon(CAPACITES_DEFAUT)
    expect(cartesDeSource(sources).map(s => s.cle)).not.toContain('resana')
    expect(ligneBientot(sources)).toContain('Résana')
  })
  it('allumée : une carte, retirée de « Bientôt »', () => {
    const sources = sourcesSelon(normaliserCapacites({ resana: true }))
    expect(cartesDeSource(sources).map(s => s.cle)).toEqual(['file', 'directory', 'resana'])
    expect(ligneBientot(sources)).not.toContain('Résana')
  })
  it('le drapeau ne touche que sa source', () => {
    expect(sourcesSelon(normaliserCapacites({ resana: true })).filter(s => s.cle !== 'resana')).toEqual(SOURCES.filter(s => s.cle !== 'resana'))
  })
})
