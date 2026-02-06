# Google Cloud Storage (GCS) Setup Guide

This guide shows you how to configure Google Cloud Storage as a data source for Flexible GraphRAG, with optional real-time Pub/Sub integration.

---

## Part 1: Google Cloud Setup

### 1.1 Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown at the top
3. Click **"New Project"**
4. Enter a project name (e.g., "my-graphrag-project")
5. Click **"Create"**
6. Note your **Project ID** (e.g., `my-project-123456`)

### 1.2 Enable Required APIs

1. In the Google Cloud Console, go to **APIs & Services** → **Library**
2. Search for and enable these APIs:
   - **Cloud Storage API**
   - **Pub/Sub API** (only needed for real-time updates)

### 1.3 Create a Service Account

1. Go to **IAM & Admin** → **Service Accounts**
2. Click **"+ CREATE SERVICE ACCOUNT"**
3. Enter:
   - **Service account name**: `graphrag-service-account`
   - **Description**: "Service account for Flexible GraphRAG"
4. Click **"Create and Continue"**
5. **Grant roles**:
   - **Storage Object Viewer** (required - to read files from GCS)
   - **Pub/Sub Subscriber** (optional - for real-time updates)
   - **Pub/Sub Viewer** (optional - for cleaner logs)
6. Click **"Continue"**, then **"Done"**

### 1.4 Create Service Account Key (JSON)

1. In **IAM & Admin** → **Service Accounts**
2. Click on your service account (`graphrag-service-account`)
3. Go to **Keys** tab
4. Click **"Add Key"** → **"Create new key"**
5. Select **JSON** format
6. Click **"Create"** - the JSON file will download
7. **Keep this file secure** - it contains your credentials

The JSON file looks like this:
```json
{
  "type": "service_account",
  "project_id": "my-project-123456",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "client_email": "graphrag-service-account@my-project-123456.iam.gserviceaccount.com",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  ...
}
```

### 1.5 Create a GCS Bucket

1. Go to **Cloud Storage** → **Buckets**
2. Click **"Create"**
3. Enter:
   - **Bucket name**: Choose a globally unique name (e.g., `my-graphrag-docs`)
   - **Location type**: Choose based on your needs (Region, Multi-region)
   - **Storage class**: Standard
   - **Access control**: Uniform
4. Click **"Create"**

### 1.6 Upload Sample Files

1. Open your bucket (click on its name)
2. Click **"Upload Files"**
3. Select PDF, DOCX, TXT, or other supported files
4. Files will appear in the bucket

---

## Part 2: Pub/Sub Setup (Optional - For Real-Time Updates)

If you want Flexible GraphRAG to automatically detect when files are added/modified/deleted in GCS, set up Pub/Sub notifications.

### 2.1 Create a Pub/Sub Topic

1. Go to **Pub/Sub** → **Topics**
2. Click **"Create Topic"**
3. Enter:
   - **Topic ID**: `gcs-file-notifications`
4. **Uncheck** "Add a default subscription"
5. Click **"Create"**

### 2.2 Create a Pub/Sub Subscription

1. In **Pub/Sub** → **Subscriptions**
2. Click **"Create Subscription"**
3. Enter:
   - **Subscription ID**: `gcs-notifications-sub`
   - **Select a Cloud Pub/Sub topic**: Choose `gcs-file-notifications`
   - **Delivery type**: Pull
   - **Acknowledgement deadline**: 60 seconds (default)
   - **Message retention duration**: 7 days (default)
4. Click **"Create"**

### 2.3 Configure Bucket Notifications

Use **Google Cloud Shell** (click the terminal icon at the top right of the Google Cloud Console):

```bash
# Replace with your bucket name and topic
gsutil notification create -t gcs-file-notifications -f json gs://my-graphrag-docs
```

This tells GCS to send a Pub/Sub message whenever files are created, updated, or deleted.

To verify notifications are configured:
```bash
gsutil notification list gs://my-graphrag-docs
```

You should see output like:
```
projects/_/buckets/my-graphrag-docs/notificationConfigs/1
  Cloud Pub/Sub topic: projects/my-project-123456/topics/gcs-file-notifications
```

### 2.4 Verify IAM Permissions

Go to **IAM & Admin** → **IAM** and verify your service account has:
- **Pub/Sub Subscriber** role (required for receiving messages)
- **Pub/Sub Viewer** role (optional, for cleaner logs)

If missing:
1. Click **"+ GRANT ACCESS"**
2. **New principals**: `graphrag-service-account@my-project-123456.iam.gserviceaccount.com`
3. **Select roles**: 
   - Add **Pub/Sub Subscriber**
   - Add **Pub/Sub Viewer** (optional)
4. Click **"Save"**

---

## Part 3: Flexible GraphRAG Configuration

### 3.1 Configure via UI

1. Start Flexible GraphRAG and open the UI
2. Go to **Sources** tab
3. Click **"Add Data Source"**
4. Select **"GCS (Google Cloud Storage)"**
5. Fill in the form:
   - **Source Name**: Any name (e.g., "My GCS Bucket")
   - **Bucket Name**: Your bucket name (e.g., `my-graphrag-docs`)
   - **Credentials JSON**: Paste the entire contents of your service account JSON file
   - **Prefix** (optional): Subdirectory to scan (e.g., `documents/` to only scan files in `gs://my-bucket/documents/`)
   - **Pub/Sub Subscription** (optional): Your subscription ID (e.g., `gcs-notifications-sub`)
6. Click **"Add Source"**

**Important Notes:**
- The **Project ID** is automatically extracted from the credentials JSON - you don't need to enter it separately
- If you fill in **Pub/Sub Subscription**, the system will use **event-driven mode** (real-time)
- If you leave **Pub/Sub Subscription** empty, the system will use **periodic polling mode** (checks every few minutes)

### 3.2 Manual Testing with httpie (Optional)

If you have httpie installed, you can test the connection:

```bash
# Save your credentials to a file
# credentials.json

# Test adding the source
http POST http://localhost:8000/api/sources/add \
  name="My GCS Source" \
  source_type="gcs" \
  connection_params:='{
    "bucket_name": "my-graphrag-docs",
    "credentials": "$(cat credentials.json | jq -c .)",
    "pubsub_subscription": "gcs-notifications-sub"
  }'
```

---

## Part 4: Verify It's Working

### 4.1 Check Backend Logs

Watch the Flexible GraphRAG backend logs for:

**Successful startup (without Pub/Sub):**
```
GCS detector started in PERIODIC MODE - no Pub/Sub subscription configured
```

**Successful startup (with Pub/Sub):**
```
[PUBSUB SETUP] SUCCESS: Subscription path: projects/my-project-123456/subscriptions/gcs-notifications-sub
[PUBSUB SETUP] SUCCESS: Subscription verified!
GCS detector started in EVENT MODE - Pub/Sub subscription: gcs-notifications-sub
```

**If you see permission warnings:**
```
[PUBSUB SETUP] WARNING: Could not verify subscription (403 Permission Denied)
[PUBSUB SETUP]   Service account 'graphrag-service-account@...' needs Pub/Sub permissions
[PUBSUB SETUP]   See GCS-SETUP.md for IAM configuration instructions
```
→ Go back to Part 2.4 and add the IAM roles

### 4.2 Test File Detection

**Periodic Mode:**
- Upload a new file to your GCS bucket
- Wait 2-5 minutes
- Check the Processing tab in the UI - the file should appear

**Event Mode (Pub/Sub):**
- Upload a new file to your GCS bucket
- Within seconds, check the Processing tab - the file should appear immediately

### 4.3 Check Processing Status

In the UI:
1. Go to **Processing** tab
2. You should see your files being processed
3. Check **Search** tab to query the indexed content
4. Check **Chat** tab to ask questions about your documents

---

## Common Issues

### "403 Permission Denied" on subscription
→ Add **Pub/Sub Subscriber** role to your service account (see Part 2.4)

### "404 Subscription not found"
→ Create the subscription in Pub/Sub console (see Part 2.2)

### Files not appearing in Processing tab
→ Check bucket name and credentials are correct. Check backend logs for errors.

### Pub/Sub events not being received
→ Verify bucket notifications are configured: `gsutil notification list gs://your-bucket`

---

## Summary

**Minimum Required (Periodic Polling):**
1. Google Cloud project
2. GCS bucket with files
3. Service account with **Storage Object Viewer** role
4. Service account JSON key

**For Real-Time Updates (Event-Driven):**
5. Pub/Sub topic + subscription
6. Bucket notification configuration (`gsutil notification create`)
7. Service account with **Pub/Sub Subscriber** role

That's it! Your GCS bucket is now connected to Flexible GraphRAG.

---

## Appendix: gcloud CLI Commands

If you prefer command-line tools, you can use `gcloud` commands instead of the Google Cloud Console UI.

**Install gcloud**: https://cloud.google.com/sdk/docs/install  
**Or use Google Cloud Shell**: Built into the Console (click the terminal icon at the top)

### Create Pub/Sub Topic
```bash
gcloud pubsub topics create gcs-file-notifications
```

### Create Pub/Sub Subscription
```bash
gcloud pubsub subscriptions create gcs-notifications-sub \
  --topic=gcs-file-notifications
```

### Configure Bucket Notifications
```bash
# Send file change notifications to Pub/Sub
gsutil notification create -t gcs-file-notifications -f json gs://my-graphrag-docs

# List configured notifications
gsutil notification list gs://my-graphrag-docs
```

### Add IAM Roles to Service Account
```bash
# Replace PROJECT_ID and SERVICE_ACCOUNT_EMAIL with your values

# Add Pub/Sub Subscriber (required)
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member='serviceAccount:SERVICE_ACCOUNT_EMAIL' \
  --role='roles/pubsub.subscriber'

# Add Pub/Sub Viewer (optional, for cleaner logs)
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member='serviceAccount:SERVICE_ACCOUNT_EMAIL' \
  --role='roles/pubsub.viewer'

# Add Storage Object Viewer (required to read bucket files)
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member='serviceAccount:SERVICE_ACCOUNT_EMAIL' \
  --role='roles/storage.objectViewer'
```

### Test Pub/Sub Subscription
```bash
# Pull messages (if any) from the subscription
gcloud pubsub subscriptions pull gcs-notifications-sub --limit=5 --auto-ack
```

