<template>
  <div class="myrag-bank-filter" role="tablist">
    <button v-for="f in filters" :key="f.key"
            class="myrag-bank-filter__tab"
            :class="modelValue === f.key ? 'myrag-bank-filter__tab--active' : ''"
            :disabled="f.count === 0 && f.key !== 'all'"
            @click="$emit('update:modelValue', f.key)">
      {{ f.label }}
      <span v-if="f.count !== null" class="myrag-bank-filter__count">{{ f.count }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import type { BankSource, BankStats } from '~/composables/useBank'

const props = defineProps<{
  modelValue: BankSource | 'all'
  stats: BankStats
}>()

defineEmits<{
  (e: 'update:modelValue', v: BankSource | 'all'): void
}>()

const filters = computed(() => [
  { key: 'all' as const,       label: 'Toutes',   count: props.stats.total },
  { key: 'fb_neg' as const,    label: '👎',        count: props.stats.fb_neg },
  { key: 'promoted' as const,  label: '👍',        count: props.stats.promoted },
  { key: 'generated' as const, label: '🤖',        count: props.stats.generated },
  { key: 'imported' as const,  label: '📄',        count: props.stats.imported },
])
</script>

<style scoped>
.myrag-bank-filter {
  display: flex;
  gap: 0.2rem;
  margin-bottom: 0.8rem;
  flex-wrap: wrap;
}
.myrag-bank-filter__tab {
  border: 1px solid #dddddd;
  background: #fff;
  padding: 0.3rem 0.6rem;
  border-radius: 3px;
  font-size: 0.82rem;
  cursor: pointer;
  color: #3a3a3a;
  white-space: nowrap;
}
.myrag-bank-filter__tab:disabled {
  color: #999;
  cursor: not-allowed;
}
.myrag-bank-filter__tab:hover:not(:disabled) { background: #f6f6f6; }
.myrag-bank-filter__tab--active {
  background: #000091;
  color: #fff;
  border-color: #000091;
}
.myrag-bank-filter__count {
  display: inline-block;
  margin-left: 0.3rem;
  padding: 0 0.35rem;
  font-size: 0.72rem;
  background: rgba(0, 0, 0, 0.08);
  border-radius: 8px;
}
.myrag-bank-filter__tab--active .myrag-bank-filter__count {
  background: rgba(255, 255, 255, 0.25);
}
</style>
