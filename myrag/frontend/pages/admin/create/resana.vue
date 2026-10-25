<script setup lang="ts">
/**
 * Créer une collection depuis Résana (docs/resana.md). La collection est ancrée sur un ESPACE :
 * c'est lui qui la nomme (`resana-<numéro>`, posé par le serveur — le numéro est la seule clé
 * unique d'un espace). Les dossiers cochés sont un réglage d'indexation, modifiable ensuite.
 * 1. l'espace (avec une recherche), et les collections déjà ancrées dessus ;
 * 2. les dossiers à indexer, cochés dans l'arbre de l'espace ;
 * 3. la fiche : titre (le nom de l'espace), entité administrative, identifiant expliqué ;
 * 4. une fois créée (étape 3 de l'assistant, `?collection=`) : l'indexation suivie, la sensibilité,
 *    et la suite de l'assistant (vérifier les réponses, puis l'étape 5 qui dit qu'elle reste privée).
 */
import type { ErreurResana, EspaceResana } from '~/utils/resana'
import { descriptionParDefaut, erreurResana, etiquetteResana, titreDepuisEspace } from '~/utils/resana'
import { lienEtape } from '~/utils/wizard'

interface Existante { collection: string, titre: string, chemins: string[], couverture: string }

const route = useRoute()
const router = useRouter()
const { get, post } = useApi()
const champ = useId()

// La collection créée est dans l'adresse : l'étape 3 se rouvre telle quelle (rechargement, retour
// depuis l'étape 4).
const creee = computed(() => (route.query.collection as string) || '')
const phase = ref<'choisir' | 'fiche' | 'documents'>(creee.value ? 'documents' : 'choisir')
const { capacites, charger: chargerCapacites } = useCapacites()
const erreur = ref<ErreurResana | null>(null)

// ─── Les dossiers cochés (2), déclarés d'abord : choisir un autre espace les vide ─────────────
const choisis = ref<string[]>([])
const dossiersChoisis = ref<{ id: string, chemin: string }[]>([])

// ─── 1. L'espace ─────────────────────────────────────────────────────────────
const espaces = ref<EspaceResana[]>([])
const espace = ref('')
const chargeEspaces = ref(false)
const existantes = ref<Existante[]>([])
const optionsEspaces = computed(() => espaces.value.map(e => ({ value: e.id, label: e.nom, hint: e.objet || e.description || '' })))
const espaceChoisi = computed(() => espaces.value.find(e => e.id === espace.value) || null)

async function chargerEspaces () {
  chargeEspaces.value = true
  erreur.value = null
  try {
    espaces.value = (await get('/api/sources/resana/espaces')).espaces || []
  }
  catch (e) {
    erreur.value = erreurResana(e)
  }
  finally {
    chargeEspaces.value = false
  }
}

watch(espace, async (id) => {
  existantes.value = []
  choisis.value = []
  if (!id) {
    return
  }
  try {
    existantes.value = (await get('/api/sources/resana/existant', { espace: id })).collections || []
  }
  catch {}
})

const peutContinuer = computed(() => !!espaceChoisi.value && dossiersChoisis.value.length > 0)

// ─── 3. La fiche ─────────────────────────────────────────────────────────────
const titre = ref('')
const entite = ref('')
const description = ref('')
const suffixe = ref('')
const proposition = ref<{ identifiant: string, disponible: boolean, motif: string | null } | null>(null)
const envoi = ref(false)
let minuterie: ReturnType<typeof setTimeout> | undefined

async function proposer () {
  if (!espace.value) {
    return
  }
  try {
    proposition.value = await get('/api/sources/resana/proposition', { espace: espace.value, suffixe: suffixe.value })
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
  if (!espaceChoisi.value) {
    return
  }
  titre.value = titreDepuisEspace(espaceChoisi.value)
  suffixe.value = ''
  proposer()
  phase.value = 'fiche'
}

async function creerEtIndexer () {
  if (!espaceChoisi.value) {
    return
  }
  envoi.value = true
  erreur.value = null
  try {
    const r = await post('/api/sources/resana/collections', {
      espace_id: espace.value,
      dossiers: dossiersChoisis.value,
      titre: titre.value.trim(),
      description: description.value.trim(),
      entite: entite.value.trim(),
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

onMounted(() => {
  chargerCapacites()
  if (phase.value !== 'documents') {
    chargerEspaces()
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
        v-if="capacites.resana"
        :collection="creee"
        compact
      />
      <DepotSensibiliteResana
        class="fr-mt-4w"
        :collection="creee"
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
            :to="lienEtape(4, creee, 'resana')"
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
    :titre="phase === 'choisir' ? 'Choisir dans Résana' : 'Relire la fiche'"
  >
    <template #formulaire>
      <p class="fr-text--lg fr-mb-2w">
        {{ phase === 'choisir'
          ? 'Un espace, puis les dossiers à indexer. La collection reste privée : vous seul l\'interrogez, avec vos droits Résana.'
          : 'Tout est prérempli d\'après l\'espace : relisez, puis créez. L\'indexation se fait en arrière-plan.' }}
      </p>
      <div
        v-if="phase === 'choisir'"
        class="fr-alert fr-alert--info fr-alert--sm fr-mb-2w"
      >
        <p>
          Mes collections lit Résana avec <strong>vos</strong> droits : seuls les documents que vous pouvez ouvrir dans
          Résana sont indexés. Un document qui vous est refusé est écarté, et listé après l'import avec la raison.
        </p>
      </div>

      <div
        v-if="erreur"
        class="fr-alert fr-alert--sm fr-mb-2w"
        :class="erreur.code === 'session_absente' ? 'fr-alert--warning' : 'fr-alert--error'"
        role="alert"
      >
        <p>{{ erreur.message }}</p>
        <p class="fr-mt-1w">
          <a
            v-if="erreur.urlConnexion"
            :href="erreur.urlConnexion"
            class="fr-link fr-mr-2w"
            target="_blank"
            rel="noopener"
          >Se connecter à Résana<span class="fr-sr-only"> (nouvelle fenêtre)</span></a>
          <button
            v-if="phase === 'choisir' && !espaces.length"
            type="button"
            class="fr-btn fr-btn--sm fr-btn--tertiary"
            :disabled="chargeEspaces"
            @click="chargerEspaces"
          >
            {{ chargeEspaces ? 'Nouvelle tentative…' : 'Réessayer' }}
          </button>
        </p>
      </div>

      <!-- 1 et 2 : l'espace, puis les dossiers -->
      <template v-if="phase === 'choisir'">
        <p
          v-if="chargeEspaces"
          class="fr-text--sm"
          role="status"
        >
          Ouverture de votre session Résana… Cela peut prendre jusqu'à une minute et demie la première fois.
        </p>

        <ListeDeroulanteRiche
          v-if="espaces.length"
          v-model="espace"
          :options="optionsEspaces"
          label="Espace"
          :hint="`${espaces.length} espace${espaces.length > 1 ? 's' : ''} ouvert${espaces.length > 1 ? 's' : ''} à votre compte. Tapez une partie du nom, de l'objet ou de la description.`"
          placeholder="Rechercher un espace…"
        />
        <p
          v-else-if="!chargeEspaces && !erreur"
          class="fr-text--sm"
        >
          Aucun espace Résana ne vous est ouvert.
        </p>

        <!-- Déjà ancrées sur cet espace : les reprendre plutôt qu'en créer une de plus. -->
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
            </NuxtLink> indexe déjà cet espace ({{ etiquetteResana(c) }}, {{ c.chemins.join(', ') }}) : vous pouvez y ajouter
            des dossiers par « Modifier la sélection ». Une seconde collection sur le même espace demandera un suffixe.
          </p>
        </div>

        <DepotDossiersResana
          v-if="espaceChoisi"
          v-model="choisis"
          class="fr-mt-3w"
          :espace="espace"
          @dossiers="dossiersChoisis = $event"
        />
      </template>

      <!-- 3 : la fiche -->
      <template v-else-if="espaceChoisi">
        <div class="fr-input-group">
          <label
            class="fr-label"
            :for="`${champ}-titre`"
          >Titre
            <span class="fr-hint-text">Le nom de l'espace ; vous pouvez le préciser.</span>
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
            :for="`${champ}-entite`"
          >Entité administrative (facultatif)
            <span class="fr-hint-text">Résana ne la donne pas : elle distingue des espaces de même nom d'une entité à l'autre.</span>
          </label>
          <input
            :id="`${champ}-entite`"
            v-model="entite"
            class="fr-input"
            placeholder="ex. Préfecture de la région Bretagne"
            autocomplete="organization"
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
            :placeholder="descriptionParDefaut(espaceChoisi, entite)"
          />
        </div>

        <div class="identifiant fr-mb-2w">
          <p class="fr-text--sm fr-mb-1v">
            Identifiant : <code>{{ proposition?.identifiant || '…' }}</code>
          </p>
          <p class="fr-text--xs fr-mb-0 identifiant__pourquoi">
            Posé d'après le numéro de l'espace, la seule clé unique dans Résana (plusieurs entités ont des espaces de même
            nom). Le préfixe « resana- » est réservé aux collections importées de Résana. Il ne change pas si la sélection
            de dossiers change.
          </p>
          <div
            v-if="proposition && !proposition.disponible"
            class="fr-input-group fr-mt-2w fr-mb-0"
          >
            <label
              class="fr-label"
              :for="`${champ}-suffixe`"
            >Suffixe
              <span class="fr-hint-text">Une collection porte déjà cet identifiant : nommez l'usage de la seconde (ex. car, comites).</span>
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
          <li><span class="fr-tag fr-tag--sm">Résana</span></li>
          <li><span class="fr-tag fr-tag--sm">Privée</span></li>
        </ul>
        <p class="fr-text--sm fr-mb-0">
          <strong>{{ espaceChoisi.nom }}</strong> — {{ dossiersChoisis.length }} dossier{{ dossiersChoisis.length > 1 ? 's' : '' }} :
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
