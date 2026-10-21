/**
 * Les sites déclarés d'une collection ou d'un assistant : sur ces pages, l'extension du navigateur
 * propose la bulle « + IA ». Le serveur valide les motifs (règle des *match patterns*) ; ici, on
 * passe seulement du texte saisi (un motif par ligne) à la liste, et retour.
 */
import { messageErreur } from './collectif'

const FIN_DE_LIGNE = /\r?\n/
const REFUS_422 = /^API error 422: (.*)$/s

/** Un motif par ligne ; lignes vides et espaces autour ignorés ; doublons exacts retirés. */
export function lignesVersMotifs (texte: string): string[] {
  const vus: string[] = []
  for (const ligne of (texte || '').split(FIN_DE_LIGNE)) {
    const m = ligne.trim()
    if (m && !vus.includes(m)) {
      vus.push(m)
    }
  }
  return vus
}

export function motifsVersLignes (motifs: readonly string[]): string {
  return motifs.join('\n')
}

/**
 * Le message d'un refus : la raison d'un motif refusé (422 `{reason: 'motif', message}`),
 * sinon le message d'erreur commun.
 */
export function messageRefus (e: unknown): string {
  const brut = e instanceof Error ? e.message : String(e)
  const m = brut.match(REFUS_422)
  if (m) {
    try {
      const d = JSON.parse(m[1]!).detail
      if (d?.reason === 'motif' && typeof d.message === 'string') {
        return d.message
      }
    }
    catch {}
  }
  return messageErreur(e)
}
