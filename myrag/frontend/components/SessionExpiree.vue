<script setup lang="ts">
/**
 * « Votre session a expiré » : quand le SSO ne renouvelle plus le jeton, chaque appel échouerait.
 * La fenêtre le dit et propose de se reconnecter ; on revient ensuite sur la même page.
 * Elle bloque la page (pas de fermeture) : continuer sans session ne mènerait qu'à des erreurs.
 */
const { sessionExpiree, reconnecter } = useAuth()
const fenetre = ref<HTMLElement | null>(null)
const bouton = ref<HTMLButtonElement | null>(null)
const envoi = ref(false)

watch(sessionExpiree, (v) => {
  if (v) {
    nextTick(() => bouton.value?.focus())
  }
})

async function seReconnecter () {
  envoi.value = true
  await reconnecter()
  envoi.value = false
}
</script>

<template>
  <Teleport to="body">
    <dialog
      v-if="sessionExpiree"
      ref="fenetre"
      open
      class="fr-modal fr-modal--opened session-expiree"
      aria-labelledby="session-expiree-titre"
      aria-describedby="session-expiree-texte"
      aria-modal="true"
      role="alertdialog"
      @keydown="piegerLeFocus($event, fenetre)"
    >
      <div class="fr-container fr-container--fluid fr-container-md">
        <div class="fr-grid-row fr-grid-row--center">
          <div class="fr-col-12 fr-col-md-8 fr-col-lg-6">
            <div class="fr-modal__body">
              <div class="fr-modal__content fr-pt-4w">
                <h1
                  id="session-expiree-titre"
                  class="fr-modal__title"
                >
                  <span
                    class="fr-icon-lock-line fr-mr-1w"
                    aria-hidden="true"
                  />Votre session a expiré
                </h1>
                <p id="session-expiree-texte">
                  Pour votre sécurité, la connexion a pris fin. Reconnectez-vous pour continuer : vous reviendrez sur
                  cette page. Ce qui n'a pas été enregistré sur la page sera à refaire.
                </p>
                <p class="fr-text--sm session-expiree__discret">
                  Un import Résana déjà lancé n'est pas perdu : s'il a dû s'arrêter, « Mettre à jour » le reprendra.
                </p>
              </div>
              <div class="fr-modal__footer">
                <ul class="fr-btns-group fr-btns-group--right fr-btns-group--inline-md">
                  <li>
                    <button
                      ref="bouton"
                      type="button"
                      class="fr-btn"
                      :disabled="envoi"
                      @click="seReconnecter"
                    >
                      {{ envoi ? 'Redirection…' : 'Se reconnecter' }}
                    </button>
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

<style scoped>
.session-expiree { display: block; z-index: 1000; background: rgb(22 22 22 / 64%); }
.session-expiree__discret { color: var(--text-mention-grey); }
</style>
