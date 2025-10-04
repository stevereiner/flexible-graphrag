export const environment = {
  production: true,
  apiUrl: '/api', // API routing through nginx proxy
  defaultFolderPath: '/Shared/GraphRAG',
  cmisBaseUrl: 'http://host.docker.internal:8080', // Docker networking
  alfrescoBaseUrl: 'http://host.docker.internal:8080' // Docker networking
};
