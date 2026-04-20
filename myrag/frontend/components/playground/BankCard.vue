<template>
  <div class="myrag-bank-card" :class="tested ? 'myrag-bank-card--tested' : ''">
    <div class="myrag-bank-card__badge" :class="`myrag-bank-card__badge--${item.source}`">
      {{ badge }}
    </div>
    <p class="myrag-bank-card__question">{{ item.question }}</p>
    <p v-if="item.metadata?.reason" class="fr-text--xs myrag-bank-card__reason">
      Raison : {{ item.metadata.reason }}
    </p>
    <div class="myrag-bank-card__actions">
      <button class="fr-btn fr-btn--sm" :disabled="loading" @click="$emit('test')">
        {{ tested ? '↻ Re-tester' : '▶ Tester' }}
      </button>
      <button v-if="canRemove"
              class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-delete-line fr-btn--icon-left"
              :disabled="loading"
              :title="removeWarning"
              @click="onRemove">
        Retirer
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { BankItem } from '~/composables/useBank'

const props = defineProps<{
  item: BankItem
  tested?: boolean
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'test'): void
  (e: 'remove'): void
}>()

const badge = computed(() => {
  switch (props.item.source) {
    case 'generated': return '🤖 Generee'
    case 'imported':  return '📄 Importee'
    case 'fb_neg':    return '👎 Retour negatif'
    case 'promoted':  return '👍 Promue'
    default:          return props.item.source
  }
})

const canRemove = computed(() =>
  props.item.source === 'promoted'
  || props.item.source === 'generated'
  || props.item.source === 'imported',
)

const removeWarning = computed(() => {
  if (props.item.source === 'generated' || props.item.source === 'imported') {
    return 'Supprime tout le jeu de test (peut contenir d\'autres questions)'
  }
  return 'Retire du cache Q&R'
})

function onRemove() {
  if (props.item.source === 'generated' || props.item.source === 'imported') {
    if (!confirm(removeWarning.value + '. Continuer ?')) return
  }
  emit('remove')
}
</script>

<style scoped>
.myrag-bank-card {
  padding: 0.7rem 0.9rem;
  margin-bottom: 0.5rem;
  background: #fff;
  border: 1px solid #dddddd;
  border-radius: 4px;
  transition: border-color 0.15s;
}
.myrag-bank-card:hover { border-color: #000091; }
.myrag-bank-card--tested { border-left: 3px solid #000091; }
.myrag-bank-card__badge {
  font-size: 0.72rem;
  font-weight: 600;
  color: #666;
  margin-bottom: 0.3rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
.myrag-bank-card__badge--fb_neg   { color: #ce0500; }
.myrag-bank-card__badge--promoted { color: #18753c; }
.myrag-bank-card__badge--generated { color: #0063cb; }
.myrag-bank-card__badge--imported { color: #6a6af4; }
.myrag-bank-card__question {
  font-size: 0.88rem;
  line-height: 1.35;
  margin: 0 0 0.4rem 0;
  color: #161616;
}
.myrag-bank-card__reason { color: #666; margin: 0 0 0.4rem 0; }
.myrag-bank-card__actions {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}
</style>
