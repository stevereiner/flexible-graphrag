# Azure Blob Storage Setup Guide

This guide covers creating an Azure Storage Account and container, configuring it in Flexible GraphRAG, and optionally enabling Change Feed for near real-time sync.

---

## 1. Create a Storage Account

1. Go to [portal.azure.com](https://portal.azure.com) and sign in
2. Search for **"Storage accounts"** and click **+ Create**
3. Fill in the basics:
   - **Subscription** and **Resource group** — select or create one
   - **Storage account name** — e.g. `mystorageaccount` (lowercase, 3–24 chars)
   - **Region** — choose one close to you
   - **Performance** — Standard
   - **Redundancy** — LRS is fine for most use cases
4. Click **Review + Create**, then **Create**

> **Note:** Change Feed requires a **General-purpose v2** account (the default). Blob Storage accounts also work.

---

## 2. Create a Container

1. Open your new Storage Account
2. In the left menu under **Data storage**, click **Containers**
3. Click **+ Container**
   - **Name** — e.g. `graphrag-docs`
   - **Public access level** — Private (no anonymous access)
4. Click **Create**

Upload your documents to this container using the Azure Portal's **Upload** button or Azure Storage Explorer.

---

## 3. Get Your Credentials

You need the **Account Name**, **Account URL**, and **Account Key** for Flexible GraphRAG.

1. In your Storage Account, go to **Security + networking → Access keys**
2. Click **Show** next to **key1**
3. Note down:
   - **Storage account name** (top of the page)
   - **Key** (the long base64 string under key1)
4. Your **Account URL** is: `https://<storage-account-name>.blob.core.windows.net`

---

## 4. Configure in Flexible GraphRAG

In the **Add Data Source** form, select **Azure Blob Storage** and fill in:

| Field | Value |
|-------|-------|
| **Container Name** | Your container name (e.g. `graphrag-docs`) |
| **Account URL** | `https://<your-account-name>.blob.core.windows.net` |
| **Account Name** | Your storage account name |
| **Account Key** | The key1 value from Access keys |
| **Prefix** *(optional)* | Folder path to limit scope (e.g. `reports/`) |

In the **Processing** tab:
- Check **Auto Sync** to enable incremental monitoring — Flexible GraphRAG will automatically detect files added, modified, or deleted in the container

---

## 5. Enable Change Feed *(Optional — for faster sync)*

Without Change Feed, Flexible GraphRAG scans the container every 5 minutes. With Change Feed enabled, changes are detected within seconds.

1. Open your **Storage Account** in the Azure Portal
2. In the left menu under **Data management**, click **Data protection**
3. Scroll to the **Tracking** section
4. Check **Enable blob change feed**
5. Set **Retention period** — 7 days is sufficient
6. Click **Save**

That's it — no changes needed in Flexible GraphRAG. The app detects Change Feed automatically on startup and logs `Azure Blob detector started in CHANGE FEED MODE`. If Change Feed is not enabled it logs `Falling back to periodic refresh mode` and continues using 5-minute scans.

---

## How It Works

| Change Feed | Behavior |
|-------------|----------|
| **Enabled** | Near real-time detection (seconds to minutes) via Azure's immutable change log |
| **Not enabled** | Periodic scan every 5 minutes — no data loss, just a slight delay |
