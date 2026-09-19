<template>
  <span ref="ancre" class="myrag-source-chip-wrap"
        @mouseenter="ouvrirApercu"
        @mouseleave="fermerApercuPlusTard"
        @focusin="ouvrirApercu"
        @focusout="fermerApercuPlusTard"
        @keydown.esc="fermerApercu">
    <a v-if="href"
       :href="href" target="_blank" rel="noopener"
       class="fr-tag fr-tag--sm myrag-source-chip"
       :aria-describedby="apercuVisible ? idApercu : undefined"
       @click="ouvrirLecteur($event, href, 'extrait')">
      <span class="fr-icon-file-line" aria-hidden="true" style="margin-right:0.3rem;"></span>
      {{ label }}<span v-if="page" class="myrag-source-chip__page">&nbsp;·&nbsp;p. {{ page }}</span>
    </a>
    <span v-else class="fr-tag fr-tag--sm" tabindex="0"
          :aria-describedby="apercuVisible ? idApercu : undefined">
      {{ label }}<span v-if="page">&nbsp;·&nbsp;p. {{ page }}</span>
    </span>

    <!-- Aperçu au survol : texte du morceau (déjà présent dans la réponse du chat) et
         liens. Il est posé sur la fenêtre, hors de la zone de messages qui défile et le
         rognerait. Le cadre transparent côté puce comble l'écart, et la fermeture est
         différée : la souris rejoint la bulle sans que l'aperçu disparaisse en chemin. -->
    <Teleport to="body">
      <span v-if="apercuVisible" :id="idApercu" role="tooltip"
            class="myrag-source-chip__popover"
            :class="{ 'myrag-source-chip__popover--dessous': place.dessous }"
            :style="place.style"
            @mouseenter="ouvrirApercu" @mouseleave="fermerApercuPlusTard">
        <span class="myrag-source-chip__popover-card">
          <span class="myrag-source-chip__popover-title">{{ titre || 'Extrait' }}</span>
          <span class="myrag-source-chip__popover-body">{{ previewText }}</span>
          <span class="myrag-source-chip__popover-hint">
            <a v-if="href" :href="href" target="_blank" rel="noopener"
               class="myrag-source-chip__popover-link myrag-source-chip__popover-link--plein"
               @click.stop="ouvrirLecteur($event, href, 'extrait')">
              <span class="fr-icon-article-line fr-icon--sm" aria-hidden="true"></span>
              Lire l'extrait
            </a>
            <a v-if="fullDocHref" :href="fullDocHref" target="_blank" rel="noopener"
               class="myrag-source-chip__popover-link"
               @click.stop="ouvrirLecteur($event, fullDocHref, 'document')">
              <span class="fr-icon-file-text-line fr-icon--sm" aria-hidden="true"></span>
              Document complet
            </a>
          </span>
        </span>
      </span>
    </Teleport>

    <PlaygroundSourceViewer :open="!!lecteur" :url="lecteur?.url || ''"
                            :titre="lecteur?.titre || titre || label"
                            :sous-titre="lecteur?.sousTitre"
                            :page="lecteur?.mode === 'extrait' ? page : undefined"
                            :contenu-initial="lecteur?.mode === 'extrait' ? source.content : ''"
                            @close="lecteur = null" />
  </span>
</template>

<script setup lang="ts">
import { prettyName, proxiedSourceUrl } from '~/utils/playground'
import { decouperMorceau } from '~/utils/extrait'

const props = defineProps<{
  source: {
    original_filename?: string
    filename?: string
    /** Libellé lisible posé par l'API (titre de la section du morceau) —
     *  « Homicides (unité : Victime) — département 04 » plutôt que le nom
     *  de fichier. Absent pour les collections ordinaires : repli prettyName. */
    libelle?: string
    titre_document?: string
    file_url?: string
    chunk_url?: string
    page?: number | string
    content?: string
  }
}>()

const showPreview = ref(false)
const ancre = ref<HTMLElement | null>(null)
const idApercu = `myrag-apercu-${useId()}`
const place = ref<{ dessous: boolean, style: Record<string, string> }>({ dessous: false, style: {} })
let minuterie: ReturnType<typeof setTimeout> | null = null

const LARGEUR = 420
const MARGE = 8
/** Place libre au-dessus de la puce en deçà de laquelle la bulle passe dessous. */
const HAUTEUR_MIN = 300

/** La bulle est fixée à la fenêtre : au-dessus de la puce (ancrée par son bas, donc
 *  sans avoir à mesurer sa hauteur), ou dessous quand la puce est trop près du haut. */
function placer() {
  const r = ancre.value?.getBoundingClientRect()
  if (!r) return
  const largeur = Math.min(LARGEUR, window.innerWidth - 2 * MARGE)
  const gauche = Math.max(MARGE, Math.min(r.left, window.innerWidth - largeur - MARGE))
  const dessous = r.top < HAUTEUR_MIN && window.innerHeight - r.bottom > r.top
  place.value = {
    dessous,
    style: {
      left: `${gauche}px`,
      width: `${largeur}px`,
      ...(dessous ? { top: `${r.bottom}px` } : { bottom: `${window.innerHeight - r.top}px` }),
    },
  }
}

function ouvrirApercu() {
  if (minuterie) { clearTimeout(minuterie); minuterie = null }
  if (showPreview.value) return
  placer()
  showPreview.value = true
}
function fermerApercu() {
  if (minuterie) { clearTimeout(minuterie); minuterie = null }
  showPreview.value = false
}
function fermerApercuPlusTard() {
  if (minuterie) clearTimeout(minuterie)
  minuterie = setTimeout(fermerApercu, 250)
}

/** Une bulle fixée à la fenêtre ne suit pas sa puce : au moindre défilement, on la ferme. */
watch(showPreview, (ouvert) => {
  if (ouvert) window.addEventListener('scroll', fermerApercu, { capture: true, passive: true })
  else window.removeEventListener('scroll', fermerApercu, { capture: true })
})
onBeforeUnmount(() => {
  fermerApercu()
  window.removeEventListener('scroll', fermerApercu, { capture: true })
})

/** Lecteur ouvert : un morceau, ou le document complet. Ctrl/Cmd-clic et clic du
 *  milieu gardent le comportement du lien (nouvel onglet). */
const lecteur = ref<{ url: string, mode: 'extrait' | 'document', titre: string, sousTitre?: string } | null>(null)
function ouvrirLecteur(ev: MouseEvent, url: string, mode: 'extrait' | 'document') {
  if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button !== 0) return
  ev.preventDefault()
  fermerApercu()
  lecteur.value = {
    url,
    mode,
    titre: titre.value || label.value,
    sousTitre: mode === 'extrait'
      ? (label.value !== titre.value ? label.value : undefined)
      : 'Document complet',
  }
}
const fullName = computed(() => props.source.original_filename || props.source.filename || '')
const label = computed(() => props.source.libelle || prettyName(fullName.value) || 'Source')
const titre = computed(() => props.source.titre_document || fullName.value)
const page = computed(() => props.source.page)
const href = computed(() => proxiedSourceUrl(props.source.chunk_url || props.source.file_url))
/** Separate link for the original document (file_url), shown in the popover
 *  so the user can open the full PDF/HTML/etc. when the chunk alone isn't
 *  enough context. Hidden if the source has no file_url distinct from the
 *  chunk link. */
const fullDocHref = computed(() => {
  const fu = props.source.file_url
  if (!fu) return ''
  const proxied = proxiedSourceUrl(fu)
  return proxied === href.value ? '' : proxied
})

/** L'aperçu reprend le texte du morceau déjà reçu avec la réponse, débarrassé de ses
 *  balises techniques ; 600 caractères suffisent à juger de la pertinence. */
const previewText = computed(() => {
  const raw = decouperMorceau(props.source.content).corps
  if (!raw) return ''
  return raw.length > 600 ? raw.substring(0, 600) + '…' : raw
})
const apercuVisible = computed(() => showPreview.value && !!previewText.value && !lecteur.value)
</script>

<style scoped>
.myrag-source-chip-wrap {
  position: relative;
  display: inline-block;
}
.myrag-source-chip {
  text-decoration: none;
  margin: 0 0.3rem 0.3rem 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.myrag-source-chip:hover { background: #eceae3; }
/* La puce ouvre la fenêtre de lecture : pas d'icône « lien externe ». */
.myrag-source-chip[target="_blank"]::after { content: none; }
.myrag-source-chip__page { color: #666; font-size: 0.85em; }

.myrag-source-chip__popover {
  position: fixed;
  z-index: 900;
  /* Pont transparent entre la bulle et la puce : la souris ne « sort » pas en chemin. */
  padding-bottom: 8px;
  box-sizing: border-box;
}
.myrag-source-chip__popover--dessous {
  padding-bottom: 0;
  padding-top: 8px;
}
.myrag-source-chip__popover-card {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  padding: 0.8rem 1rem 0.7rem;
  background: #fff;
  border: 1px solid #dddddd;
  border-top: 3px solid #000091;
  border-radius: 4px;
  box-shadow: 0 6px 18px rgba(0, 0, 18, 0.16);
  white-space: normal;
  font-size: 0.82rem;
  line-height: 1.5;
  color: #161616;
}
.myrag-source-chip__popover-title {
  font-weight: 700;
  font-size: 0.8rem;
  color: #161616;
  word-break: break-word;
}
.myrag-source-chip__popover-body {
  white-space: pre-line;
  word-break: break-word;
  color: #3a3a3a;
  max-height: 9em;
  overflow: hidden;
  mask-image: linear-gradient(to bottom, rgba(0,0,0,1) 65%, rgba(0,0,0,0) 100%);
  -webkit-mask-image: linear-gradient(to bottom, rgba(0,0,0,1) 65%, rgba(0,0,0,0) 100%);
}
.myrag-source-chip__popover-hint {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  align-items: center;
  padding-top: 0.5rem;
  border-top: 1px solid #eeeeee;
}
.myrag-source-chip__popover-link {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.78rem;
  font-weight: 500;
  color: #000091;
  background-image: none;
  text-decoration: none;
  padding: 0.3rem 0.7rem;
  border: 1px solid #000091;
  border-radius: 3px;
}
.myrag-source-chip__popover-link:hover { background-color: #f5f5fe; }
.myrag-source-chip__popover-link--plein { background-color: #000091; color: #fff; }
.myrag-source-chip__popover-link--plein:hover { background-color: #1212ff; }
.myrag-source-chip__popover-link[target="_blank"]::after { content: none; }
</style>
