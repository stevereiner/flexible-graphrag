# CMIS Integration Guide

This guide covers CMIS-specific configuration and requirements for the Flexible GraphRAG system.

## About CMIS

[CMIS (Content Management Interoperability Services)](https://en.wikipedia.org/wiki/Content_Management_Interoperability_Services) is a standard that allows different content management systems to inter-operate over the Internet.

For more information: [Libraries Supporting KG building and GraphRAG](https://github.com/stevereiner/cmis-graphrag/blob/main/Libraries%20Supporting%20KG%20building%20and%20GraphRAG.md)

## CMIS Repository Requirements

Your CMIS server needs to support CMIS 1.0 or CMIS 1.1:

- **Alfresco** (CMIS 1.1)
- **Nuxeo** (CMIS 1.1)  
- **OpenText Documentum, OpenText Content Management, OpenText eDocs** (CMIS 1.1)
- **SAP Hana, SAP Extended ECM, SAP Mobile** (CMIS 1.1)
- **IBM FileNet Content Manager, IBM Content Manager** (full CMIS 1.0, partial CMIS 1.1)
- **Microsoft SharePoint Server** (CMIS 1.0, on premises only)

## CMIS Configuration

Add these settings to your `.env` file:

```env
# CMIS Configuration
CMIS_URL=http://your-cmis-server/alfresco/api/-default-/public/cmis/versions/1.1/atom
CMIS_USERNAME=your-username
CMIS_PASSWORD=your-password
```

## CMIS API Endpoints

### Document Processing
- `POST /api/process-folder` - Process documents from a CMIS folder
  ```json
  {
    "folder_path": "/Shared/GraphRAG"
  }
  ```

### Legacy CMIS Usage

For legacy CMIS-specific implementations, the system provides backward compatibility with the original CMIS-focused endpoints.

## CMIS Library Information

- **Package**: cmislib 0.7.0
- **PyPI**: [cmislib 0.7.0](https://pypi.org/project/cmislib/)
- **Summary**: Apache Chemistry CMIS client library for Python
- **Info**: [Apache Chemistry](http://chemistry.apache.org/)
- **Note**: cmislib 0.7.0 supports Python 3.x (previous versions were Python 2.x only)

## File Structure (CMIS-specific)

- `cmis_util.py` - CMIS repository interaction utilities
- `sources.py` - Includes CMIS data source connector

## Notes

- The system maintains compatibility with existing CMIS workflows
- CMIS integration is optional - the system can work with filesystem and Alfresco sources
- For CMIS-specific deployments, ensure your repository supports the required CMIS version