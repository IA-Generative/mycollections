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
        <strong>Quand une demande devient-elle un chantier ?</strong>
        Quand <strong>{{ capacites.seuil_chantier }} collègues</strong> l’ont soutenue — la preuve que le besoin est partagé —
        et qu’<strong>un garant</strong> s’est proposé : la personne qui veille à ce que les données restent justes et à jour (environ deux heures par mois).
        Ce nombre est fixé au dépôt de la demande : s’il change plus tard, les demandes déjà ouvertes gardent le leur.
      </p>
    </div>

    <div v-if="!chargees" class="fr-callout"><p>Chargement…</p></div>
    <div v-else-if="!capacites.demandes" class="fr-alert fr-alert--info"><p>Les demandes de jeux de données ne sont pas activées sur cette plateforme.</p></div>
    <template v-else>
      <!-- Le formulaire se déplie à la demande : ouvert d'office, il occupait tout l'écran et cachait
           la liste — alors que le premier geste utile est souvent de SOUTENIR une demande existante.
           `v-show`, pas `v-if` : replier ne perd pas ce qui a été saisi. -->
      <section class="demande-depot fr-mb-4w" :class="{ ouvert: formulaireOuvert }">
        <div class="demande-depot__tete">
          <div>
            <h2 class="fr-h6 fr-mb-0">Un jeu de données vous manque ?</h2>
            <p v-if="!formulaireOuvert" class="fr-text--sm fr-mb-0" style="color:var(--text-mention-grey)">
              Regardez d'abord la liste ci-dessous : s'il est déjà demandé, un « Moi aussi » compte davantage qu'une nouvelle demande.
            </p>
          </div>
          <button type="button" class="fr-btn fr-btn--sm fr-btn--icon-left" :class="formulaireOuvert ? 'fr-btn--tertiary fr-icon-arrow-up-s-line' : 'fr-icon-add-line'"
                  aria-controls="formulaire-demande" :aria-expanded="formulaireOuvert" @click="basculer">
            {{ formulaireOuvert ? 'Replier le formulaire' : 'Demander un jeu de données' }}
          </button>
        </div>
        <div v-show="formulaireOuvert" id="formulaire-demande" class="fr-mt-2w">
          <CollectifFormulaireDemande :mail="mail" :chercher="chercher" :deposer="deposerDemande" @deposee="apresDepot" @moi-aussi="moiAussi" />
        </div>
      </section>

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
import { computed, nextTick, onMounted, ref } from 'vue'
import { LIBELLES_DEMANDE, ceQuiManque, messageErreur, progression } from '~/utils/collectif'
const { capacites, chargees, charger } = useCapacites()
const { listerDemandes, deposerDemande, soutenir, retirerSoutien } = useCollectif()
const { user } = useAuth()
const demandes = ref<any[] | null>([])
const filtre = ref('toutes')
const route = useRoute()
// L'accueil (« Demander un jeu de données ») arrive ici avec ?deposer=1 : le formulaire s'ouvre d'office.
const formulaireOuvert = ref(route.query.deposer === '1')
function basculer() {
  formulaireOuvert.value = !formulaireOuvert.value
  if (formulaireOuvert.value) nextTick(() => document.getElementById('d-titre')?.focus())
}
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
function apresDepot(d: any) {
  message.value = `Demande « ${d.titre} » déposée. Vous êtes abonné·e à son avancement.`
  if (demandes.value) demandes.value = [d, ...demandes.value]
  formulaireOuvert.value = false   // déposée : on rend la place à la liste, où elle apparaît en tête
}
onMounted(async () => {
  await charger()
  if (capacites.value.demandes) await recharger()
  if (formulaireOuvert.value) nextTick(() => document.getElementById('d-titre')?.focus())
})
</script>

<style scoped>
.demande-depot { border: 1px solid var(--border-default-grey); border-left: 4px solid var(--border-active-blue-france); padding: 1rem 1.25rem; }
.demande-depot__tete { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .75rem 1.5rem; }
.demande-depot__tete > div { flex: 1 1 320px; }
/* Replié dans un encadré, le formulaire n'a plus besoin de son propre cadre de mise en avant. */
.demande-depot :deep(form.fr-callout) { margin-bottom: 0; }
.demande-depot :deep(form.fr-callout > .fr-callout__title) { display: none; }
</style>
