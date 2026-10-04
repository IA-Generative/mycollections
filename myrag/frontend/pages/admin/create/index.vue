<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin">Administration</NuxtLink></li>
        <li><a class="fr-breadcrumb__link" aria-current="page">Créer une collection</a></li>
      </ol>
    </nav>

    <h1 class="fr-h3">Créer une collection</h1>
    <p class="fr-text--lg fr-mb-2w">Étape 1 sur 5 — D'où viennent vos documents ?</p>

    <div class="fr-callout fr-mb-4w">
      <p class="fr-callout__text">
        Avant de creer une collection, consultez le
        <NuxtLink to="/admin/catalog" class="fr-link">catalogue des collections existantes</NuxtLink>
        pour eviter les doublons et contribuer aux efforts en cours.
      </p>
    </div>

    <WizardStepper :current-step="1" />

    <div class="myrag-card-grid">
      <div v-for="src in sources" :key="src.key"
           :class="['fr-card', {
             'fr-card--shadow': selected === src.key,
             'fr-enlarge-link': !src.soon,
           }]"
           :role="src.soon ? undefined : 'button'"
           :tabindex="src.soon ? -1 : 0"
           :aria-pressed="src.soon ? undefined : selected === src.key"
           :aria-disabled="src.soon ? 'true' : undefined"
           @click="!src.soon && (selected = src.key)"
           @keydown.enter.prevent="!src.soon && (selected = src.key)"
           @keydown.space.prevent="!src.soon && (selected = src.key)"
           :style="src.soon ? 'opacity:0.5;cursor:not-allowed;' : 'cursor:pointer;'">
        <div class="fr-card__body">
          <div class="fr-card__content">
            <h3 class="fr-card__title">
              <span>{{ src.icon }} {{ src.name }}</span>
            </h3>
            <p class="fr-card__desc">{{ src.description }}</p>
            <div class="fr-card__start">
              <span v-if="src.soon" class="fr-badge fr-badge--sm fr-badge--grey">Bientôt disponible</span>
              <span v-if="src.refresh && !src.soon" class="fr-badge fr-badge--sm fr-badge--new">Refresh auto</span>
              <span v-if="!src.soon" class="fr-badge fr-badge--sm fr-badge--info">{{ src.strategy }}</span>
            </div>
          </div>
        </div>
        <div v-if="selected === src.key && !src.soon" class="fr-card__header" style="background:#000091;padding:4px;text-align:center;">
          <span style="color:white;font-size:0.8rem;font-weight:bold;">✓ Sélectionnée</span>
        </div>
      </div>
    </div>

    <div class="fr-btns-group fr-btns-group--right fr-mt-4w">
      <button class="fr-btn" @click="next" :disabled="!selected">
        Suivant →
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
const router = useRouter()
const selected = ref('')

const sources = [
  {
    key: 'legifrance',
    icon: '⚖️',
    name: 'Légifrance',
    description: 'Code, loi, ordonnance depuis l\'API PISTE, découpés par article.',
    refresh: true,
    strategy: 'article',
    prompt_template: 'juridique',
    soon: true,
  },
  {
    key: 'file',
    icon: '📄',
    name: 'Fichier unique',
    description: 'Un fichier texte ou Markdown (.txt, .md, .csv). Les PDF et documents Word ne sont pas encore lus : enregistrez-les d\'abord au format texte.',
    refresh: false,
    strategy: 'auto',
    prompt_template: 'generic',
  },
  {
    key: 'directory',
    icon: '📁',
    name: 'Répertoire local',
    description: 'Un dossier ou un ZIP de plusieurs fichiers, indexés ensemble.',
    refresh: false,
    strategy: 'auto',
    prompt_template: 'multi_thematique',
    soon: true,
  },
  {
    key: 'drive',
    icon: '☁️',
    name: 'Suite Numérique Drive',
    description: 'Un dossier de Drive (Suite Numérique), resynchronisé quand il change.',
    refresh: true,
    strategy: 'auto',
    prompt_template: 'multi_thematique',
  },
  {
    key: 'nextcloud',
    icon: '📦',
    name: 'Nextcloud',
    description: 'Un dossier Nextcloud, resynchronisé quand il change.',
    refresh: true,
    strategy: 'auto',
    prompt_template: 'multi_thematique',
    soon: true,
  },
  {
    key: 'resana',
    icon: '🗂️',
    name: 'Resana',
    description: 'Connecter un espace Resana. Synchronisation automatique des documents.',
    refresh: true,
    strategy: 'auto',
    prompt_template: 'multi_thematique',
    soon: true,
  },
  {
    key: 'website',
    icon: '🌐',
    name: 'Indexation de site',
    description: 'Crawler un site web ou un intranet pour indexer ses pages. Suivi des modifications.',
    refresh: true,
    strategy: 'section',
    prompt_template: 'multi_thematique',
    soon: true,
  },
]

function next() {
  router.push(`/admin/create/step-2?source=${selected.value}`)
}
</script>
