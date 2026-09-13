<template>
  <div>
    <div class="fr-mb-3w">
      <h1 class="fr-h2">Demandes de la communauté</h1>
      <p class="fr-text--lead" style="max-width:65ch">
        Dites quel jeu de données vous manque, rassemblez {{ capacites.seuil_chantier }} collègues et un garant, et le chantier démarre.
        Un chantier sans nouvelle depuis trente jours est marqué <strong>en sommeil</strong>.
        <NuxtLink to="/guide" class="fr-link">Comment ça se passe ?</NuxtLink>
      </p>
      <p class="fr-text--sm" style="color:var(--text-mention-grey)">
        Seuil de chantier : <strong>{{ capacites.seuil_chantier }} soutiens et un garant</strong> — un paramètre de la plateforme, figé sur chaque demande à sa création.
      </p>
    </div>

    <div v-if="!chargees" class="fr-callout"><p>Chargement…</p></div>
    <div v-else-if="!capacites.demandes" class="fr-alert fr-alert--info"><p>Les demandes de jeux de données ne sont pas activées sur cette plateforme.</p></div>
    <template v-else>
      <CollectifFormulaireDemande :mail="mail" :chercher="chercher" :deposer="deposerDemande" @deposee="apresDepot" @moi-aussi="moiAussi" />

      <div v-if="message" class="fr-alert fr-alert--success fr-alert--sm fr-mb-2w"><p>{{ message }}</p></div>
      <div v-if="erreur" class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"><p>{{ erreur }}</p></div>

      <div class="fr-grid-row fr-grid-row--middle fr-mb-2w" style="gap:1rem">
        <h2 class="fr-h4" style="margin:0">{{ demandesFiltrees.length }} demande{{ demandesFiltrees.length > 1 ? 's' : '' }}</h2>
        <div class="collectif-roles" role="group" aria-label="Filtrer par état">
          <button v-for="e in ['toutes', 'ouverte', 'chantier', 'realisee', 'close']" :key="e" class="collectif-roles__role" :class="{ pris: filtre === e }" @click="filtre = e">{{ e === 'toutes' ? 'toutes' : LIBELLES_DEMANDE[e].libelle }}</button>
        </div>
      </div>

      <p v-if="demandes === null" class="fr-text--sm">Liste indisponible.</p>
      <p v-else-if="demandesFiltrees.length === 0" class="fr-text--sm" style="color:var(--text-mention-grey)">Aucune demande. La première est peut-être la vôtre.</p>
      <div v-else class="fr-table fr-table--no-caption" style="overflow-x:auto">
        <table>
          <caption>Demandes</caption>
          <thead><tr><th>Demande</th><th>Fréquence</th><th>Soutiens</th><th>Garant</th><th>État</th><th>Je peux aider</th><th></th></tr></thead>
          <tbody>
            <tr v-for="d in demandesFiltrees" :key="d.id">
              <td>
                <NuxtLink :to="`/demandes/${d.id}`" class="fr-link"><strong>{{ d.titre }}</strong></NuxtLink>
                <div class="fr-text--xs" style="color:var(--text-mention-grey);max-width:34ch">{{ d.usage }}</div>
              </td>
              <td>{{ d.frequence }}</td>
              <td><span class="collectif-jauge"><i :style="`--p:${progression(d.nb_soutiens, d.seuil).pourcent}%`"></i>{{ progression(d.nb_soutiens, d.seuil).texte }}</span></td>
              <td><span class="fr-badge fr-badge--sm" :class="d.garant ? 'fr-badge--success' : 'fr-badge--warning'">{{ d.garant ? '✓ garant' : 'à pourvoir' }}</span></td>
              <td>
                <span class="fr-badge fr-badge--sm" :class="LIBELLES_DEMANDE[d.etat]?.badge">{{ LIBELLES_DEMANDE[d.etat]?.libelle || d.etat }}</span>
                <span v-if="d.sommeil" class="fr-badge fr-badge--sm fr-ml-1w">en sommeil</span>
                <div v-if="ceQuiManque(d)" class="fr-text--xs" style="color:var(--text-mention-grey)">{{ ceQuiManque(d) }}</div>
              </td>
              <td><CollectifJePeuxAider :mon-role="d.mon_role" :garant="d.garant" :ferme="['realisee', 'close'].includes(d.etat)" @choisir="(r, m) => aider(d, r, m)" /></td>
              <td>
                <button v-if="!['realisee', 'close'].includes(d.etat)" class="fr-btn fr-btn--sm" :class="d.soutenue_par_moi ? 'fr-btn--tertiary' : ''" @click="d.soutenue_par_moi ? retirer(d) : aider(d, 'soutien', 0)">
                  {{ d.soutenue_par_moi ? 'Retirer' : 'Moi aussi' }}
                </button>
                <NuxtLink v-else-if="d.collection_name" :to="`/c/${d.collection_name}`" class="fr-btn fr-btn--sm fr-btn--secondary">Ouvrir la collection</NuxtLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { LIBELLES_DEMANDE, ceQuiManque, messageErreur, progression } from '~/utils/collectif'
const { capacites, chargees, charger } = useCapacites()
const { listerDemandes, deposerDemande, soutenir, retirerSoutien } = useCollectif()
const { user } = useAuth()
const demandes = ref<any[] | null>([])
const filtre = ref('toutes')
const message = ref('')
const erreur = ref('')
const mail = computed(() => (user.value as any)?.profile?.email || '')
const demandesFiltrees = computed(() => (demandes.value || []).filter(d => filtre.value === 'toutes' || d.etat === filtre.value))

async function recharger() {
  try { demandes.value = (await listerDemandes()).demandes } catch (e) { demandes.value = null; erreur.value = messageErreur(e) }
}
async function chercher(q: string) { return (await listerDemandes({ q })).demandes }
function remplacer(d: any) { if (demandes.value) demandes.value = demandes.value.map(x => (x.id === d.id ? d : x)) }
async function aider(d: any, role: string, minutes: number) {
  erreur.value = ''
  try { remplacer((await soutenir(d.id, role, minutes || null)).demande) } catch (e) { erreur.value = messageErreur(e) }
}
async function retirer(d: any) { try { remplacer((await retirerSoutien(d.id)).demande) } catch (e) { erreur.value = messageErreur(e) } }
async function moiAussi(id: string) { const d = (demandes.value || []).find(x => x.id === id) || { id }; await aider(d, 'soutien', 0) }
function apresDepot(d: any) { message.value = `Demande « ${d.titre} » déposée. Vous êtes abonné·e à son avancement.`; if (demandes.value) demandes.value = [d, ...demandes.value] }
onMounted(async () => { await charger(); if (capacites.value.demandes) await recharger() })
</script>
