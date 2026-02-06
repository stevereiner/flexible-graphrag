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
    
    <v-text-field
      :model-value="localPrefix"
      @update:model-value="handlePrefixChange"
      label="Prefix (Optional)"
      variant="outlined"
      class="mb-2"
      placeholder="sample-docs/"
      hint="Optional: folder path prefix (e.g., 'sample-docs/' for a specific folder)"
      persistent-hint
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

export default defineComponent({
  name: 'GCSSourceForm',
  components: {
    BaseSourceForm
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

    return {
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
