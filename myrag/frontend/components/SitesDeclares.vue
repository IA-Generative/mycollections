<script setup lang="ts">
/**
 * Les sites où proposer la bulle « + IA » de MirAI Assistant pour navigateur, pour une collection ou un
 * assistant. Un motif par ligne ; le serveur valide et normalise (`docs/clients.md`).
 */
import { lignesVersMotifs, messageRefus, motifsVersLignes } from '~/utils/sites'

const props = defineProps<{
  /** `/api/collections/{name}/sites` ou `/api/assistants/{id}/sites`. */
  chemin: string
  /** « cette collection » ou « cet assistant ». */
  objet: string
  ecrire: boolean
}>()

const { get, put } = useApi()
const texte = ref('')
const max = ref(20)
const envoi = ref(false)
const message = ref('')
const erreur = ref('')
const champ = useId()
// La page d'installation de l'extension, servie par le device management (vide : pas de lien).
const installation = ref('')

async function charger () {
  try {
    const r = await get(props.chemin)
    texte.value = motifsVersLignes(r.motifs || [])
    max.value = r.max || 20
  }
  catch (e) {
    erreur.value = messageRefus(e)
  }
}

async function enregistrer () {
  envoi.value = true
  message.value = ''
  erreur.value = ''
  try {
    const r = await put(props.chemin, { motifs: lignesVersMotifs(texte.value) })
    texte.value = motifsVersLignes(r.motifs || [])
    message.value = r.motifs?.length ? 'Sites enregistrés.' : 'Aucun site : la bulle ne sera proposée nulle part.'
  }
  catch (e) {
    erreur.value = messageRefus(e)
  }
  finally {
    envoi.value = false
  }
}

onMounted(async () => {
  charger()
  try {
    installation.value = (await get('/api/config')).navigateur_installation_url || ''
  }
  catch { /* sans adresse, pas de lien */ }
})
</script>

<template>
  <section
    class="sites"
    :aria-labelledby="`${champ}-titre`"
  >
    <h2
      :id="`${champ}-titre`"
      class="fr-h6 fr-mb-1v"
    >
      Dans le navigateur
    </h2>
    <p class="fr-text--sm fr-mb-2w">
      Sur les pages qui correspondent à ces adresses, MirAI Assistant pour navigateur propose une bulle
      « + IA » qui interroge {{ objet }}. Il compare lui-même l'adresse de la page :
      aucune page visitée n'est envoyée au service.
    </p>
    <p
      v-if="installation"
      class="fr-text--sm fr-mb-2w"
    >
      Pas encore installé ?
      <a
        :href="installation"
        class="fr-link fr-text--sm"
        target="_blank"
        rel="noopener"
      >Installer MirAI Assistant pour navigateur<span class="fr-sr-only"> (nouvelle fenêtre)</span></a>
    </p>
    <div class="fr-input-group">
      <label
        class="fr-label"
        :for="champ"
      >Adresses, une par ligne
        <span class="fr-hint-text">Par exemple https://www.fake-domain.name/guides/* ou https://*.fake-domain.name/* ; {{ max }} au plus, https seulement.</span>
      </label>
      <textarea
        :id="champ"
        v-model="texte"
        class="fr-input sites__champ"
        rows="4"
        spellcheck="false"
        :disabled="!ecrire || envoi"
      />
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
    <button
      v-if="ecrire"
      type="button"
      class="fr-btn fr-btn--secondary"
      :disabled="envoi"
      @click="enregistrer"
    >
      {{ envoi ? 'Enregistrement…' : 'Enregistrer les sites' }}
    </button>
  </section>
</template>

<style scoped>
.sites__champ { font-family: ui-monospace, Menlo, monospace; font-size: .875rem; }
</style>
