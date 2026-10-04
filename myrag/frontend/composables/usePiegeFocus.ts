/**
 * Garde le focus clavier dans une fenêtre modale tant qu'elle est ouverte (Tab et Maj+Tab
 * tournent à l'intérieur), comme le ferait le JavaScript du DSFR que l'application ne charge pas.
 * Diagnostic d'octobre 2026, P2 : le focus sortait des fenêtres et se perdait sous elles.
 */
const FOCALISABLES = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function piegerLeFocus(e: KeyboardEvent, conteneur: HTMLElement | null | undefined) {
  if (e.key !== 'Tab' || !conteneur) return
  const elements = Array.from(conteneur.querySelectorAll<HTMLElement>(FOCALISABLES)).filter(el => el.offsetParent !== null || el === document.activeElement)
  if (!elements.length) { e.preventDefault(); return }
  const premier = elements[0]
  const dernier = elements[elements.length - 1]
  const actif = document.activeElement as HTMLElement | null
  const dedans = !!actif && conteneur.contains(actif)
  if (e.shiftKey && (actif === premier || !dedans)) { e.preventDefault(); dernier.focus() }
  else if (!e.shiftKey && (actif === dernier || !dedans)) { e.preventDefault(); premier.focus() }
}
