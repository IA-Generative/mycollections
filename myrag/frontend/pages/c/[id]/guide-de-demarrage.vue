<script setup lang="ts">
/**
 * Le guide de démarrage d'une collection, à garder : ce qui a été fait, ce qui reste à faire, les
 * liens utiles en clair. Ouvert depuis l'étape 5 de l'assistant, ré-ouvrable depuis la fiche ; fait
 * pour l'impression (Ctrl+P → PDF) : l'habillage du site disparaît (`@media print`, assets/main.css).
 */
import { libelleSensibilite } from '~/utils/libelles'
import { sourceImportee } from '~/utils/fichiers'
import { resumeCreation } from '~/utils/wizard'

const route = useRoute()
const id = route.params.id as string
const { titre, retenir } = useTitreCollection(id, { charger: false })
const { get } = useApi()

const fiche = ref<any>(null)
const resume = ref<{ faits: string[], aFaire: string[] } | null>(null)
const origine = ref('')
const date = new Date().toLocaleDateString('fr-FR', { dateStyle: 'long' })

const base = computed(() => `${origine.value}/c/${encodeURIComponent(id)}`)
const liens = computed(() => [
  { libelle: 'La fiche de la collection', vers: base.value, aide: 'Tout part de là : poser une question, partager, régler.' },
  { libelle: 'Poser une question', vers: `${base.value}/playground`, aide: 'Le bac à sable : la collection répond, en citant ses passages.' },
  { libelle: sourceImportee(fiche.value) ? 'Gérer les documents' : 'Ajouter des documents', vers: `${base.value}/upload`, aide: sourceImportee(fiche.value) ? `Mettre à jour depuis ${sourceImportee(fiche.value) === 'fichiers' ? 'Fichiers' : 'Résana'}, changer les dossiers indexés.` : 'Déposer, remplacer ou retirer des documents.' },
  { libelle: 'Partager', vers: `${base.value}/publish`, aide: 'Choisir qui voit la collection dans le chat MirAI.' },
  { libelle: 'Qualité', vers: `${base.value}/qualite`, aide: 'Le jeu de questions, les réponses validées, la mesure.' },
])

onMounted(async () => {
  origine.value = window.location.origin
  try {
    fiche.value = await get(`/api/collections/${encodeURIComponent(id)}`)
    retenir(fiche.value)
  }
  catch { /* fiche illisible : le guide reste utile pour ses liens */ }
  const importee = sourceImportee(fiche.value)
  const resana = importee !== null
  const [docs, statut, qualite, publication] = await Promise.all([
    resana ? Promise.resolve(null) : get(`/api/collections/${encodeURIComponent(id)}/documents`, { par_page: '1' }).catch(() => null),
    resana ? get(`/api/sources/${importee}/status/${encodeURIComponent(id)}`).catch(() => null) : Promise.resolve(null),
    get(`/api/collections/${encodeURIComponent(id)}/qualite`).catch(() => null),
    get(`/api/collections/${encodeURIComponent(id)}/publication`).catch(() => null),
  ])
  resume.value = resumeCreation({
    titre: titre.value,
    documents: typeof docs?.total === 'number' ? docs.total : null,
    resana: statut ? { documents: statut.documents || 0, etat: statut.travail?.etat || null, total: statut.travail?.total || null } : null,
    questions: { total: qualite?.questions?.total || 0, validees: qualite?.questions?.par_relecture?.valide || 0 },
    sensibilite: libelleSensibilite(fiche.value?.sensitivity),
    groupes: publication?.state === 'published' ? publication.visibility_groups || [] : [],
  })
})

function imprimer () {
  window.print()
}
</script>

<template>
  <div class="guide">
    <FilAriane
      :collection="id"
      :titre="titre"
      rubrique="Guide de démarrage"
    />
    <div class="guide__tete">
      <h1 class="fr-h3 fr-mb-1v">
        Guide de démarrage — {{ titre }}
      </h1>
      <button
        type="button"
        class="fr-btn fr-btn--sm fr-btn--secondary fr-icon-printer-line fr-btn--icon-left no-print"
        @click="imprimer"
      >
        Imprimer ou enregistrer en PDF
      </button>
    </div>
    <p class="fr-text--sm guide__discret">
      Établi le {{ date }} · identifiant <code>{{ id }}</code>
    </p>

    <section
      v-if="resume"
      class="guide__section"
    >
      <h2 class="fr-h5">
        Ce qui a été fait
      </h2>
      <ul>
        <li
          v-for="(f, i) in resume.faits"
          :key="i"
        >
          {{ f }}
        </li>
      </ul>
    </section>

    <section
      v-if="resume"
      class="guide__section"
    >
      <h2 class="fr-h5">
        Ce qui reste à faire
      </h2>
      <ol>
        <li
          v-for="(a, i) in resume.aFaire"
          :key="i"
        >
          {{ a }}
        </li>
      </ol>
    </section>

    <section class="guide__section">
      <h2 class="fr-h5">
        Vos liens
      </h2>
      <ul class="guide__liens">
        <li
          v-for="l in liens"
          :key="l.vers"
        >
          <a
            :href="l.vers"
            class="fr-link"
          >{{ l.libelle }}</a>
          <span class="fr-text--sm guide__discret"> — {{ l.aide }}</span>
        </li>
      </ul>
    </section>

    <section class="guide__section">
      <h2 class="fr-h5">
        Comment vos collègues l'utilisent
      </h2>
      <p>
        Une fois partagée, la collection apparaît dans la liste des modèles du <strong>chat MirAI</strong>, pour les
        membres des groupes choisis. Ils la sélectionnent, posent leur question, et la réponse s'appuie sur vos
        documents, en les citant. Tant que la collection n'est pas publiée à tous, ses réponses portent la mention
        « en cours de vérification ».
      </p>
      <p class="fr-text--sm guide__discret">
        Les réponses que vous validez (page Qualité) servent de référence pour mesurer la qualité de la collection.
      </p>
    </section>
  </div>
</template>

<style scoped>
.guide__tete { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 1rem; }
.guide__section { margin-top: 1.5rem; break-inside: avoid; }
.guide__liens { list-style: none; padding: 0; }
.guide__liens li { margin-bottom: .5rem; }
.guide__discret { color: var(--text-mention-grey); }
@media print {
  .guide__section { margin-top: 1rem; }
  .guide__discret { color: #555; }
}
</style>
