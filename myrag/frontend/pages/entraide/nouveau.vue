<script setup lang="ts">
import { ref } from 'vue'
import { messageErreur } from '~/utils/collectif'
import { LIBELLES_TYPE, TYPES_REDIGES } from '~/utils/entraide'

definePageMeta({ middleware: 'capacite', capacite: 'entraide' })
useHead({ title: 'Lancer un appel — Mes collections' })

const { creerAppel } = useEntraide()
const type = ref<string>('cherche')
const titre = ref('')
const texte = ref('')
const erreur = ref('')
const envoi = ref(false)

async function enregistrer () {
  erreur.value = ''
  envoi.value = true
  try {
    const { appel } = await creerAppel({ type: type.value, titre: titre.value, texte: texte.value })
    await navigateTo(`/entraide/${appel.id}`)
  }
  catch (e) {
    erreur.value = messageErreur(e)
  }
  finally {
    envoi.value = false
  }
}
</script>

<template>
  <div>
    <h1 class="fr-h2">
      Lancer un appel
    </h1>
    <p>
      Votre appel reste un brouillon, visible de vous seul·e, jusqu'à ce que vous le publiez.
      Une donnée vous manque ?
      <NuxtLink
        class="fr-link"
        to="/demandes?deposer=1"
      >
        Faites plutôt une demande
      </NuxtLink>.
    </p>
    <form
      class="fr-mb-4w"
      @submit.prevent="enregistrer"
    >
      <fieldset class="fr-fieldset">
        <legend class="fr-fieldset__legend">
          Que voulez-vous faire ?
        </legend>
        <div
          v-for="t in TYPES_REDIGES"
          :key="t"
          class="fr-fieldset__element"
        >
          <div class="fr-radio-group">
            <input
              :id="`nouveau-${t}`"
              v-model="type"
              type="radio"
              name="type"
              :value="t"
            >
            <label
              class="fr-label"
              :for="`nouveau-${t}`"
            >{{ LIBELLES_TYPE[t].libelle }}</label>
          </div>
        </div>
      </fieldset>
      <div class="fr-input-group">
        <label
          class="fr-label"
          for="appel-titre"
        >Titre de l'appel</label>
        <input
          id="appel-titre"
          v-model="titre"
          class="fr-input"
          type="text"
          maxlength="200"
          required
        >
      </div>
      <div class="fr-input-group">
        <label
          class="fr-label"
          for="appel-texte"
        >Pour en dire plus <span class="fr-hint-text">Facultatif</span></label>
        <textarea
          id="appel-texte"
          v-model="texte"
          class="fr-input"
          rows="6"
          maxlength="5000"
        />
      </div>
      <div
        v-if="erreur"
        class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"
        role="alert"
      >
        <p>{{ erreur }}</p>
      </div>
      <ul class="fr-btns-group fr-btns-group--inline-md">
        <li>
          <button
            class="fr-btn"
            type="submit"
            :disabled="envoi || !titre.trim()"
          >
            Enregistrer le brouillon
          </button>
        </li>
        <li>
          <NuxtLink
            class="fr-btn fr-btn--tertiary"
            to="/entraide"
          >
            Annuler
          </NuxtLink>
        </li>
      </ul>
    </form>
  </div>
</template>
