# Data Source Configuration Guide

This document provides detailed setup instructions for cloud storage and enterprise data sources in Flexible GraphRAG.

---

## Table of Contents

1. [Microsoft OneDrive](#microsoft-onedrive)
2. [Microsoft SharePoint](#microsoft-sharepoint)
3. [Box](#box)
4. [Source Path Examples](#source-path-examples)

---

## Microsoft OneDrive

OneDrive for Business is built on SharePoint, so you'll be working with Microsoft Entra ID (formerly Azure Active Directory) and Microsoft Graph API.

### Prerequisites

- Microsoft 365 account with OneDrive
- Access to Azure Portal (portal.azure.com)
- Admin permissions to register applications

### Step 1: Register Application in Microsoft Entra ID

1. Go to **Azure Portal** (portal.azure.com)
2. Navigate to **Microsoft Entra ID** → **App registrations** → **New registration**
3. Fill in:
   - **Name**: `Flexible-GraphRAG-OneDrive` (or any name)
   - **Supported account types**: `Accounts in this organizational directory only (Single tenant)`
   - **Redirect URI**: Leave blank
4. Click **Register**

### Step 2: Get Application Credentials

After registration, on the **Overview** page:
- Copy **Application (client) ID** - this is your `client_id`
- Copy **Directory (tenant) ID** - this is your `tenant_id`

Then create a client secret:
1. Go to **Certificates & secrets** → **Client secrets** → **New client secret**
2. Add a description (e.g., "GraphRAG Access")
3. Choose expiration (e.g., 24 months)
4. Click **Add**
5. **Copy the secret VALUE immediately** - this is your `client_secret` (you can't see it again!)

### Step 3: Grant API Permissions

1. Go to **API permissions** → **Add a permission**
2. Select **Microsoft Graph** → **Application permissions**
3. Add these permissions:
   - `Files.Read.All` (to read OneDrive files)
   - `Sites.Read.All` (for SharePoint integration)
4. Click **Grant admin consent for [Your Tenant]** ✅ (required!)

After granting, all permissions should show green checkmarks.

### Step 4: Get User Principal Name

Your `user_principal_name` is your M365 email address:
- Format: `admin@yourtenantname.onmicrosoft.com`
- Find it: Azure Portal → **Microsoft Entra ID** → **Users** → your user

### Step 5: Determine OneDrive Folder Path

OneDrive paths are relative to the user's OneDrive root:
- Root folder: `/` or leave blank
- Specific folder: `/test` or `/Documents/Reports`
- **Note**: The UI shows "My files" but the API path is still relative to root

To find the correct path:
1. Go to OneDrive in browser
2. Navigate to desired folder
3. Look at URL: `https://tenant-my.sharepoint.com/personal/user/Documents/FolderName`
4. Extract path: If folder is at root level use `/FolderName`, if in Documents use `/Documents/FolderName`

**Important**: Even though the OneDrive UI may show "My files", use the actual folder path from the URL structure.

### Configuration Example

```bash
ONEDRIVE_CONFIG={"user_principal_name": "admin@tenant.onmicrosoft.com", "client_id": "12345678-1234-1234-1234-123456789abc", "client_secret": "XFA8Q~abc123...", "tenant_id": "87654321-4321-4321-4321-cba987654321", "folder_path": "/Documents"}
```

---

## Microsoft SharePoint

SharePoint configuration is similar to OneDrive, as both use Microsoft Graph API.

### Prerequisites

Same as OneDrive - you can use the same Azure app registration for both.

### Configuration Notes

- **site_name**: The SharePoint site name (not full URL)
  - Example: If your site is `https://tenant.sharepoint.com/sites/MySite`, use `site_name: "MySite"`
- **folder_path**: Relative path within the site (e.g., `/Shared Documents/Reports`)
- **site_id**: Optional, only needed for Sites.Selected permission scope

### Configuration Example

```bash
SHAREPOINT_CONFIG={"client_id": "12345678-1234-1234-1234-123456789abc", "client_secret": "XFA8Q~abc123...", "tenant_id": "87654321-4321-4321-4321-cba987654321", "site_name": "MySite", "folder_path": "/Shared Documents"}
```

---

## Box

Box supports two authentication methods: **Developer Token** (quick testing) and **Client Credentials Grant** (production).

### Method 1: Developer Token (Simplest - for Testing)

**Best for**: Quick testing, proof of concept  
**Limitation**: Expires in 60 minutes

#### Setup Steps

1. Go to **Box Developer Console** (https://app.box.com/developers/console)
2. Create or select your application
3. Go to **Configuration** → **Developer Token**
4. Click **Generate Developer Token**
5. Copy the token (valid for 60 minutes)

#### Configuration

```bash
BOX_CONFIG={"folder_id": "0", "developer_token": "your_developer_token_here"}
```

- **folder_id**: `"0"` for root folder, or specific folder ID
- **developer_token**: The token you generated

---

### Method 2: Client Credentials Grant (CCG - Production)

**Best for**: Production deployments, long-lived credentials  
**Requires**: Box app with CCG enabled

#### Setup Steps

1. Go to **Box Developer Console** → your app → **Configuration**
2. **Authentication Method**: Select **OAuth 2.0 with Client Credentials Grant**
3. **Application Access**: Choose appropriate level:
   - **App Access Only**: Non-enterprise users
   - **App + Enterprise Access**: Enterprise-wide access
4. **Application Scopes**: Enable required permissions (e.g., "Read all files")
5. **Submit for Authorization** (requires Box admin approval)

#### Get Required IDs

- **client_id** and **client_secret**: From **Configuration** → **OAuth 2.0 Credentials**
- **user_id**: Box user ID (found in user profile or admin console)
- **enterprise_id**: Box enterprise ID (found in admin console → **Account Info**)
- **folder_id**: Get from Box folder URL or API

#### Configuration Options

**a) Non-enterprise user account:**
```bash
BOX_CONFIG={"folder_id": "0", "client_id": "abc123", "client_secret": "xyz789", "user_id": "12345678"}
```

**b) Enterprise-wide access:**
```bash
BOX_CONFIG={"folder_id": "0", "client_id": "abc123", "client_secret": "xyz789", "enterprise_id": "987654321"}
```

**c) Enterprise + specific user:**
```bash
BOX_CONFIG={"folder_id": "0", "client_id": "abc123", "client_secret": "xyz789", "enterprise_id": "987654321", "user_id": "12345678"}
```

**Required**: client_id, client_secret, AND at least one of (user_id OR enterprise_id)

---

## Source Path Examples

### Windows Paths

**Single file:**
```bash
SOURCE_PATHS=["C:\\Documents\\report.pdf"]
```

**Multiple files:**
```bash
SOURCE_PATHS=["C:\\file1.pdf", "D:\\folder\\file2.docx"]
```

**Whole directory:**
```bash
SOURCE_PATHS=["C:\\Documents\\reports"]
# Note: Processes ALL files in directory
```

### macOS Paths

**Single file:**
```bash
SOURCE_PATHS=["/Users/username/Documents/report.pdf"]
```

**Directory:**
```bash
SOURCE_PATHS=["/Users/username/Documents/reports"]
```

### Linux Paths

**Single file:**
```bash
SOURCE_PATHS=["/home/username/documents/report.pdf"]
```

**Directory:**
```bash
SOURCE_PATHS=["/home/username/documents/reports"]
```

### Path Notes

- **Filesystem source**: Use `SOURCE_PATHS` for backend configuration
- **UI clients**: Use different environment variables:
  - `PROCESS_FOLDER_PATH` (backend UI config)
  - `VITE_PROCESS_FOLDER_PATH` (frontend UI config)
- **Directory processing**: When you specify a directory, ALL files in it will be processed
- **Backslashes**: Windows paths require escaped backslashes (`\\`) in config files

For more examples, see also: `docs/SOURCE-PATH-EXAMPLES.md`

---

## Additional Resources

- **Microsoft Graph API Documentation**: https://learn.microsoft.com/en-us/graph/
- **Box Developer Documentation**: https://developer.box.com/
- **Troubleshooting**: See main README.md for common issues and solutions

