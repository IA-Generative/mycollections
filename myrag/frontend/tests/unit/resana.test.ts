import { describe, expect, it } from 'vitest'
import { CAPACITES_DEFAUT, normaliserCapacites } from '../../utils/capacites'
import { arbreDossiers, avisDeReponse, basculerDossier, codeEcart, descriptionParDefaut, dossiersVisibles, erreurResana, estCollectionResana, etiquetteResana, extensionsDe, filtrerEspaces, grouperEcartes, inclusParUnParent, libelleTravail, partageResanaPret, phraseCouverture, phrasesQualite, preparation, resumeApercu, titreDepuisEspace, titrePageDocuments, travailEnCours } from '../../utils/resana'
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
      .toBe('Synchronisation terminée : 1 ajouté, 2 modifiés, 0 retiré, 1 écarté.')
    expect(libelleTravail({ etat: 'termine', action: 'import', ajoutes: 3, en_erreur: 2 }))
      .toBe('Import terminé : 3 ajoutés, 0 modifié, 0 retiré. 2 documents n\'ont pas pu être lus par le moteur de recherche.')
    expect(libelleTravail({ etat: 'en_cours', phase: 'indexation', total: 40, faits: 4 }))
      .toBe('Indexation en cours : 4 sur 40 documents confiés au moteur de recherche, quelques-uns à la fois.')
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

describe('la couverture', () => {
  it('étiquette et phrase', () => {
    expect(etiquetteResana({ couverture: 'totale' })).toBe('Résana · index complet')
    expect(etiquetteResana({ couverture: 'partielle' })).toBe('Résana · index partiel')
    expect(etiquetteResana(null)).toBe('')
    expect(phraseCouverture({ couverture: 'partielle', raisons: ['selection'], documents_indexes: 412, documents_disponibles: 2141 }))
      .toBe('412 documents indexés sur 2141 dans les dossiers choisis : index partiel (certains sous-dossiers sont exclus).')
    expect(phraseCouverture({ couverture: 'totale', documents_indexes: 1 })).toBe('1 document indexé : index complet.')
  })
  it('les avis d\'une réponse : seulement des liens internes', () => {
    const bon = { collection: 'c', code: 'resana_ancien', message: 'L\'index semble ancien.', action: { libelle: 'Mettre à jour', url: '/c/c/upload?synchroniser=1' } }
    expect(avisDeReponse([bon, { ...bon, action: { libelle: 'x', url: 'https://ailleurs.fake-domain.name' } }, { ...bon, action: { libelle: 'x', url: '//ailleurs' } }, null])).toEqual([bon])
    expect(avisDeReponse(undefined)).toEqual([])
  })
})

describe('choisir l\'espace et les dossiers', () => {
  const espaces = [
    { id: '1', nom: 'Instances de gouvernance régionale', objet: 'Préfecture fictive de l\'Ouest' },
    { id: '2', nom: 'Équipe projet', description: 'Fictif' },
  ]
  it('la recherche d\'un espace ignore les accents et lit l\'objet', () => {
    expect(filtrerEspaces(espaces, 'equipe').map(e => e.id)).toEqual(['2'])
    expect(filtrerEspaces(espaces, 'PRÉFECTURE').map(e => e.id)).toEqual(['1'])
    expect(filtrerEspaces(espaces, '  ')).toHaveLength(2)
  })
  const dossiers = [
    { id: 'r', titre: 'CAR', parent_id: null, chemin: 'CAR' },
    { id: 'a', titre: 'Comptes rendus', parent_id: 'r', chemin: 'CAR / Comptes rendus' },
    { id: 'a1', titre: '2026', parent_id: 'a', chemin: 'CAR / Comptes rendus / 2026' },
    { id: 'b', titre: 'Archives', parent_id: null, chemin: 'Archives' },
  ]
  it('l\'arbre : racines et enfants triés', () => {
    const { racines, enfants } = arbreDossiers(dossiers)
    expect(racines.map(d => d.id)).toEqual(['b', 'r'])
    expect(enfants.get('r')!.map(d => d.id)).toEqual(['a'])
  })
  it('cocher un dossier inclut son contenu ; la liste reste la plus courte', () => {
    let choisis = basculerDossier('a1', new Set(), dossiers)
    choisis = basculerDossier('r', choisis, dossiers)
    expect([...choisis]).toEqual(['r'])
    expect(inclusParUnParent('a1', choisis, dossiers)).toBe(true)
    expect(inclusParUnParent('b', choisis, dossiers)).toBe(false)
    expect([...basculerDossier('r', choisis, dossiers)]).toEqual([])
  })
  it('la recherche d\'un dossier garde ses ancêtres pour le contexte', () => {
    expect([...dossiersVisibles(dossiers, '2026')!].sort()).toEqual(['a', 'a1', 'r'])
    expect(dossiersVisibles(dossiers, '')).toBeNull()
  })
  it('titre et description proposés', () => {
    expect(titreDepuisEspace({ id: '206', nom: 'Instances de gouvernance régionale' })).toBe('Instances de gouvernance régionale')
    expect(descriptionParDefaut({ id: '206', nom: 'Instances' }, 'Préfecture fictive')).toBe('Espace Résana « Instances » (n° 206), Préfecture fictive.')
    expect(descriptionParDefaut({ id: '206', nom: 'Instances' }, '')).toBe('Espace Résana « Instances » (n° 206).')
  })
})

describe('la page des documents d\'une collection Résana (#134)', () => {
  it('se gère par la sélection de dossiers : ni dépôt manuel ni découpage', () => {
    expect(estCollectionResana({ source_type: 'resana' })).toBe(true)
    expect(titrePageDocuments({ source_type: 'resana' })).toBe('Gérer les documents')
  })

  it('une autre collection garde le dépôt de fichiers', () => {
    for (const fiche of [{ source_type: null }, { source_type: 'drive' }, {}, null, undefined]) {
      expect(estCollectionResana(fiche)).toBe(false)
      expect(titrePageDocuments(fiche)).toBe('Ajouter des documents')
    }
  })
})

describe('ouvrir une collection Résana à un groupe', () => {
  it('demande un groupe et la confirmation des droits Résana', () => {
    expect(partageResanaPret(['/g/equipe'], true)).toBe(true)
    expect(partageResanaPret(['/g/equipe-a', '/g/equipe-b'], true)).toBe(true)
    expect(partageResanaPret(['/g/equipe'], false)).toBe(false)
    expect(partageResanaPret([], true)).toBe(false)
  })
})

describe('ce que vaut l\'index (#144)', () => {
  it('ne dit rien quand tout est complet', () => {
    expect(phrasesQualite(null)).toEqual([])
    expect(phrasesQualite({ par_etat: { complet: 12 }, a_reprendre: 0 })).toEqual([])
  })

  it('dit les scans, avec le conseil de la version électronique, puis les contextes manquants', () => {
    const p = phrasesQualite({ par_etat: { complet: 10, sans_texte: 3, sans_contexte: 2 }, a_reprendre: 5, passages: 40, passages_sans_contexte: 6 })
    expect(p).toHaveLength(2)
    expect(p[0]).toMatch(/^3 documents n'ont aucun texte lisible/)
    expect(p[0]).toContain('de préférence non signée')
    expect(p[1]).toBe('2 documents sont indexés sans tout le contexte qui aide à les retrouver (6 passages sur 40).')
  })

  it('accorde au singulier', () => {
    expect(phrasesQualite({ par_etat: { echec: 1, inconnue: 1 }, a_reprendre: 0 })).toEqual([
      '1 document n\'a pas pu être lu (format ou fichier refusé).',
      '1 document a été indexé avant le suivi de la qualité : elle sera connue à sa prochaine lecture.',
    ])
  })

  it('dit les scans lus par OCR, même quand tout est complet', () => {
    expect(phrasesQualite({ par_etat: { complet: 5 }, a_reprendre: 0, scans: 2, scans_lus: 2 })).toEqual([
      '2 scans ont été lus par reconnaissance de caractères : le texte peut contenir des erreurs, vérifiez les passages importants dans le document d\'origine.',
    ])
  })

  it('nomme la ré-indexation', () => {
    expect(libelleTravail({ etat: 'termine', action: 'reindexation', ajoutes: 0, modifies: 2, retires: 0 })).toBe('Ré-indexation terminée : 0 ajouté, 2 modifiés, 0 retiré.')
  })
})

describe('les documents écartés', () => {
  it('retrouve le code d\'un écart noté avant le code, d\'après le texte', () => {
    expect(codeEcart({ raison: 'même contenu que « A »' })).toBe('doublon')
    expect(codeEcart({ raison: 'Résana vous refuse ce document.' })).toBe('hors_droits')
    expect(codeEcart({ raison: 'format non pris en charge' })).toBe('format')
    expect(codeEcart({ raison: 'Résana a renvoyé ce fichier vide : le téléchargement n\'a rien rapporté.' })).toBe('fichier_vide')
    expect(codeEcart({ raison: '???' })).toBe('autre')
    expect(codeEcart({ code: 'vide', raison: 'peu importe' })).toBe('vide')
  })

  it('regroupe par raison, dans l\'ordre des explications, et ne garde que les adresses https', () => {
    const groupes = grouperEcartes([
      { titre: 'C', raison: 'même contenu que « A »', code: 'doublon', url: 'https://resana.fake-domain.name/e/ged/c' },
      { titre: 'X', raison: 'Résana vous refuse ce document.', code: 'hors_droits', url: 'http://pas-sur.fake-domain.name/x' },
      { titre: 'D', raison: 'même contenu que « B »' },
    ])
    expect(groupes.map(g => g.code)).toEqual(['hors_droits', 'doublon'])
    expect(groupes[1]!.documents.map(d => d.titre)).toEqual(['C', 'D'])
    expect(groupes[0]!.documents[0]!.url).toBe('')
    expect(groupes[0]!.quoiFaire).toContain('Mettre à jour')
  })
})

describe('les formats des écartés', () => {
  it('dit quels formats sont écartés, sans doublon', () => {
    expect(extensionsDe([{ titre: 'a', raison: 'format non pris en charge (.ZIP)', extension: '.ZIP' }, { titre: 'b', raison: '', extension: '.msg' }, { titre: 'c', raison: '', extension: '.zip' }, { titre: 'd', raison: '' }])).toEqual(['.msg', '.zip'])
    expect(grouperEcartes([{ titre: 'a', raison: 'format non pris en charge (.zip)', extension: '.zip' }])[0]!.extensions).toEqual(['.zip'])
  })
})
