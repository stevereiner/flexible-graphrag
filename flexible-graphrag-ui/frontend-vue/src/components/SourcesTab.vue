<template>
  <div class="pa-4">
    <h2 class="mb-4">Data Source Configuration</h2>
    
    <!-- Data Source Selection -->
    <v-select
      v-model="dataSource"
      :items="dataSourceOptions"
      label="Data Source"
      variant="outlined"
      class="mb-4 data-source-select"
      :menu-props="{
        maxHeight: 'none',
        maxWidth: 400
      }"
      density="compact"
    ></v-select>

    <!-- Dynamic Source Forms -->
    <component
      :is="currentSourceComponent"
      v-if="currentSourceComponent"
      v-bind="currentSourceProps"
      @configuration-change="handleConfigurationChange"
      @validation-change="handleValidationChange"
    />

    <!-- Configure Processing Button -->
    <div class="d-flex align-center mt-4">
      <v-btn
        color="primary"
        size="large"
        :disabled="!isFormValid"
        @click="configureProcessing"
      >
        CONFIGURE PROCESSING →
      </v-btn>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import axios from 'axios';
import {
  FileUploadForm,
  AlfrescoSourceForm,
  CMISSourceForm,
  WebSourceForm,
  WikipediaSourceForm,
  YouTubeSourceForm,
  S3SourceForm,
  GCSSourceForm,
  AzureBlobSourceForm,
  OneDriveSourceForm,
  SharePointSourceForm,
  BoxSourceForm,
  GoogleDriveSourceForm,
} from './sources';

export default defineComponent({
  name: 'SourcesTab',
  emits: ['configure-processing', 'sources-configured'],
  setup(_, { emit }) {
    // Data source options - matching React order exactly
    const dataSourceOptions = [
      { title: 'File Upload', value: 'upload' },
      { title: 'Alfresco Repository', value: 'alfresco' },
      { title: 'CMIS Repository', value: 'cmis' },
      { title: '─── Web ───', value: '', disabled: true },
      { title: 'Web Page', value: 'web' },
      { title: 'Wikipedia', value: 'wikipedia' },
      { title: 'YouTube', value: 'youtube' },
      { title: '─── Cloud ───', value: '', disabled: true },
      { title: 'Google Drive', value: 'google_drive' },
      { title: 'Microsoft OneDrive', value: 'onedrive' },
      { title: 'Amazon S3', value: 's3' },
      { title: 'Azure Blob Storage', value: 'azure_blob' },
      { title: 'Google Cloud Storage', value: 'gcs' },
      { title: '─── Enterprise ───', value: '', disabled: true },
      { title: 'Box', value: 'box' },
      { title: 'SharePoint', value: 'sharepoint' },
    ];

    // State
    const dataSource = ref('upload');
    const folderPath = ref('/Shared/GraphRAG');
    const selectedFiles = ref<File[]>([]);
    const isFormValid = ref(false);
    const currentConfig = ref<any>({});

    // CMIS state
    const cmisUrl = ref(`${import.meta.env.VITE_CMIS_BASE_URL || 'http://localhost:8080'}/alfresco/api/-default-/public/cmis/versions/1.1/atom`);
    const cmisUsername = ref('admin');
    const cmisPassword = ref('admin');

    // Alfresco state
    const alfrescoUrl = ref(import.meta.env.VITE_ALFRESCO_BASE_URL || 'http://localhost:8080');
    const alfrescoUsername = ref('admin');
    const alfrescoPassword = ref('admin');

    // Web sources state
    const webUrl = ref('');
    const wikipediaUrl = ref('');
    const youtubeUrl = ref('');

    // Cloud storage state
    const s3AccessKey = ref('');
    const s3SecretKey = ref('');
    const gcsBucketName = ref('');
    const gcsCredentials = ref('');
    const azureBlobConnectionString = ref('');
    const azureBlobContainer = ref('');
    const azureBlobName = ref('');
    const azureBlobAccountName = ref('');
    const azureBlobAccountKey = ref('');

    // Enterprise state
    const onedriveUserPrincipalName = ref('');
    const onedriveClientId = ref('');
    const onedriveClientSecret = ref('');
    const onedriveTenantId = ref('');
    const sharepointSiteName = ref('');
    const sharepointClientId = ref('');
    const sharepointClientSecret = ref('');
    const sharepointTenantId = ref('');
    const boxClientId = ref('');
    const boxClientSecret = ref('');
    const boxDeveloperToken = ref('');
    const boxUserId = ref('');
    const boxEnterpriseId = ref('');
    const googleDriveCredentials = ref('');

    // Computed
    const currentSourceComponent = computed(() => {
      const componentMap: Record<string, any> = {
        upload: FileUploadForm,
        cmis: CMISSourceForm,
        alfresco: AlfrescoSourceForm,
        web: WebSourceForm,
        wikipedia: WikipediaSourceForm,
        youtube: YouTubeSourceForm,
        s3: S3SourceForm,
        gcs: GCSSourceForm,
        azure_blob: AzureBlobSourceForm,
        onedrive: OneDriveSourceForm,
        sharepoint: SharePointSourceForm,
        box: BoxSourceForm,
        google_drive: GoogleDriveSourceForm,
      };
      return componentMap[dataSource.value] || null;
    });

    const currentSourceProps = computed(() => {
      const baseProps = {};
      
      switch (dataSource.value) {
        case 'upload':
          return {
            ...baseProps,
            selectedFiles: selectedFiles.value,
            'onUpdate:selectedFiles': (files: File[]) => { selectedFiles.value = files; }
          };
        case 'cmis':
          return {
            ...baseProps,
            url: cmisUrl.value,
            username: cmisUsername.value,
            password: cmisPassword.value,
            folderPath: folderPath.value,
            'onUpdate:url': (value: string) => { cmisUrl.value = value; },
            'onUpdate:username': (value: string) => { cmisUsername.value = value; },
            'onUpdate:password': (value: string) => { cmisPassword.value = value; },
            'onUpdate:folderPath': (value: string) => { folderPath.value = value; }
          };
        case 'alfresco':
          return {
            ...baseProps,
            url: alfrescoUrl.value,
            username: alfrescoUsername.value,
            password: alfrescoPassword.value,
            path: folderPath.value,
            'onUpdate:url': (value: string) => { alfrescoUrl.value = value; },
            'onUpdate:username': (value: string) => { alfrescoUsername.value = value; },
            'onUpdate:password': (value: string) => { alfrescoPassword.value = value; },
            'onUpdate:path': (value: string) => { folderPath.value = value; }
          };
        case 'web':
          return {
            ...baseProps,
            url: webUrl.value,
            'onUpdate:url': (value: string) => { webUrl.value = value; }
          };
        case 'wikipedia':
          return {
            ...baseProps,
            url: wikipediaUrl.value,
            'onUpdate:url': (value: string) => { wikipediaUrl.value = value; }
          };
        case 'youtube':
          return {
            ...baseProps,
            url: youtubeUrl.value,
            'onUpdate:url': (value: string) => { youtubeUrl.value = value; }
          };
        case 's3':
          return {
            ...baseProps,
            accessKey: s3AccessKey.value,
            secretKey: s3SecretKey.value,
            'onUpdate:accessKey': (value: string) => { s3AccessKey.value = value; },
            'onUpdate:secretKey': (value: string) => { s3SecretKey.value = value; }
          };
        case 'gcs':
          return {
            ...baseProps,
            bucketName: gcsBucketName.value,
            credentials: gcsCredentials.value,
            'onUpdate:bucketName': (value: string) => { gcsBucketName.value = value; },
            'onUpdate:credentials': (value: string) => { gcsCredentials.value = value; }
          };
        case 'azure_blob':
          return {
            ...baseProps,
            connectionString: azureBlobConnectionString.value,
            containerName: azureBlobContainer.value,
            blobName: azureBlobName.value,
            accountName: azureBlobAccountName.value,
            accountKey: azureBlobAccountKey.value,
            'onUpdate:connectionString': (value: string) => { azureBlobConnectionString.value = value; },
            'onUpdate:containerName': (value: string) => { azureBlobContainer.value = value; },
            'onUpdate:blobName': (value: string) => { azureBlobName.value = value; },
            'onUpdate:accountName': (value: string) => { azureBlobAccountName.value = value; },
            'onUpdate:accountKey': (value: string) => { azureBlobAccountKey.value = value; }
          };
        case 'onedrive':
          return {
            ...baseProps,
            userPrincipalName: onedriveUserPrincipalName.value,
            clientId: onedriveClientId.value,
            clientSecret: onedriveClientSecret.value,
            tenantId: onedriveTenantId.value,
            'onUpdate:userPrincipalName': (value: string) => { onedriveUserPrincipalName.value = value; },
            'onUpdate:clientId': (value: string) => { onedriveClientId.value = value; },
            'onUpdate:clientSecret': (value: string) => { onedriveClientSecret.value = value; },
            'onUpdate:tenantId': (value: string) => { onedriveTenantId.value = value; }
          };
        case 'sharepoint':
          return {
            ...baseProps,
            siteName: sharepointSiteName.value,
            clientId: sharepointClientId.value,
            clientSecret: sharepointClientSecret.value,
            tenantId: sharepointTenantId.value,
            'onUpdate:siteName': (value: string) => { sharepointSiteName.value = value; },
            'onUpdate:clientId': (value: string) => { sharepointClientId.value = value; },
            'onUpdate:clientSecret': (value: string) => { sharepointClientSecret.value = value; },
            'onUpdate:tenantId': (value: string) => { sharepointTenantId.value = value; }
          };
        case 'box':
          return {
            ...baseProps,
            clientId: boxClientId.value,
            clientSecret: boxClientSecret.value,
            developerToken: boxDeveloperToken.value,
            userId: boxUserId.value,
            enterpriseId: boxEnterpriseId.value,
            'onUpdate:clientId': (value: string) => { boxClientId.value = value; },
            'onUpdate:clientSecret': (value: string) => { boxClientSecret.value = value; },
            'onUpdate:developerToken': (value: string) => { boxDeveloperToken.value = value; },
            'onUpdate:userId': (value: string) => { boxUserId.value = value; },
            'onUpdate:enterpriseId': (value: string) => { boxEnterpriseId.value = value; }
          };
        case 'google_drive':
          return {
            ...baseProps,
            credentials: googleDriveCredentials.value,
            'onUpdate:credentials': (value: string) => { googleDriveCredentials.value = value; }
          };
        default:
          return baseProps;
      }
    });

    // Methods
    const handleConfigurationChange = (config: any) => {
      currentConfig.value = config;
    };

    const handleValidationChange = (valid: boolean) => {
      isFormValid.value = valid;
    };

    const configureProcessing = () => {
      // Build configuration object based on data source
      const sourceConfig: any = {
        dataSource: dataSource.value,
        files: selectedFiles.value,
        folderPath: folderPath.value,
      };

      // Add source-specific configurations
      switch (dataSource.value) {
        case 'cmis':
          sourceConfig.cmisConfig = currentConfig.value;
          break;
        case 'alfresco':
          sourceConfig.alfrescoConfig = currentConfig.value;
          break;
        case 'web':
          sourceConfig.webConfig = currentConfig.value;
          break;
        case 'wikipedia':
          sourceConfig.wikipediaConfig = currentConfig.value;
          break;
        case 'youtube':
          sourceConfig.youtubeConfig = currentConfig.value;
          break;
        case 's3':
        case 'gcs':
        case 'azure_blob':
          sourceConfig.cloudConfig = currentConfig.value;
          break;
        case 'onedrive':
        case 'sharepoint':
        case 'box':
        case 'google_drive':
          sourceConfig.enterpriseConfig = currentConfig.value;
          break;
      }

      emit('sources-configured', sourceConfig);
      emit('configure-processing');
    };

    // Clear state when data source changes
    watch(dataSource, () => {
      selectedFiles.value = [];
      currentConfig.value = {};
      isFormValid.value = false;
    });

    return {
      dataSourceOptions,
      dataSource,
      currentSourceComponent,
      currentSourceProps,
      isFormValid,
      handleConfigurationChange,
      handleValidationChange,
      configureProcessing,
    };
  },
});
</script>

<style scoped>
.cursor-pointer {
  cursor: pointer;
}

/* CSS hover styles removed - now handled by computed dropZoneStyle */

.drag-normal {
  background-color: #1976d2 !important;
}

/* Data source dropdown styling */
.data-source-select {
  max-width: 400px;
}

/* Ultra-specific Vuetify 3 selectors to force compact spacing */
.data-source-select :deep(.v-overlay__content .v-list) {
  padding: 2px 0 !important;
}

.data-source-select :deep(.v-overlay__content .v-list .v-list-item) {
  min-height: 28px !important;
  max-height: 28px !important;
  height: 28px !important;
  padding: 2px 16px !important;
  margin: 0 !important;
  font-size: 13px !important;
  line-height: 24px !important;
}

.data-source-select :deep(.v-overlay__content .v-list .v-list-item .v-list-item__content) {
  padding: 0 !important;
  margin: 0 !important;
  min-height: 28px !important;
  height: 28px !important;
}

.data-source-select :deep(.v-overlay__content .v-list .v-list-item .v-list-item-title) {
  font-size: 13px !important;
  line-height: 24px !important;
  padding: 0 !important;
  margin: 0 !important;
}

/* Target the actual rendered elements with highest specificity */
.data-source-select :deep(.v-overlay__content .v-list .v-list-item--disabled) {
  min-height: 28px !important;
  max-height: 28px !important;
  height: 28px !important;
  padding: 2px 16px !important;
  margin: 0 !important;
  opacity: 0.6 !important;
  font-size: 13px !important;
  line-height: 24px !important;
}

/* Force override any default Vuetify spacing */
.data-source-select :deep(.v-overlay__content .v-list .v-list-item__overlay) {
  display: none !important;
}

.data-source-select :deep(.v-overlay__content .v-list .v-list-item__underlay) {
  display: none !important;
}

/* Global override for this specific dropdown menu */
:global(.v-overlay .v-menu .v-list .v-list-item) {
  min-height: 28px !important;
  max-height: 28px !important;
  height: 28px !important;
  padding: 2px 16px !important;
  margin: 0 !important;
  font-size: 13px !important;
  line-height: 24px !important;
}
</style>
