<script setup lang="ts">
/**
 * Archiver, désarchiver, purger : les gestes de qui GÈRE une collection, sortis du catalogue
 * (refonte du 2026-10-19) pour vivre dans ses réglages. Mêmes routes, mêmes droits : l'API reste
 * seule juge ; le parent n'affiche ce bloc qu'à qui a `mes_droits.ecrire`.
 */
const props = defineProps<{
  /** Identifiant technique de la collection. */
  name: string
  /** Ce que lit une personne. */
  titre: string
  archivee: boolean
}>()
const emit = defineEmits<{ change: [], purgee: [] }>()

const { post, del } = useApi()
const erreur = ref('')
const enCours = ref(false)
const confirmationArchive = ref(false)
const purgeOuverte = ref(false)
const purgeSaisie = ref('')
const purgeErreur = ref('')
const btnPurger = ref<HTMLButtonElement | null>(null)

async function archiver () {
  enCours.value = true
  erreur.value = ''
  try {
    await post(`/api/collections/${props.name}/archive`)
    confirmationArchive.value = false
    emit('change')
  }
  catch (e: any) {
    erreur.value = messageErreur(e)
  }
  finally {
    enCours.value = false
  }
}

async function desarchiver () {
  enCours.value = true
  erreur.value = ''
  try {
    await post(`/api/collections/${props.name}/unarchive`)
    emit('change')
  }
  catch (e: any) {
    erreur.value = messageErreur(e)
  }
  finally {
    enCours.value = false
  }
}

function ouvrirPurge () {
  purgeSaisie.value = ''
  purgeErreur.value = ''
  purgeOuverte.value = true
  // Le focus entre dans la fenêtre : Échap et le piège du focus y agissent.
  nextTick(() => document.getElementById('purge-confirm')?.focus())
}

function fermerPurge () {
  purgeOuverte.value = false
  nextTick(() => btnPurger.value?.focus())
}

async function purger () {
  if (purgeSaisie.value !== props.name) {
    purgeErreur.value = 'L\'identifiant saisi ne correspond pas.'
    return
  }
  enCours.value = true
  purgeErreur.value = ''
  try {
    await del(`/api/collections/${props.name}`)
    purgeOuverte.value = false
    emit('purgee')
  }
  catch (e: any) {
    purgeErreur.value = messageErreur(e)
  }
  finally {
    enCours.value = false
  }
}
</script>

<template>
  <section
    class="zone-sensible fr-mt-6w"
    aria-labelledby="titre-zone-sensible"
  >
    <h2
      id="titre-zone-sensible"
      class="fr-h5"
    >
      Zone sensible
    </h2>
    <div
      v-if="erreur"
      class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"
      role="alert"
    >
      <p>{{ erreur }}</p>
    </div>

    <template v-if="!archivee">
      <p class="fr-text--sm">
        Archiver retire la collection du catalogue et de l'assistant. Ses documents sont gardés : vous pourrez la désarchiver.
      </p>
      <div
        v-if="confirmationArchive"
        class="fr-alert fr-alert--warning fr-alert--sm fr-mb-2w"
        role="alert"
      >
        <p>Archiver « {{ titre }} » ? Elle ne sera plus proposée à vos collègues.</p>
        <div class="fr-btns-group fr-btns-group--inline-sm fr-btns-group--sm fr-mt-1w">
          <button
            type="button"
            class="fr-btn fr-btn--sm"
            :disabled="enCours"
            @click="archiver"
          >
            Confirmer l'archivage
          </button>
          <button
            type="button"
            class="fr-btn fr-btn--sm fr-btn--secondary"
            @click="confirmationArchive = false"
          >
            Annuler
          </button>
        </div>
      </div>
      <button
        v-else
        type="button"
        class="fr-btn fr-btn--secondary fr-icon-inbox-archive-line fr-btn--icon-left"
        @click="confirmationArchive = true"
      >
        Archiver
      </button>
    </template>

    <template v-else>
      <p class="fr-text--sm">
        Cette collection est archivée. Vous pouvez la désarchiver, ou la purger définitivement.
      </p>
      <div class="fr-btns-group fr-btns-group--inline-sm">
        <button
          type="button"
          class="fr-btn fr-btn--secondary fr-icon-refresh-line fr-btn--icon-left"
          :disabled="enCours"
          @click="desarchiver"
        >
          Désarchiver
        </button>
        <button
          ref="btnPurger"
          type="button"
          class="fr-btn fr-btn--tertiary fr-icon-delete-line fr-btn--icon-left zone-sensible__purger"
          @click="ouvrirPurge"
        >
          Purger
        </button>
      </div>
    </template>

    <dialog
      v-if="purgeOuverte"
      open
      class="fr-modal fr-modal--opened"
      aria-labelledby="titre-purge"
      style="display:block;"
      @keydown="piegerLeFocus($event, $event.currentTarget as HTMLElement)"
      @keydown.esc="fermerPurge"
    >
      <div class="fr-container fr-container--fluid fr-container-md">
        <div class="fr-grid-row fr-grid-row--center">
          <div class="fr-col-12 fr-col-md-8 fr-col-lg-6">
            <div class="fr-modal__body">
              <div class="fr-modal__header">
                <button
                  type="button"
                  class="fr-btn--close fr-btn"
                  @click="fermerPurge"
                >
                  Fermer
                </button>
              </div>
              <div class="fr-modal__content">
                <h1
                  id="titre-purge"
                  class="fr-modal__title"
                >
                  <span
                    class="fr-icon-warning-fill"
                    aria-hidden="true"
                  />
                  Purger définitivement « {{ titre }} » ?
                </h1>
                <p>Cette action est <strong>irréversible</strong>. Elle supprime :</p>
                <ul>
                  <li>Tous les documents indexés</li>
                  <li>Les fichiers sources stockés sur disque</li>
                  <li>Toutes les données liées (partages, dépôts, avis, évaluations)</li>
                </ul>
                <div
                  class="fr-input-group"
                  :class="{ 'fr-input-group--error': purgeErreur }"
                >
                  <label
                    class="fr-label"
                    for="purge-confirm"
                  >
                    Pour confirmer, tapez l'identifiant de la collection : <strong>{{ name }}</strong>
                  </label>
                  <input
                    id="purge-confirm"
                    v-model="purgeSaisie"
                    class="fr-input"
                    type="text"
                    @keyup.enter="purger"
                  >
                  <p
                    v-if="purgeErreur"
                    class="fr-error-text"
                  >
                    {{ purgeErreur }}
                  </p>
                </div>
              </div>
              <div class="fr-modal__footer">
                <ul class="fr-btns-group fr-btns-group--right fr-btns-group--inline-reverse fr-btns-group--inline-lg">
                  <li>
                    <button
                      type="button"
                      class="fr-btn zone-sensible__confirmer"
                      :disabled="enCours"
                      @click="purger"
                    >
                      {{ enCours ? 'Purge en cours…' : 'Purger définitivement' }}
                    </button>
                  </li>
                  <li>
                    <button
                      type="button"
                      class="fr-btn fr-btn--secondary"
                      @click="fermerPurge"
                    >
                      Annuler
                    </button>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </dialog>
  </section>
</template>

<style scoped>
.zone-sensible { border-top: 1px solid var(--border-default-grey); padding-top: 1.5rem; }
.zone-sensible__purger { color: var(--text-default-error); }
.zone-sensible__confirmer { background-color: var(--background-flat-error); }
</style>
