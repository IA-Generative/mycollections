<template>
  <div>
    <FilAriane :collection="id" :titre="titre" rubrique="Ajouter des documents" />

    <h1 class="fr-h3">Ajouter des documents — {{ titre }}</h1>

    <div class="fr-grid-row fr-grid-row--gutters">
      <div class="fr-col-12 fr-col-lg-8">
        <!-- Strategy -->
        <div class="fr-select-group fr-mt-2w">
          <label class="fr-label" for="strategy">Découpage du document
            <span class="fr-hint-text">Comment un fichier texte (.txt, .md, .csv) est coupé en passages, que l'assistant retrouve et cite. Les PDF, Word et autres documents sont découpés par le moteur de recherche.</span>
          </label>
          <select id="strategy" class="fr-select" v-model="strategy">
            <option value="auto">Automatique (détection du type)</option>
            <option value="article">Par article (code juridique)</option>
            <option value="section">Par section (rapport)</option>
            <option value="qr">Par question-réponse (FAQ)</option>
            <option value="length">Par longueur fixe</option>
          </select>
        </div>

        <!-- Sensitivity -->
        <div class="fr-select-group fr-mt-2w">
          <label class="fr-label" for="sensitivity">Sensibilité</label>
          <select id="sensitivity" class="fr-select" v-model="sensitivity">
            <option value="public">Public</option>
            <option value="internal">Interne</option>
            <option value="restricted">Restreint</option>
            <option value="confidential">Confidentiel</option>
          </select>
        </div>

        <DepotZone class="fr-mt-4w" :collection="id" :strategy="strategy" :sensitivity="sensitivity" :desactive="rechercheIndisponible" />
        <p v-if="rechercheIndisponible" class="fr-message fr-message--info fr-mt-1w">
          L'ajout de documents reviendra avec la recherche. Le bandeau en haut de la page vous préviendra.
        </p>
        <div v-if="error" class="fr-alert fr-alert--error fr-mt-4w">
          <p>{{ error }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { titre } = useTitreCollection(id)
// Le document irait au moteur de recherche : pendant une panne, l'envoi échouerait.
const { rechercheIndisponible } = useEtatService()
const strategy = ref('auto')
const sensitivity = ref('public')
const error = ref('')
</script>
