<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous êtes ici">
      <ol class="fr-breadcrumb__list"><li><NuxtLink class="fr-breadcrumb__link" to="/admin">Administration</NuxtLink></li><li><a class="fr-breadcrumb__link" aria-current="page">Amorces</a></li></ol>
    </nav>
    <h1 class="fr-h2">Amorces</h1>
    <p class="fr-text--lead" style="max-width:65ch">Les collections constituées depuis l'open data avant l'ouverture de la section collaborative. Un import se rejoue sans dommage.</p>
    <div v-if="ouverture" class="fr-callout" :class="ouverture.ouverte ? 'fr-callout--green-emeraude' : ''">
      <h3 class="fr-callout__title">Section collaborative : {{ ouverture.ouverte ? 'ouverte' : 'pas encore ouverte' }}</h3>
      <p>{{ ouverture.en_controle }} amorce{{ ouverture.en_controle > 1 ? 's' : '' }} en contrôle ou au-delà sur {{ ouverture.requis }} requises.</p>
    </div>
    <div v-if="erreur" class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"><p>{{ erreur }}</p></div>
    <div class="fr-table" style="overflow-x:auto">
      <table>
        <caption>Catalogue des amorces</caption>
        <thead><tr><th>Amorce</th><th>Garant pressenti</th><th>État de la collection</th><th>Dernier import</th><th></th></tr></thead>
        <tbody>
          <tr v-for="a in amorces" :key="a.id">
            <td><strong>{{ a.titre }}</strong><div class="fr-text--xs" style="color:var(--text-mention-grey);max-width:40ch">{{ a.description }}</div>
              <NuxtLink v-if="a.collection_name" :to="`/c/${a.collection_name}`" class="fr-link fr-text--xs">{{ a.collection_name }}</NuxtLink></td>
            <td class="fr-text--sm">{{ a.garant_pressenti }}</td>
            <td><span v-if="a.etat_collab" class="fr-badge fr-badge--sm fr-badge--info">{{ libelleEtat(a.etat_collab) }}</span><span v-else class="fr-text--xs" style="color:var(--text-mention-grey)">pas encore créée</span></td>
            <td class="fr-text--sm">
              <span class="fr-badge fr-badge--sm" :class="{ jamais: '', en_cours: 'fr-badge--info', termine: 'fr-badge--success', echec: 'fr-badge--error' }[a.etat_import]">{{ a.etat_import.replace('_', ' ') }}</span>
              <div v-if="a.dernier_import_le" class="fr-text--xs">{{ dateCourte(a.dernier_import_le) }}</div>
              <div v-if="a.detail && a.detail.lignes_importees !== undefined" class="fr-text--xs">{{ a.detail.lignes_importees }} lignes · {{ a.detail.documents }} documents</div>
              <div v-if="a.erreur" class="fr-text--xs" style="color:var(--text-default-error)">{{ a.erreur }}</div>
            </td>
            <td><button class="fr-btn fr-btn--sm" :disabled="a.etat_import === 'en_cours'" @click="importer(a.id)">{{ a.etat_import === 'en_cours' ? 'En cours…' : (a.etat_import === 'jamais' ? 'Importer' : 'Réimporter') }}</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { dateCourte, libelleEtat, messageErreur } from '~/utils/collectif'
definePageMeta({ middleware: 'admin-only' })
const c = useCollectif()
const amorces = ref<any[]>([])
const ouverture = ref<any>(null)
const erreur = ref('')
let minuteur: any = null
async function charger() { try { const r = await c.amorces(); amorces.value = r.amorces; ouverture.value = r.ouverture } catch (e) { erreur.value = messageErreur(e) } }
async function importer(id: string) { erreur.value = ''; try { await c.importerAmorce(id); await charger() } catch (e) { erreur.value = messageErreur(e); await charger() } }
onMounted(() => { charger(); minuteur = setInterval(charger, 15000) })
onUnmounted(() => clearInterval(minuteur))
</script>
