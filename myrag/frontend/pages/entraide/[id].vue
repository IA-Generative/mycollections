<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { messageErreur } from '~/utils/collectif'
import { compteReponses, libelleRoles, LIBELLES_ETAT_APPEL, LIBELLES_TYPE, sansRecommandation } from '~/utils/entraide'

definePageMeta({ middleware: 'capacite', capacite: 'entraide' })

const route = useRoute()
const id = computed(() => String(route.params.id))
const { lireAppel, recommandations: lireRecommandations, publierAppel, cloreAppel, repondre } = useEntraide()
const appel = ref<any | null>(null)
const chargement = ref(true)
const erreur = ref('')
const message = ref('')
const reponse = ref('')
const recommandations = ref<any | null>(null)

useHead({ title: computed(() => `${appel.value?.titre || 'Appel'} — Mes collections`) })

async function charger () {
  chargement.value = true
  try {
    appel.value = (await lireAppel(id.value)).appel
    // Avant de publier, le réseau montre ce qui existe déjà.
    recommandations.value = appel.value.est_mon_appel && appel.value.etat === 'brouillon' ? await lireRecommandations(id.value) : null
  }
  catch {
    appel.value = null
  }
  finally {
    chargement.value = false
  }
}
async function geste (action: () => Promise<any>, ok: string) {
  erreur.value = ''
  message.value = ''
  try {
    await action()
    message.value = ok
    await charger()
  }
  catch (e) {
    erreur.value = messageErreur(e)
  }
}
const publier = () => geste(() => publierAppel(id.value), 'Votre appel est publié : vos collègues peuvent y répondre.')
const clore = () => geste(() => cloreAppel(id.value), 'L\'appel est clos.')
async function envoyer () {
  await geste(() => repondre(id.value, reponse.value), 'Votre réponse est envoyée.')
  if (!erreur.value) {
    reponse.value = ''
  }
}
onMounted(charger)
</script>

<template>
  <div>
    <p>
      <NuxtLink
        class="fr-link fr-icon-arrow-left-line fr-link--icon-left"
        to="/entraide"
      >
        Tous les appels
      </NuxtLink>
    </p>
    <p v-if="chargement">
      Chargement…
    </p>
    <div
      v-else-if="!appel"
      class="fr-alert fr-alert--warning"
    >
      <p>Appel introuvable.</p>
    </div>
    <template v-else>
      <h1 class="fr-h2">
        {{ appel.titre }}
      </h1>
      <ul class="fr-badges-group fr-mb-2w">
        <li>
          <p class="fr-badge fr-badge--sm">
            {{ LIBELLES_TYPE[appel.type as keyof typeof LIBELLES_TYPE]?.libelle || appel.type }}
          </p>
        </li>
        <li>
          <p
            class="fr-badge fr-badge--sm"
            :class="LIBELLES_ETAT_APPEL[appel.etat]?.badge"
          >
            {{ LIBELLES_ETAT_APPEL[appel.etat]?.libelle || appel.etat }}
          </p>
        </li>
        <li>
          <p class="fr-badge fr-badge--sm fr-badge--no-icon">
            {{ compteReponses(appel) }}
          </p>
        </li>
      </ul>
      <p
        v-if="appel.texte"
        style="white-space: pre-line"
      >
        {{ appel.texte }}
      </p>

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

      <section
        v-if="appel.etat === 'brouillon' && !sansRecommandation(recommandations)"
        class="fr-callout fr-mb-3w"
        aria-labelledby="existe-titre"
      >
        <h2
          id="existe-titre"
          class="fr-callout__title fr-h5"
        >
          Ceci existe peut-être déjà
        </h2>
        <p class="fr-text--sm">
          Avant de publier, regardez si une de ces ressources répond à votre besoin.
        </p>
        <ul class="fr-raw-list">
          <li
            v-for="c in recommandations.collections"
            :key="`c-${c.id}`"
          >
            <NuxtLink
              class="fr-link"
              :to="c.vers"
            >
              Collection : {{ c.titre }}
            </NuxtLink>
          </li>
          <li
            v-for="a in recommandations.assistants"
            :key="`a-${a.id}`"
          >
            <NuxtLink
              class="fr-link"
              :to="a.vers"
            >
              Assistant : {{ a.titre }}
            </NuxtLink>
          </li>
          <li
            v-for="d in recommandations.demandes_voisines"
            :key="`d-${d.demande_id}`"
          >
            <NuxtLink
              class="fr-link"
              :to="d.vers"
            >
              Demande voisine : {{ d.titre }}
            </NuxtLink>
            <span class="fr-text--xs"> — déjà soutenue par : {{ libelleRoles(d.roles) }}</span>
          </li>
        </ul>
      </section>

      <ul
        v-if="appel.est_mon_appel && appel.etat !== 'clos'"
        class="fr-btns-group fr-btns-group--inline-md fr-btns-group--icon-left fr-mb-3w"
      >
        <li v-if="appel.etat === 'brouillon'">
          <button
            class="fr-btn fr-icon-send-plane-line fr-btn--icon-left"
            type="button"
            @click="publier"
          >
            Publier l'appel
          </button>
        </li>
        <li>
          <button
            class="fr-btn fr-btn--secondary fr-icon-close-line fr-btn--icon-left"
            type="button"
            @click="clore"
          >
            Clore l'appel
          </button>
        </li>
      </ul>

      <section
        v-if="appel.etat !== 'brouillon'"
        aria-labelledby="reponses-titre"
      >
        <h2
          id="reponses-titre"
          class="fr-h4"
        >
          Réponses
        </h2>
        <p
          v-if="!appel.reponses.length"
          class="fr-text--sm"
        >
          Personne n'a encore répondu.
        </p>
        <ul
          v-else
          class="fr-raw-list"
        >
          <li
            v-for="r in appel.reponses"
            :key="r.id"
            class="fr-callout fr-callout--sm fr-mb-2w"
          >
            <p class="fr-callout__text">
              {{ r.texte }}
            </p>
            <p class="fr-text--xs fr-mb-0">
              {{ r.de_moi ? 'Vous' : 'Un collègue' }}, le {{ new Date(r.cree_le).toLocaleDateString('fr-FR') }}
            </p>
          </li>
        </ul>

        <form
          v-if="appel.etat === 'publie'"
          class="fr-mt-3w"
          @submit.prevent="envoyer"
        >
          <div class="fr-input-group">
            <label
              class="fr-label"
              for="reponse-texte"
            >Votre réponse</label>
            <textarea
              id="reponse-texte"
              v-model="reponse"
              class="fr-input"
              rows="4"
              maxlength="5000"
            />
          </div>
          <button
            class="fr-btn"
            type="submit"
            :disabled="!reponse.trim()"
          >
            Répondre
          </button>
        </form>
      </section>
    </template>
  </div>
</template>
