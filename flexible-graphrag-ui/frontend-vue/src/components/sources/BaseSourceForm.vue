<template>
  <div class="base-source-form">
    <h3 class="mb-2">{{ title }}</h3>
    <p v-if="description" class="text-medium-emphasis mb-4">{{ description }}</p>
    <slot></slot>
  </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue';

export default defineComponent({
  name: 'BaseSourceForm',
  props: {
    title: {
      type: String,
      required: true
    },
    description: {
      type: String,
      default: ''
    }
  }
});
</script>

<style scoped>
.base-source-form {
  /* Base styling for all source forms */
}
</style>
