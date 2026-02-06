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
    
    <v-text-field
      v-model="prefix"
      label="Prefix/Path (Optional)"
      variant="outlined"
      class="mb-2"
      placeholder="documents/reports/"
      hint="Optional: folder path prefix within bucket"
      persistent-hint
      autocomplete="off"
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
      autocomplete="url"
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
          autocomplete="off"
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
          autocomplete="off"
        />
      </v-col>
    </v-row>
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';

export default defineComponent({
  name: 'S3SourceForm',
  components: {
    BaseSourceForm
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
    const regionName = ref('us-east-1');
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

    return {
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
