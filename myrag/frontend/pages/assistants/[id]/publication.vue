<script setup lang="ts">
import type { Canal, FicheAssistant } from '~/utils/assistants'
import { CANAUX, ligneFenetre } from '~/utils/assistants'

/** Où l'assistant est servi, et ses versions (B1). Cocher un canal ne fait pas une version ;
 *  publier fige le brouillon en version, seulement s'il a changé. */
definePageMeta({ middleware: 'capacite', capacite: 'assistants' })
const id = useRoute().params.id as string
useHead({ title: `Publication — ${id} — Mes collections` })

const { archiver, enregistrer, publier, versions: lireVersions } = useAssistants()
const versions = ref<any[]>([])
const message = ref('')
const erreur = ref('')
const envoi = ref(false)
const copie = ref(false)
const base = ref('')
/** Archiver se confirme en deux temps : le premier bouton ouvre la confirmation, jamais l'inverse. */
const confirmerArchivage = ref(false)
const btnConfirmer = ref<HTMLButtonElement | null>(null)
function demanderArchivage () {
  confirmerArchivage.value = true
  nextTick(() => btnConfirmer.value?.focus())
}
async function archiverAssistant () {
  envoi.value = true
  erreur.value = ''
  try {
    await archiver(id)
    await navigateTo('/assistants')
  }
  catch (e) {
    erreur.value = messageErreur(e)
    confirmerArchivage.value = false
  }
  finally {
    envoi.value = false
  }
}

async function chargerVersions () {
  try {
    versions.value = await lireVersions(id)
  }
  catch {
    versions.value = []
  }
}
onMounted(() => {
  base.value = window.location.origin
  chargerVersions()
})

async function agir (action: () => Promise<unknown>, succes: string, recharger: () => Promise<void>) {
  envoi.value = true
  erreur.value = ''
  message.value = ''
  try {
    await action()
    message.value = succes
    await recharger()
    await chargerVersions()
  }
  catch (e) {
    erreur.value = messageErreur(e)
  }
  finally {
    envoi.value = false
  }
}
function basculer (fiche: FicheAssistant, canal: Canal) {
  fiche.publication[canal] = !fiche.publication[canal]
}
async function copier (texte: string) {
  try {
    await navigator.clipboard.writeText(texte)
    copie.value = true
    setTimeout(() => {
      copie.value = false
    }, 2000)
  }
  catch {}
}
const FUSEAU = /(?:Z|[+-]\d{2}:?\d{2})$/
const dateVersion = (iso: string) => iso ? new Date(FUSEAU.test(iso) ? iso : `${iso}Z`).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' }) : ''
</script>

<template>
  <AssistantsCadre
    :id="id"
    rubrique="Publication"
  >
    <template #default="{ donnees, recharger }">
      <div class="fr-grid-row fr-grid-row--gutters">
        <div class="fr-col-12 fr-col-lg-7">
          <fieldset
            class="fr-fieldset"
            aria-labelledby="titre-canaux"
          >
            <legend
              id="titre-canaux"
              class="fr-fieldset__legend"
            >
              Où vos collègues le trouvent
              <span class="fr-hint-text">Ces choix s'appliquent tout de suite, sans nouvelle version.</span>
            </legend>
            <div
              v-for="c in CANAUX"
              :key="c.cle"
              class="fr-fieldset__element"
            >
              <div class="fr-checkbox-group">
                <input
                  :id="`canal-${c.cle}`"
                  type="checkbox"
                  :checked="donnees.fiche.publication[c.cle]"
                  :disabled="!donnees.mes_droits.ecrire"
                  @change="basculer(donnees.fiche, c.cle)"
                >
                <label
                  class="fr-label"
                  :for="`canal-${c.cle}`"
                >{{ c.libelle }}
                  <span class="fr-hint-text">{{ c.aide }}</span>
                </label>
              </div>
            </div>
          </fieldset>
          <div
            v-if="donnees.fiche.publication.fenetre_js"
            class="fr-mb-3w"
          >
            <p class="fr-text--sm fr-mb-1v">
              Ligne à coller dans votre page :
            </p>
            <pre class="publication-ligne">{{ ligneFenetre(id, base) }}</pre>
            <button
              type="button"
              class="fr-btn fr-btn--tertiary fr-btn--sm fr-icon-clipboard-line fr-btn--icon-left"
              @click="copier(ligneFenetre(id, base))"
            >
              {{ copie ? 'Copiée' : 'Copier la ligne' }}
            </button>
          </div>
          <div
            v-if="message"
            class="fr-alert fr-alert--success fr-alert--sm fr-mb-2w"
            role="status"
          >
            <p>{{ message }}</p>
          </div>
          <div
            v-if="erreur"
            class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"
            role="alert"
          >
            <p>{{ erreur }}</p>
          </div>
          <ul
            v-if="donnees.mes_droits.ecrire"
            class="fr-btns-group fr-btns-group--inline-md fr-btns-group--icon-left"
          >
            <li>
              <button
                type="button"
                class="fr-btn fr-btn--secondary"
                :disabled="envoi"
                @click="agir(() => enregistrer(donnees.fiche), 'Canaux enregistrés.', recharger)"
              >
                Enregistrer les canaux
              </button>
            </li>
            <li>
              <button
                type="button"
                class="fr-btn fr-icon-send-plane-line fr-btn--icon-left"
                :disabled="envoi"
                @click="agir(() => publier(id), 'Publié : le brouillon est devenu une version.', recharger)"
              >
                Publier une version
              </button>
            </li>
          </ul>
          <section
            v-if="donnees.mes_droits.ecrire && !donnees.assistant.collection_name"
            class="publication-retrait fr-mt-4w"
            aria-labelledby="titre-retrait"
          >
            <h2
              id="titre-retrait"
              class="fr-h6 fr-mb-1v"
            >
              Retirer l'assistant
            </h2>
            <p class="fr-text--sm fr-mb-2w">
              Archiver le retire de la liste : il ne répond plus et l'extension ne le propose plus. Rien
              n'est effacé : ses versions et ses consignes sont conservées.
            </p>
            <button
              v-if="!confirmerArchivage"
              type="button"
              class="fr-btn fr-btn--tertiary fr-btn--sm"
              :disabled="envoi"
              @click="demanderArchivage"
            >
              Archiver l'assistant…
            </button>
            <ul
              v-else
              class="fr-btns-group fr-btns-group--inline-sm"
              @keydown.esc="confirmerArchivage = false"
            >
              <li>
                <button
                  ref="btnConfirmer"
                  type="button"
                  class="fr-btn fr-btn--sm"
                  :disabled="envoi"
                  @click="archiverAssistant"
                >
                  Confirmer l'archivage
                </button>
              </li>
              <li>
                <button
                  type="button"
                  class="fr-btn fr-btn--secondary fr-btn--sm"
                  @click="confirmerArchivage = false"
                >
                  Annuler
                </button>
              </li>
            </ul>
          </section>
          <SitesDeclares
            class="fr-mt-4w"
            :chemin="`/api/assistants/${encodeURIComponent(id)}/sites`"
            objet="cet assistant"
            :ecrire="donnees.mes_droits.ecrire"
          />
        </div>

        <div class="fr-col-12 fr-col-lg-5">
          <h2 class="fr-h6">
            Versions
          </h2>
          <p
            v-if="!versions.length"
            class="fr-text--sm publication-discret"
          >
            Aucune version publiée : l'assistant n'est encore qu'un brouillon.
          </p>
          <ol
            v-else
            class="publication-versions"
          >
            <li
              v-for="v in versions"
              :key="v.numero ?? v.version"
            >
              <strong>Version {{ v.numero ?? v.version }}</strong>
              <span class="fr-text--xs publication-discret"> · {{ dateVersion(v.publie_le || v.cree_le) }}</span>
            </li>
          </ol>
        </div>
      </div>
    </template>
  </AssistantsCadre>
</template>

<style scoped>
.publication-retrait { border-top: 1px solid var(--border-default-grey); padding-top: 1.5rem; }
.publication-ligne { margin: 0 0 .5rem; padding: .75rem; font-size: .8rem; white-space: pre-wrap; overflow-wrap: anywhere; background: var(--background-alt-grey); }
.publication-discret { color: var(--text-mention-grey); }
.publication-versions { margin: 0; padding-left: 1.25rem; }
</style>
