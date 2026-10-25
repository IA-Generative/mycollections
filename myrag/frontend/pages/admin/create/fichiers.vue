<script setup lang="ts">
/**
 * Créer une collection depuis Fichiers, le Drive de La Suite numérique (docs/fichiers.md).
 * 1. l'instance : chacune dit sa zone et le niveau de sensibilité le plus haut de ses documents ;
 * 2. les dossiers à indexer, cochés dans l'arbre de ce que la personne voit dans l'instance ;
 * 3. la fiche : titre, description, sensibilité (le plafond de l'instance, ou plus haut), identifiant ;
 * 4. une fois créée (étape 3 de l'assistant, `?collection=`) : l'indexation suivie, la sensibilité,
 *    et la suite de l'assistant.
 * Drive est lu avec le jeton de la personne : ses droits, rien de plus. La collection reste privée
 * jusqu'à ce qu'elle l'ouvre à un groupe.
 */
import type { InstanceFichiers } from '~/utils/fichiers'
import type { ErreurResana } from '~/utils/resana'
import { couleurPlafond, niveauxPermis } from '~/utils/fichiers'
import { erreurResana, etiquetteResana } from '~/utils/resana'
import { lienEtape } from '~/utils/wizard'

interface Existante { collection: string, titre: string, chemins: string[], couverture: string }

const route = useRoute()
const router = useRouter()
const { get, post } = useApi()
const champ = useId()

const creee = computed(() => (route.query.collection as string) || '')
const phase = ref<'choisir' | 'fiche' | 'documents'>(creee.value ? 'documents' : 'choisir')
const { capacites, charger: chargerCapacites } = useCapacites()
const erreur = ref<ErreurResana | null>(null)

// ─── Les dossiers cochés (2) ──────────────────────────────────────────────────
const choisis = ref<string[]>([])
const dossiersChoisis = ref<{ id: string, chemin: string }[]>([])

// ─── 1. L'instance ────────────────────────────────────────────────────────────
const instances = ref<InstanceFichiers[]>([])
const charge = ref(false)
// Lien d'entrée depuis Fichiers : `?instance=<id>&dossier=<id>` préremplit le choix.
const instance = ref((route.query.instance as string) || '')
const existantes = ref<Existante[]>([])
const instanceChoisie = computed(() => instances.value.find(i => i.id === instance.value) || null)

async function chargerInstances () {
  charge.value = true
  erreur.value = null
  try {
    instances.value = (await get('/api/sources/fichiers/instances')).instances || []
    if (instances.value.length === 1 && !instance.value) {
      instance.value = instances.value[0]!.id
    }
  }
  catch (e) {
    erreur.value = erreurResana(e)
  }
  finally {
    charge.value = false
  }
}

watch(instance, async (id) => {
  existantes.value = []
  choisis.value = route.query.dossier && id === route.query.instance ? [route.query.dossier as string] : []
  if (!id) {
    return
  }
  try {
    existantes.value = (await get('/api/sources/fichiers/existant', { espace: id })).collections || []
  }
  catch {}
}, { immediate: true })

const peutContinuer = computed(() => !!instanceChoisie.value && dossiersChoisis.value.length > 0)

// ─── 3. La fiche ──────────────────────────────────────────────────────────────
const titre = ref('')
const description = ref('')
const sensibilite = ref('')
const suffixe = ref('')
const proposition = ref<{ identifiant: string, disponible: boolean, motif: string | null } | null>(null)
const envoi = ref(false)
const niveaux = computed(() => niveauxPermis(instanceChoisie.value?.sensibilite_max || 'internal'))
let minuterie: ReturnType<typeof setTimeout> | undefined

async function proposer () {
  if (!instance.value || !dossiersChoisis.value.length) {
    return
  }
  try {
    proposition.value = await get('/api/sources/fichiers/proposition', { espace: instance.value, dossier: dossiersChoisis.value[0]!.id, suffixe: suffixe.value })
  }
  catch {
    proposition.value = null
  }
}

watch(suffixe, () => {
  clearTimeout(minuterie)
  minuterie = setTimeout(proposer, 300)
})

function continuer () {
  if (!instanceChoisie.value) {
    return
  }
  const premier = dossiersChoisis.value[0]?.chemin || ''
  titre.value = premier.split('/').pop() || premier
  sensibilite.value = instanceChoisie.value.sensibilite_max
  suffixe.value = ''
  proposer()
  phase.value = 'fiche'
}

async function creerEtIndexer () {
  envoi.value = true
  erreur.value = null
  try {
    const r = await post('/api/sources/fichiers/collections', {
      espace_id: instance.value,
      dossiers: dossiersChoisis.value,
      titre: titre.value.trim(),
      description: description.value.trim(),
      sensibilite: sensibilite.value,
      suffixe: suffixe.value.trim(),
    })
    await router.replace({ query: { collection: r.collection } })
    phase.value = 'documents'
  }
  catch (e) {
    erreur.value = erreurResana(e)
    proposer()
  }
  finally {
    envoi.value = false
  }
}

// Étape 3 : le niveau des documents de l'instance, plancher de la sensibilité.
const minimum = ref<string | undefined>(undefined)
watch(creee, async (c) => {
  if (!c) {
    return
  }
  try {
    minimum.value = (await get(`/api/sources/fichiers/status/${encodeURIComponent(c)}`))?.sensibilite_min
  }
  catch {}
}, { immediate: true })

onMounted(() => {
  chargerCapacites()
  if (phase.value !== 'documents') {
    chargerInstances()
  }
})
onBeforeUnmount(() => clearTimeout(minuterie))
</script>

<template>
  <WizardEtape
    v-if="phase === 'documents'"
    :numero="3"
    titre="Suivre l'indexation"
    chapeau="Votre collection est créée. L'indexation continue en arrière-plan : vous pouvez passer à l'étape suivante sans attendre."
  >
    <template #formulaire>
      <DepotEtatResana
        v-if="capacites.fichiers"
        :collection="creee"
        source="fichiers"
        compact
      />
      <DepotSensibiliteResana
        class="fr-mt-4w"
        :collection="creee"
        :minimum="minimum"
      />
    </template>
    <template #actions>
      <ul class="fr-btns-group fr-btns-group--right fr-btns-group--inline-md">
        <li>
          <NuxtLink
            :to="`/c/${encodeURIComponent(creee)}`"
            class="fr-btn fr-btn--tertiary-no-outline"
          >
            Ouvrir la fiche de la collection
          </NuxtLink>
        </li>
        <li>
          <NuxtLink
            :to="lienEtape(4, creee, 'fichiers')"
            class="fr-btn"
          >
            Étape suivante
          </NuxtLink>
        </li>
      </ul>
    </template>
  </WizardEtape>

  <WizardEtape
    v-else
    :numero="phase === 'choisir' ? 1 : 2"
    :titre="phase === 'choisir' ? 'Choisir dans Fichiers' : 'Relire la fiche'"
  >
    <template #formulaire>
      <p class="fr-text--lg fr-mb-2w">
        {{ phase === 'choisir'
          ? 'Une instance, puis les dossiers à indexer. La collection reste privée : vous seul l\'interrogez, avec vos droits dans Fichiers.'
          : 'Tout est prérempli d\'après l\'instance et le dossier : relisez, puis créez. L\'indexation se fait en arrière-plan.' }}
      </p>

      <div
        v-if="erreur"
        class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"
        role="alert"
      >
        <p>{{ erreur.message }}</p>
      </div>

      <template v-if="phase === 'choisir'">
        <p
          v-if="charge"
          class="fr-text--sm"
          role="status"
        >
          Chargement des instances…
        </p>
        <p
          v-else-if="!instances.length && !erreur"
          class="fr-text--sm"
        >
          Aucune instance de Fichiers n'est proposée ici.
        </p>

        <fieldset
          v-if="instances.length"
          class="fr-fieldset"
          :aria-labelledby="`${champ}-instances`"
        >
          <legend
            :id="`${champ}-instances`"
            class="fr-fieldset__legend"
          >
            Où sont vos fichiers ?
            <span class="fr-hint-text">Chaque instance a un niveau de sensibilité maximal. Votre collection le reprend, et ne pourra pas descendre en dessous.</span>
          </legend>
          <div
            v-for="i in instances"
            :key="i.id"
            class="fr-fieldset__element"
          >
            <div class="fr-radio-group fr-radio-rich">
              <input
                :id="`${champ}-${i.id}`"
                v-model="instance"
                type="radio"
                :name="`${champ}-instance`"
                :value="i.id"
              >
              <label
                class="fr-label"
                :for="`${champ}-${i.id}`"
              >
                {{ i.titre }}
                <span class="fr-hint-text">{{ i.zone || i.hote }}<template v-if="i.description"> — {{ i.description }}</template></span>
                <span class="fr-mt-1v">
                  <span
                    class="fr-badge fr-badge--sm fr-badge--no-icon"
                    :class="couleurPlafond(i.sensibilite_max)"
                  >Plafond : {{ i.sensibilite_libelle }}</span>
                </span>
              </label>
            </div>
          </div>
        </fieldset>

        <div
          v-if="instanceChoisie"
          class="fr-alert fr-alert--info fr-alert--sm fr-mb-2w"
        >
          <p>
            Mes collections lit Fichiers avec <strong>vos</strong> droits : seuls les documents que vous pouvez ouvrir
            sont indexés. La collection naît privée ; vous pourrez l'ouvrir à un groupe une fois l'import fini.
          </p>
        </div>

        <div
          v-if="existantes.length"
          class="fr-alert fr-alert--info fr-alert--sm fr-my-2w"
        >
          <p
            v-for="c in existantes"
            :key="c.collection"
          >
            Votre collection <NuxtLink :to="`/c/${c.collection}/upload`">
              « {{ c.titre }} »
            </NuxtLink> indexe déjà cette instance ({{ etiquetteResana(c).replace('Résana', 'Fichiers') }}, {{ c.chemins.join(', ') }}) :
            vous pouvez y ajouter des dossiers par « Modifier la sélection ».
          </p>
        </div>

        <DepotDossiersResana
          v-if="instanceChoisie"
          v-model="choisis"
          class="fr-mt-3w"
          source="fichiers"
          :espace="instance"
          @dossiers="dossiersChoisis = $event"
        />
      </template>

      <template v-else-if="instanceChoisie">
        <div class="fr-input-group">
          <label
            class="fr-label"
            :for="`${champ}-titre`"
          >Titre
            <span class="fr-hint-text">Le nom du dossier ; vous pouvez le préciser.</span>
          </label>
          <input
            :id="`${champ}-titre`"
            v-model="titre"
            class="fr-input"
          >
        </div>
        <div class="fr-input-group">
          <label
            class="fr-label"
            :for="`${champ}-description`"
          >Description (facultatif)</label>
          <textarea
            :id="`${champ}-description`"
            v-model="description"
            class="fr-input"
            rows="2"
            :placeholder="`Dossier « ${dossiersChoisis.map(d => d.chemin).join(' · ')} » de ${instanceChoisie.titre}.`"
          />
        </div>

        <fieldset class="fr-fieldset">
          <legend class="fr-fieldset__legend">
            Sensibilité des documents
            <span class="fr-hint-text">
              {{ instanceChoisie.titre }} peut contenir des documents jusqu'au niveau « {{ instanceChoisie.sensibilite_libelle }} ».
              La collection prend ce niveau ; vous pouvez la placer plus haut, jamais plus bas. Chaque destination (chat,
              recherche, extension) accepte les collections jusqu'à un certain niveau.
            </span>
          </legend>
          <div
            v-for="n in niveaux"
            :key="n.valeur"
            class="fr-fieldset__element fr-fieldset__element--inline"
          >
            <div class="fr-radio-group">
              <input
                :id="`${champ}-sens-${n.valeur}`"
                v-model="sensibilite"
                type="radio"
                :name="`${champ}-sens`"
                :value="n.valeur"
              >
              <label
                class="fr-label"
                :for="`${champ}-sens-${n.valeur}`"
              >{{ n.libelle }}</label>
            </div>
          </div>
        </fieldset>

        <div class="identifiant fr-mb-2w">
          <p class="fr-text--sm fr-mb-1v">
            Identifiant : <code>{{ proposition?.identifiant || '…' }}</code>
          </p>
          <p class="fr-text--xs fr-mb-0 identifiant__pourquoi">
            Posé d'après l'instance et le dossier. Le préfixe « fichiers- » est réservé aux collections importées de
            Fichiers. Il ne change pas si la sélection de dossiers change.
          </p>
          <div
            v-if="proposition && !proposition.disponible"
            class="fr-input-group fr-mt-2w fr-mb-0"
          >
            <label
              class="fr-label"
              :for="`${champ}-suffixe`"
            >Suffixe
              <span class="fr-hint-text">Une collection porte déjà cet identifiant : nommez l'usage de la seconde.</span>
            </label>
            <input
              :id="`${champ}-suffixe`"
              v-model="suffixe"
              class="fr-input"
              maxlength="30"
            >
          </div>
        </div>

        <ul class="fr-tags-group fr-mb-1w">
          <li><span class="fr-tag fr-tag--sm">Fichiers</span></li>
          <li><span class="fr-tag fr-tag--sm">Privée</span></li>
        </ul>
        <p class="fr-text--sm fr-mb-0">
          <strong>{{ instanceChoisie.titre }}</strong> — {{ dossiersChoisis.length }} dossier{{ dossiersChoisis.length > 1 ? 's' : '' }} :
          {{ dossiersChoisis.map(d => d.chemin).join(', ') }}.
        </p>
      </template>
    </template>

    <template #actions>
      <ul class="fr-btns-group fr-btns-group--right fr-btns-group--inline-md">
        <li>
          <NuxtLink
            to="/admin/create"
            class="fr-btn fr-btn--tertiary-no-outline"
          >
            Annuler
          </NuxtLink>
        </li>
        <li v-if="phase === 'fiche'">
          <button
            type="button"
            class="fr-btn fr-btn--secondary"
            @click="phase = 'choisir'"
          >
            Étape précédente
          </button>
        </li>
        <li v-if="phase === 'choisir'">
          <button
            type="button"
            class="fr-btn"
            :disabled="!peutContinuer"
            @click="continuer"
          >
            Continuer
          </button>
        </li>
        <li v-else>
          <button
            type="button"
            class="fr-btn"
            :disabled="envoi || !titre.trim() || !proposition?.disponible"
            @click="creerEtIndexer"
          >
            {{ envoi ? 'Création…' : 'Créer et indexer' }}
          </button>
        </li>
      </ul>
    </template>
  </WizardEtape>
</template>

<style scoped>
.identifiant__pourquoi { color: var(--text-mention-grey); }
</style>
