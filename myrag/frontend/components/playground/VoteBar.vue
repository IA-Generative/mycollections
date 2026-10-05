<template>
  <div class="myrag-vote">
    <span class="myrag-vote__label">Cette réponse est-elle utile ?</span>
    <button class="fr-btn fr-btn--sm fr-btn--tertiary"
            :class="vote === 'up' ? 'myrag-vote__btn--active-up' : ''"
            :disabled="disabled"
            @click="onVote('up')"
            title="Bonne réponse — l'ajouter aux réponses validées"
            aria-label="Bonne réponse : l'ajouter aux réponses validées de la collection">
      👍
    </button>
    <button class="fr-btn fr-btn--sm fr-btn--tertiary"
            :class="vote === 'down' ? 'myrag-vote__btn--active-down' : ''"
            :disabled="disabled"
            @click="onVote('down')"
            title="Mauvaise réponse — enregistrer un avis à relire"
            aria-label="Mauvaise réponse : la signaler au gestionnaire de la collection">
      👎
    </button>
    <span v-if="!vote" class="myrag-vote__aide">
      <template v-if="gestionnaire">👍 la garde comme réponse validée · 👎 la signale au gestionnaire, qui la relira</template>
      <template v-else>👍 et 👎 sont transmis au gestionnaire de la collection, qui les relira</template>
    </span>
    <span v-if="vote" class="myrag-vote__status">
      {{ vote === 'up' && gestionnaire ? 'Ajoutée aux réponses validées.' : 'Avis transmis, merci.' }}
    </span>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  disabled?: boolean
  gestionnaire?: boolean
  vote?: 'up' | 'down' | null
}>()

const emit = defineEmits<{
  (e: 'vote', value: 'up' | 'down'): void
}>()

function onVote(v: 'up' | 'down') {
  if (props.disabled || props.vote) return
  emit('vote', v)
}
</script>

<style scoped>
.myrag-vote {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.6rem;
  flex-wrap: wrap;
}
.myrag-vote__label {
  font-size: 0.8rem;
  color: #666;
}
.myrag-vote__btn--active-up { background: #b8fec9; }
.myrag-vote__btn--active-down { background: #ffe9e9; }
.myrag-vote__status { font-size: 0.8rem; color: #18753c; }
.myrag-vote__aide { font-size: 0.75rem; color: var(--text-mention-grey); }
</style>
