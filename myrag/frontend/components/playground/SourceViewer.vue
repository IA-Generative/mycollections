<template>
  <Teleport to="body">
    <dialog v-if="open" open class="fr-modal fr-modal--opened myrag-viewer"
            aria-labelledby="myrag-viewer-title" style="display:block;"
            @click.self="fermer" @keydown.esc="fermer">
      <div class="fr-container fr-container--fluid fr-container-md">
        <div class="fr-grid-row fr-grid-row--center">
          <div class="fr-col-12 fr-col-md-10 fr-col-lg-8">
            <div class="fr-modal__body myrag-viewer__body">
              <div class="fr-modal__header">
                <button ref="btnFermer" class="fr-btn--close fr-btn" title="Fermer" @click="fermer">
                  Fermer
                </button>
              </div>
              <div class="fr-modal__content">
                <h1 id="myrag-viewer-title" class="fr-modal__title">
                  <span class="fr-icon-file-text-line fr-mr-1w" aria-hidden="true"></span>{{ titre }}
                </h1>
                <p v-if="sousTitre" class="fr-text--sm fr-mb-1w myrag-viewer__sous-titre">{{ sousTitre }}</p>
                <p v-if="metaAffichee.length" class="fr-text--xs myrag-viewer__meta">
                  <template v-for="([k, v], i) in metaAffichee" :key="k">
                    <span v-if="i" aria-hidden="true"> · </span><strong>{{ k }}</strong> : {{ v }}
                  </template>
                </p>

                <p v-if="chargement || enChargement" class="fr-text--sm" aria-live="polite">Chargement…</p>
                <div v-else-if="fichierUrl" class="myrag-viewer__fichier">
                  <iframe v-if="estPdf" :src="fichierUrl" title="Document" class="myrag-viewer__pdf"></iframe>
                  <p v-else class="fr-text--sm">
                    Ce document n'est pas un texte affichable ici.
                    <a :href="fichierUrl" target="_blank" rel="noopener">Ouvrir le document</a>
                  </p>
                </div>
                <template v-else>
                  <div v-if="avertissement" class="fr-alert fr-alert--info fr-alert--sm fr-mb-2w">
                    <p>{{ avertissement }}</p>
                  </div>
                  <div ref="zoneTexte" class="myrag-md myrag-viewer__texte" v-html="corpsHtml"></div>
                  <aside v-if="contexteAffiche" class="myrag-viewer__contexte">
                    <p class="myrag-viewer__contexte-titre">À propos du document <span>— résumé automatique</span></p>
                    <p class="myrag-viewer__contexte-texte">{{ contexteAffiche }}</p>
                  </aside>
                </template>
              </div>
              <div class="fr-modal__footer">
                <ul class="fr-btns-group fr-btns-group--right fr-btns-group--inline-lg fr-btns-group--icon-left">
                  <li v-if="!fichierUrl">
                    <button class="fr-btn fr-icon-download-line" :disabled="!morceau.corps" @click="exporterWord">
                      Télécharger en Word
                    </button>
                  </li>
                  <li v-if="!fichierUrl">
                    <button class="fr-btn fr-btn--secondary fr-icon-printer-line" :disabled="!morceau.corps"
                            title="Ouvre l'impression : choisir « Enregistrer au format PDF »"
                            @click="exporterPdf">
                      Télécharger en PDF
                    </button>
                  </li>
                  <li v-if="fichierUrl">
                    <a class="fr-btn fr-icon-download-line" :href="fichierUrl" :download="nomFichierBrut">
                      Télécharger le document
                    </a>
                  </li>
                  <li v-if="lienOnglet">
                    <a class="fr-btn fr-btn--tertiary" :href="lienOnglet"
                       target="_blank" rel="noopener">
                      {{ url ? 'Ouvrir dans un onglet' : 'Voir la source d’origine' }}
                    </a>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </dialog>
  </Teleport>
</template>

<script setup lang="ts">
import { renderMarkdownSafe } from '~/utils/sanitize'
import { decouperMorceau, lireExtrait, nomDeFichier, pageAutonome } from '~/utils/extrait'

/**
 * Fenêtre de lecture d'une source : un morceau (`/api/openrag/extract/<id>`) ou le
 * document complet (`/api/openrag/static/<fichier>`). Le texte est relu en brut
 * (`?raw=1`), débarrassé de ses balises techniques (`[CHUNK_START]`…) et rendu en
 * Markdown ; un PDF ou une image s'affiche tel quel.
 * Si la relecture échoue, on montre le texte déjà reçu avec la réponse du chat.
 */
const props = defineProps<{
  open: boolean
  url: string
  titre: string
  sousTitre?: string
  page?: number | string
  /** Texte du morceau déjà présent dans la réponse du chat — repli si la relecture échoue.
   *  Sans `url`, c'est LE texte à montrer : l'appelant l'a déjà relu (un document entier). */
  contenuInitial?: string
  /** Résumé du document, quand l'appelant le connaît déjà (sinon lu dans les balises du morceau). */
  contexte?: string
  /** L'appelant est encore en train de relire le texte. */
  enChargement?: boolean
  /** Message à afficher au-dessus du texte (lecture partielle, document tronqué…). */
  avis?: string
  /** Adresse d'origine du document (Légifrance…) : remplace « Ouvrir dans un onglet » quand il n'y a pas d'`url`. */
  lienSource?: string
}>()
const emit = defineEmits<{ (e: 'close'): void }>()

const config = useRuntimeConfig()
const chargement = ref(false)
const contenu = ref('')
const meta = ref<Record<string, any>>({})
const avertissement = ref('')
const fichierUrl = ref('')
const estPdf = ref(false)
const btnFermer = ref<HTMLButtonElement | null>(null)

const zoneTexte = ref<HTMLElement | null>(null)

const morceau = computed(() => decouperMorceau(contenu.value))
const contexteAffiche = computed(() => props.contexte || morceau.value.contexte)
const lienOnglet = computed(() => props.url || props.lienSource || '')
const corpsHtml = computed(() => renderMarkdownSafe(morceau.value.corps) || '<p><em>(extrait vide)</em></p>')
const nomFichierBrut = computed(() => props.titre || 'document')

const metaAffichee = computed<Array<[string, string]>>(() => {
  const out: Array<[string, string]> = []
  const fichier = meta.value.original_filename || meta.value.filename || morceau.value.fichier
  if (fichier && fichier !== props.titre) out.push(['Fichier', String(fichier)])
  const page = meta.value.page ?? props.page
  if (page !== undefined && page !== null && page !== '') out.push(['Page', String(page)])
  if (meta.value.partition) out.push(['Collection', String(meta.value.partition)])
  return out
})

function urlAbsolue(u: string): string {
  const base = config.public.myragApiUrl || ''
  const complete = u.startsWith('/api/') ? `${base}${u}` : u
  return complete + (complete.includes('?') ? '&' : '?') + 'raw=1'
}

function libererFichier() {
  if (fichierUrl.value) URL.revokeObjectURL(fichierUrl.value)
  fichierUrl.value = ''
  estPdf.value = false
}

async function charger() {
  libererFichier()
  contenu.value = props.contenuInitial || ''
  meta.value = {}
  avertissement.value = props.avis || ''
  if (!props.url) return
  chargement.value = true
  try {
    const resp = await fetch(urlAbsolue(props.url), { credentials: 'same-origin' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const type = resp.headers.get('content-type') || ''
    if (type.includes('json')) {
      const lu = lireExtrait(await resp.json())
      if (lu.contenu) contenu.value = lu.contenu
      meta.value = lu.meta
    } else if (type.startsWith('text/') && !type.includes('html')) {
      contenu.value = await resp.text()
    } else {
      estPdf.value = type.includes('pdf')
      fichierUrl.value = URL.createObjectURL(await resp.blob())
    }
  } catch {
    avertissement.value = contenu.value
      ? "Le texte complet n'a pas pu être relu : voici l'extrait reçu avec la réponse."
      : "L'extrait n'a pas pu être chargé. Essayez « Ouvrir dans un onglet »."
  } finally {
    chargement.value = false
  }
}

function extraitCourant() {
  return {
    titre: props.titre,
    sousTitre: props.sousTitre,
    meta: metaAffichee.value,
    contenu: morceau.value.corps,
  }
}

/** Un lien du texte (« Source : https://… ») ne doit pas faire quitter la page. */
watch([corpsHtml, zoneTexte], () => nextTick(() => {
  zoneTexte.value?.querySelectorAll('a[href]').forEach((a) => {
    a.setAttribute('target', '_blank')
    a.setAttribute('rel', 'noopener noreferrer')
  })
}), { flush: 'post' })

function exporterWord() {
  const html = pageAutonome(extraitCourant(), corpsHtml.value, true)
  // Le BOM fait lire l'UTF-8 à Word sans passer par la déclaration meta.
  const blob = new Blob(['﻿', html], { type: 'application/msword' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = nomDeFichier(props.titre, 'doc')
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

function exporterPdf() {
  // Cadre invisible plutôt que nouvelle fenêtre : pas de bloqueur de fenêtres
  // surgissantes, et l'impression ne porte que sur l'extrait mis en page.
  const cadre = document.createElement('iframe')
  cadre.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;'
  cadre.srcdoc = pageAutonome(extraitCourant(), corpsHtml.value)
  cadre.onload = () => {
    const w = cadre.contentWindow
    if (!w) return
    w.document.title = nomDeFichier(props.titre, 'pdf').replace(/\.pdf$/, '')
    w.focus()
    w.print()
    setTimeout(() => cadre.remove(), 60_000)
  }
  document.body.appendChild(cadre)
}

function fermer() {
  emit('close')
}

watch(() => [props.contenuInitial, props.avis], () => {
  if (props.open && !props.url) { contenu.value = props.contenuInitial || ''; avertissement.value = props.avis || '' }
})

watch(() => props.open, (o) => {
  if (o) {
    charger()
    nextTick(() => btnFermer.value?.focus())
  } else {
    libererFichier()
  }
}, { immediate: true })

onBeforeUnmount(libererFichier)
</script>

<style scoped>
.myrag-viewer { background: rgba(22, 22, 22, 0.64); z-index: 1000; }
.myrag-viewer__body { max-height: 90vh; }
.myrag-viewer__sous-titre { color: #3a3a3a; }
.myrag-viewer__meta { color: #666; border-bottom: 1px solid #ddd; padding-bottom: 0.6rem; }
.myrag-viewer__texte { font-size: 0.95rem; line-height: 1.6; word-break: break-word; }
.myrag-viewer__contexte { margin-top: 1.5rem; padding: 0.7rem 1rem; background: #f6f6f6; border-left: 3px solid #cecece; }
.myrag-viewer__contexte-titre { margin: 0 0 0.25rem; font-size: 0.78rem; font-weight: 700; color: #3a3a3a; }
.myrag-viewer__contexte-titre span { font-weight: 400; color: #666; }
.myrag-viewer__contexte-texte { margin: 0; font-size: 0.85rem; line-height: 1.5; color: #3a3a3a; }
.myrag-viewer__texte :deep(h1),
.myrag-viewer__texte :deep(h2),
.myrag-viewer__texte :deep(h3) { font-size: 1.1rem; margin: 1rem 0 0.4rem; }
.myrag-viewer__texte :deep(ul),
.myrag-viewer__texte :deep(ol) { padding-left: 1.4rem; }
.myrag-viewer__texte :deep(table) { border-collapse: collapse; font-size: 0.85rem; }
.myrag-viewer__texte :deep(th),
.myrag-viewer__texte :deep(td) { border: 1px solid #ddd; padding: 0.25rem 0.5rem; }
.myrag-viewer__pdf { width: 100%; height: 65vh; border: 1px solid #ddd; }
</style>
