<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { titre } = useTitreCollection(id)
// Le document irait au moteur de recherche : pendant une panne, l'envoi échouerait.
const { rechercheIndisponible } = useEtatService()
const sensitivity = ref('public')
const error = ref('')
</script>

<template>
  <div>
    <FilAriane
      :collection="id"
      :titre="titre"
      rubrique="Ajouter des documents"
    />

    <h1 class="fr-h3">
      Ajouter des documents — {{ titre }}
    </h1>

    <div class="fr-grid-row fr-grid-row--gutters">
      <div class="fr-col-12 fr-col-lg-8">
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
            <option value="public">
              Public
            </option>
            <option value="internal">
              Interne
            </option>
            <option value="restricted">
              Restreint
            </option>
            <option value="confidential">
              Confidentiel
            </option>
          </select>
        </div>

        <DepotZone
          class="fr-mt-4w"
          :collection="id"
          :sensitivity="sensitivity"
          :desactive="rechercheIndisponible"
        />
        <p
          v-if="rechercheIndisponible"
          class="fr-message fr-message--info fr-mt-1w"
        >
          L'ajout de documents reviendra avec la recherche. Le bandeau en haut de la page vous préviendra.
        </p>
        <div
          v-if="error"
          class="fr-alert fr-alert--error fr-mt-4w"
        >
          <p>{{ error }}</p>
        </div>
      </div>
    </div>
  </div>
</template>
