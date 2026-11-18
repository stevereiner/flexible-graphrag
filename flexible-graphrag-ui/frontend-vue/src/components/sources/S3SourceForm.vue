<template>
  <BaseSourceForm
    title="Amazon S3"
    description="Connect to Amazon S3 buckets using bucket name and credentials"
  >
    <v-text-field
      v-model="bucketName"
      label="Bucket Name *"
      variant="outlined"
      class="mb-2"
      placeholder="my-bucket"
      hint="S3 bucket name (required)"
      persistent-hint
      required
      autocomplete="off"
    />
    
    <div class="d-flex ga-2 mb-2 align-start">
      <v-text-field
        v-model="prefix"
        label="Prefix/Path (Optional)"
        variant="outlined"
        placeholder="documents/reports/"
        hint="Optional: a folder prefix within the bucket (ending in /), or one object's key"
        persistent-hint
        autocomplete="off"
      />
      <v-btn
        variant="outlined"
        prepend-icon="mdi-folder-open"
        height="56"
        :disabled="!isValid"
        :title="isValid ? 'Pick a folder or a file in the bucket' : 'Fill in the bucket, region and keys first'"
        @click="browseOpen = true"
      >
        Browse…
      </v-btn>
    </div>
    <SourceBrowser
      :open="browseOpen"
      :provider="provider"
      :title="`Pick a folder or a file: s3://${bucketName}`"
      :multiple="false"
      @close="browseOpen = false"
      @select="handleBrowsed"
    />

    <v-text-field
      v-model="regionName"
      label="AWS Region *"
      variant="outlined"
      class="mb-2"
      placeholder="us-east-1"
      hint="AWS region where the bucket is located (e.g., us-east-1, us-east-2, eu-west-1)"
      persistent-hint
      required
      autocomplete="off"
    />
    
    <v-text-field
      v-model="sqsQueueUrl"
      label="SQS Queue URL (Optional)"
      type="url"
      name="sqs-endpoint-url"
      variant="outlined"
      class="mb-2"
      placeholder="https://sqs.us-east-2.amazonaws.com/123456789/my-queue"
      hint="Optional: SQS queue URL for real-time event-based sync (leave empty for periodic polling)"
      persistent-hint
      autocomplete="off"
      data-lpignore="true"
      data-form-type="other"
      data-1p-ignore="true"
    />
    
    <v-row class="mb-2">
      <v-col cols="6">
        <v-text-field
          :model-value="accessKey"
          @update:model-value="handleAccessKeyChange"
          label="Access Key *"
          variant="outlined"
          type="password"
          required
          autocomplete="new-password"
        />
      </v-col>
      <v-col cols="6">
        <v-text-field
          :model-value="secretKey"
          @update:model-value="handleSecretKeyChange"
          label="Secret Key *"
          variant="outlined"
          type="password"
          required
          autocomplete="new-password"
        />
      </v-col>
    </v-row>
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';
import SourceBrowser from '../../browser/SourceBrowser.vue';
import { remoteProvider } from '../../browser/remoteProvider';
import type { BrowseItem } from '../../browser/types';

export default defineComponent({
  name: 'S3SourceForm',
  components: {
    BaseSourceForm,
    SourceBrowser
  },
  props: {
    accessKey: {
      type: String,
      default: ''
    },
    secretKey: {
      type: String,
      default: ''
    }
  },
  emits: ['update:accessKey', 'update:secretKey', 'configuration-change', 'validation-change'],
  setup(props, { emit }) {
    const bucketName = ref('');
    const prefix = ref('');
    const regionName = ref('');  // starts empty; placeholder shows e.g. us-east-1
    const sqsQueueUrl = ref('');

    const isValid = computed(() => {
      return bucketName.value.trim() !== '' && 
             props.accessKey.trim() !== '' && 
             props.secretKey.trim() !== '' &&
             regionName.value.trim() !== '';
    });

    const config = computed(() => ({
      bucket_name: bucketName.value,
      prefix: prefix.value || undefined,
      access_key: props.accessKey,
      secret_key: props.secretKey,
      region_name: regionName.value,
      sqs_queue_url: sqsQueueUrl.value || undefined
    }));

    // Emit validation and configuration changes
    watch([isValid, config], ([newIsValid, newConfig]) => {
      emit('validation-change', newIsValid);
      emit('configuration-change', newConfig);
    }, { immediate: true });

    const handleAccessKeyChange = (value: string) => {
      emit('update:accessKey', value);
    };

    const handleSecretKeyChange = (value: string) => {
      emit('update:secretKey', value);
    };

    // Browse the bucket with the keys above (POST /api/browse)
    const browseOpen = ref(false);
    const provider = remoteProvider('s3', 'S3 bucket', () => config.value);

    // one folder ("docs/reports/") or one object's key: the prefix takes either
    const handleBrowsed = (items: BrowseItem[]) => {
      if (items.length) prefix.value = items[0].path || items[0].id;
    };

    return {
      isValid,
      browseOpen,
      provider,
      handleBrowsed,
      bucketName,
      prefix,
      regionName,
      sqsQueueUrl,
      handleAccessKeyChange,
      handleSecretKeyChange,
    };
  },
});
</script>
