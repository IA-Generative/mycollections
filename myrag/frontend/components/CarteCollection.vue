<template>
  <div style="border:1px solid var(--border-default-grey);border-radius:8px;padding:1.25rem;display:flex;flex-direction:column;height:100%;min-height:280px;">
    <h4 class="fr-h6 fr-mb-0" style="margin:0;line-height:1.3;">
      {{ titreDe(col) }}
    </h4>
    <p class="fr-text--xs fr-mb-1w" style="color:var(--text-mention-grey);">
      <code title="Identifiant technique : ce que tapent les applications (openrag-…)">{{ col.name }}</code>
    </p>
    <div style="display:flex;flex-wrap:wrap;gap:0.5rem;margin-bottom:0.75rem;">
      <span class="fr-badge fr-badge--sm" :class="stateBadge(col.publication?.state)">
        {{ stateLabel(col.publication?.state) }}
      </span>
      <span class="fr-badge fr-badge--sm" :class="sensitivityBadge(col.sensitivity)">
        {{ libelleSensibilite(col.sensitivity) }}
      </span>
      <span class="fr-badge fr-badge--sm fr-badge--info">{{ libelleStrategie(col.strategy) }}</span>
      <span v-if="col.graph_enabled" class="fr-badge fr-badge--sm fr-badge--new">liens entre documents</span>
      <span v-if="col.etat_collab && col.etat_collab !== 'publiee_tous'" class="fr-badge fr-badge--sm fr-badge--warning fr-badge--no-icon" title="Non publiée à tous : servie à son groupe seulement, réponses en cours de vérification.">
        {{ libelleEtat(col.etat_collab) }}
      </span>
      <span v-if="col.orphan" class="fr-badge fr-badge--sm fr-badge--warning" title="Présente dans le moteur de recherche, mais sans fiche dans Mes collections — ouvrez la collection pour la rattacher.">
        sans fiche
      </span>
    </div>

    <p class="fr-text--sm fr-mb-1w" style="color:var(--text-mention-grey);font-style:italic;" v-if="col.orphan">
      Collection présente dans le moteur de recherche, pas encore décrite dans Mes collections.
    </p>
    <p v-else class="fr-text--sm fr-mb-1w" style="color:var(--text-mention-grey);">
      {{ col.description || 'Pas de description' }}
    </p>
    <p v-if="col.file_count" class="fr-text--xs fr-mb-2w" style="color:var(--text-mention-grey);">
      📊 {{ col.file_count }} document{{ col.file_count > 1 ? 's' : '' }}
    </p>

    <p v-if="col.contact_name" class="fr-text--xs fr-mb-2w" style="color:var(--text-mention-grey);">
      📧 {{ col.contact_name }}
      <a v-if="col.contact_email" :href="`mailto:${col.contact_email}`" class="fr-link fr-text--xs">
        {{ col.contact_email }}
      </a>
    </p>

    <div style="margin-top:auto;display:flex;flex-direction:column;gap:0.5rem;">
      <NuxtLink :to="`/c/${col.name}/playground`"
                class="fr-btn fr-btn--icon-left fr-icon-chat-3-line"
                style="width:100%;justify-content:center;">
        Poser une question
      </NuxtLink>
      <p class="fr-text--xs fr-mb-0" style="color:var(--text-mention-grey);text-align:center;">
        La réponse, et les passages sur lesquels elle s'appuie
      </p>

      <NuxtLink :to="`/c/${col.name}`"
                class="fr-btn fr-btn--secondary fr-btn--sm fr-btn--icon-left fr-icon-eye-line"
                style="width:100%;justify-content:center;">
        Voir la collection
      </NuxtLink>

      <div style="display:flex;justify-content:flex-end;margin-top:0.25rem;">
        <NuxtLink :to="`/c/${col.name}/config`"
                  class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-btn--icon-left fr-icon-settings-5-line"
                  title="Titre, description, type de collection, sensibilité, portée, contact.">
          Réglages
        </NuxtLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/** Une collection au catalogue : son TITRE d'abord, l'identifiant technique en petit. */
import type { Collection } from '~/types/collection'
import { libelleEtat } from '~/utils/collectif'
import { titreDe } from '~/utils/catalogue'
import { libelleSensibilite, libelleStrategie } from '~/utils/libelles'

defineProps<{ col: Collection }>()

function stateBadge(state?: string) {
  return { draft: 'fr-badge--grey', published: 'fr-badge--success', disabled: 'fr-badge--warning' }[state || ''] || 'fr-badge--grey'
}
function stateLabel(state?: string) {
  return { draft: 'Brouillon', published: 'Publiée', disabled: 'Désactivée', archived: 'Archivée' }[state || ''] || 'Brouillon'
}
function sensitivityBadge(s?: string) {
  return { public: 'fr-badge--green-emeraude', internal: 'fr-badge--yellow-tournesol', restricted: 'fr-badge--orange-terre-battue', confidential: 'fr-badge--pink-macaron' }[s || ''] || ''
}
</script>
