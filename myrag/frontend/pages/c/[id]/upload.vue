<script setup lang="ts">
import { SENSIBILITES } from '~/utils/libelles'
import { estCollectionResana, titrePageDocuments } from '~/utils/resana'

const route = useRoute()
const id = route.params.id as string
const { titre, retenir } = useTitreCollection(id, { charger: false })
const { get, patch } = useApi()
// Le document irait au moteur de recherche : pendant une panne, l'envoi échouerait.
const { rechercheIndisponible } = useEtatService()
const strategy = ref('auto')
const sensitivity = ref('public')
// undefined tant que la fiche n'a pas répondu (rien ne s'affiche : pas de dépôt montré puis
// retiré) ; null si elle est illisible (une partition sans fiche garde le dépôt).
const fiche = ref<{ source_type?: string | null, sensitivity?: string } | null | undefined>(undefined)
const resana = computed(() => estCollectionResana(fiche.value))
const titrePage = computed(() => titrePageDocuments(fiche.value))
// La carte Résana suit la capacité (docs/resana.md).
const { capacites, charger } = useCapacites()

onMounted(async () => {
  charger()
  try {
    const f = await get(`/api/collections/${id}`)
    retenir(f)
    fiche.value = f
    if (f?.sensitivity) { sensitivity.value = f.sensitivity }
  }
  catch {
    fiche.value = null
  }
})

// Une collection Résana : la sensibilité est celle de la fiche, enregistrée dès qu'on la change.
const enregistrement = ref(false)
const sensibiliteEnregistree = ref('')
const erreurSensibilite = ref('')
async function enregistrerSensibilite () {
  enregistrement.value = true
  sensibiliteEnregistree.value = ''
  erreurSensibilite.value = ''
  try {
    const f = await patch(`/api/collections/${id}`, { sensitivity: sensitivity.value })
    fiche.value = { ...fiche.value, ...f }
    sensibiliteEnregistree.value = 'Sensibilité enregistrée.'
  }
  catch {
    erreurSensibilite.value = 'La sensibilité n\'a pas pu être enregistrée. Réessayez dans un instant.'
    sensitivity.value = fiche.value?.sensitivity || 'internal'
  }
  finally {
    enregistrement.value = false
  }
}
</script>

<template>
  <div>
    <FilAriane
      :collection="id"
      :titre="titre"
      :rubrique="titrePage"
    />

    <h1 class="fr-h3">
      {{ titrePage }} — {{ titre }}
    </h1>

    <div
      v-if="fiche !== undefined"
      class="fr-grid-row fr-grid-row--gutters"
    >
      <!-- Une collection Résana se remplit par sa sélection de dossiers : ni dépôt ni découpage. -->
      <div
        v-if="resana"
        class="fr-col-12 fr-col-lg-8"
      >
        <DepotEtatResana
          v-if="capacites.resana"
          :collection="id"
          class="fr-mt-2w"
        />
        <p
          v-else
          class="fr-message fr-message--info fr-mt-2w"
        >
          La connexion à Résana est fermée pour le moment : la sélection et la mise à jour reviendront avec elle.
        </p>

        <div class="fr-select-group fr-mt-4w">
          <label
            class="fr-label"
            for="sensitivity"
          >Sensibilité
            <span class="fr-hint-text">Elle accompagne chaque document envoyé à l'indexeur, à partir de la prochaine mise à jour. Elle ne change pas qui peut lire la collection.</span>
          </label>
          <select
            id="sensitivity"
            v-model="sensitivity"
            class="fr-select"
            :disabled="enregistrement"
            @change="enregistrerSensibilite"
          >
            <option
              v-for="s in SENSIBILITES"
              :key="s.valeur"
              :value="s.valeur"
            >
              {{ s.libelle }}
            </option>
          </select>
          <p
            class="fr-message fr-mt-1v"
            :class="{ 'fr-message--error': erreurSensibilite, 'fr-message--valid': sensibiliteEnregistree }"
            aria-live="polite"
          >
            {{ erreurSensibilite || sensibiliteEnregistree }}
          </p>
        </div>
      </div>

      <div
        v-else
        class="fr-col-12 fr-col-lg-8"
      >
        <!-- Strategy -->
        <div class="fr-select-group fr-mt-2w">
          <label
            class="fr-label"
            for="strategy"
          >Découpage du document
            <span class="fr-hint-text">Comment un fichier texte (.txt, .md, .csv) est coupé en passages, que l'assistant retrouve et cite. Les PDF, Word et autres documents sont découpés par le moteur de recherche.</span>
          </label>
          <select
            id="strategy"
            v-model="strategy"
            class="fr-select"
          >
            <option value="auto">
              Automatique (détection du type)
            </option>
            <option value="article">
              Par article (code juridique)
            </option>
            <option value="section">
              Par section (rapport)
            </option>
            <option value="qr">
              Par question-réponse (FAQ)
            </option>
            <option value="length">
              Par longueur fixe
            </option>
          </select>
        </div>

        <!-- Sensitivity -->
        <div class="fr-select-group fr-mt-2w">
          <label
            class="fr-label"
            for="sensitivity"
          >Sensibilité</label>
          <select
            id="sensitivity"
            v-model="sensitivity"
            class="fr-select"
          >
            <option
              v-for="s in SENSIBILITES"
              :key="s.valeur"
              :value="s.valeur"
            >
              {{ s.libelle }}
            </option>
          </select>
        </div>

        <DepotZone
          class="fr-mt-4w"
          :collection="id"
          :strategy="strategy"
          :sensitivity="sensitivity"
          :desactive="rechercheIndisponible"
        />
        <p
          v-if="rechercheIndisponible"
          class="fr-message fr-message--info fr-mt-1w"
        >
          L'ajout de documents reviendra avec la recherche. Le bandeau en haut de la page vous préviendra.
        </p>
      </div>
    </div>
  </div>
</template>
