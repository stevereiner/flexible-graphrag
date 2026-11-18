<template>
  <BaseSourceForm
    title="Google Cloud Storage"
    description="Connect to Google Cloud Storage buckets"
  >
    <v-text-field
      :model-value="bucketName"
      @update:model-value="handleBucketNameChange"
      label="Bucket Name *"
      variant="outlined"
      class="mb-2"
      placeholder="my-gcs-bucket"
      hint="GCS bucket name (required)"
      persistent-hint
      required
    />
    
    <div class="d-flex ga-2 mb-2 align-start">
      <v-text-field
        :model-value="localPrefix"
        @update:model-value="handlePrefixChange"
        label="Prefix (Optional)"
        variant="outlined"
        placeholder="sample-docs/"
        hint="Optional: folder path prefix (e.g., 'sample-docs/' for a specific folder)"
        persistent-hint
      />
      <v-btn
        variant="outlined"
        prepend-icon="mdi-folder-open"
        height="56"
        :disabled="!isValid"
        :title="isValid ? 'Pick a folder in the bucket' : 'Fill in the bucket and the credentials first'"
        @click="browseOpen = true"
      >
        Browse…
      </v-btn>
    </div>
    <SourceBrowser
      :open="browseOpen"
      :provider="provider"
      :title="`Pick a folder: gs://${bucketName}`"
      :files="false"
      :multiple="false"
      @close="browseOpen = false"
      @select="handleBrowsed"
    />

    <v-textarea
      :model-value="credentials"
      @update:model-value="handleCredentialsChange"
      label="Service Account Credentials (JSON) *"
      variant="outlined"
      class="mb-2"
      placeholder='{"type": "service_account", "project_id": "...", ...}'
      hint="JSON service account key (includes project_id)"
      persistent-hint
      rows="4"
      required
    />
    
    <v-text-field
      :model-value="localPubsubSubscription"
      @update:model-value="handlePubsubSubscriptionChange"
      label="Pub/Sub Subscription (Optional)"
      variant="outlined"
      class="mb-2"
      placeholder="gcs-notifications-sub"
      hint="Pub/Sub subscription name for real-time change detection (leave empty for periodic polling)"
      persistent-hint
    />
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';
import SourceBrowser from '../../browser/SourceBrowser.vue';
import { remoteProvider } from '../../browser/remoteProvider';
import type { BrowseItem } from '../../browser/types';

export default defineComponent({
  name: 'GCSSourceForm',
  components: {
    BaseSourceForm,
    SourceBrowser
  },
  props: {
    bucketName: {
      type: String,
      default: ''
    },
    credentials: {
      type: String,
      default: ''
    },
    prefix: {
      type: String,
      default: ''
    },
    pubsubSubscription: {
      type: String,
      default: ''
    }
  },
  emits: [
    'update:bucketName', 'update:credentials', 
    'update:prefix', 'update:pubsubSubscription',
    'configuration-change', 'validation-change'
  ],
  setup(props, { emit }) {
    const localPrefix = ref(props.prefix);
    const localPubsubSubscription = ref(props.pubsubSubscription);

    // Sync local state with props
    watch(() => props.prefix, (newVal) => {
      localPrefix.value = newVal;
    });

    watch(() => props.pubsubSubscription, (newVal) => {
      localPubsubSubscription.value = newVal;
    });

    const isValid = computed(() => {
      return props.bucketName.trim() !== '' && 
             props.credentials.trim() !== '';
    });

    const config = computed(() => ({
      bucket_name: props.bucketName,
      credentials: props.credentials,
      prefix: localPrefix.value || undefined,
      pubsub_subscription: localPubsubSubscription.value || undefined
    }));

    // Emit validation and configuration changes
    watch([isValid, config], ([newIsValid, newConfig]) => {
      emit('validation-change', newIsValid);
      emit('configuration-change', newConfig);
    }, { immediate: true });

    const handleBucketNameChange = (value: string) => {
      emit('update:bucketName', value);
    };

    const handleCredentialsChange = (value: string) => {
      emit('update:credentials', value);
    };

    const handlePrefixChange = (value: string) => {
      localPrefix.value = value;
      emit('update:prefix', value);
    };

    const handlePubsubSubscriptionChange = (value: string) => {
      localPubsubSubscription.value = value;
      emit('update:pubsubSubscription', value);
    };

    // Browse the bucket with the credentials below (POST /api/browse)
    const browseOpen = ref(false);
    const provider = remoteProvider('gcs', 'GCS bucket', () => config.value);

    // a folder's prefix ("docs/2024/"): the ingest reads a prefix as a folder
    const handleBrowsed = (items: BrowseItem[]) => {
      if (items.length) handlePrefixChange(items[0].path || items[0].id);
    };

    return {
      isValid,
      browseOpen,
      provider,
      handleBrowsed,
      localPrefix,
      localPubsubSubscription,
      handleBucketNameChange,
      handleCredentialsChange,
      handlePrefixChange,
      handlePubsubSubscriptionChange,
    };
  },
});
</script>
