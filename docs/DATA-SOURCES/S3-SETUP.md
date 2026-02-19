# S3 Event Notifications - Setup Guide

Configure S3 with SQS event notifications for real-time change detection and automatic synchronization.

## Benefits

**Event-Driven vs Polling:**

| Feature | Event Notifications (SQS) | Polling |
|---------|--------------------------|---------|
| **Latency** | 1-5 seconds | 1-60 minutes |
| **API Calls** | ~1 per change | Full bucket scan every interval |
| **Cost** | Very low (per event) | Moderate (LIST operations) |
| **Scalability** | Unlimited | Limited by LIST performance |

**Performance:**
- ⚡ **720x faster** updates (5 seconds vs 1 hour)
- 💰 **60x fewer** API calls
- 📈 **Infinite scalability** (no need to list all objects)

## Architecture

```
S3 Bucket → Event Notifications → SQS Queue → Flexible GraphRAG
```

**How it works:**
1. File added/modified/deleted in S3 bucket
2. S3 sends event notification to SQS queue
3. Flexible GraphRAG polls SQS queue
4. Change is detected and processed immediately

## Prerequisites

- AWS account with S3 bucket
- IAM permissions for S3, SQS, and IAM
- Flexible GraphRAG with incremental updates enabled

## Setup Methods

Choose your preferred method:

### Option A: AWS Console (Easiest)

Step-by-step visual setup using AWS web console.

### Option B: AWS CLI (Fastest)

Command-line setup for automation and scripting.

### Option C: Terraform (Production)

Infrastructure as code for reproducible deployments.

## Option A: AWS Console Setup

### Step 1: Create SQS Queue

1. Open **SQS Console**: https://console.aws.amazon.com/sqs/
2. Click **Create queue**
3. Configure queue:
   - **Type**: Standard
   - **Name**: `flexible-graphrag-s3-events`
   - **Visibility timeout**: 300 seconds
   - **Message retention**: 1 day (86400 seconds)
   - **Receive message wait time**: 20 seconds (long polling)
4. Click **Create queue**
5. **Copy the Queue URL** (you'll need this later)
   - Format: `https://sqs.REGION.amazonaws.com/ACCOUNT_ID/flexible-graphrag-s3-events`

### Step 2: Configure SQS Access Policy

1. In SQS console, select your queue
2. Click **Access policy** tab
3. Click **Edit**
4. Replace with this policy (update bucket name and account ID):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "s3.amazonaws.com"
      },
      "Action": "SQS:SendMessage",
      "Resource": "arn:aws:sqs:REGION:ACCOUNT_ID:flexible-graphrag-s3-events",
      "Condition": {
        "ArnLike": {
          "aws:SourceArn": "arn:aws:s3:::YOUR_BUCKET_NAME"
        }
      }
    }
  ]
}
```

5. Click **Save**

### Step 3: Configure S3 Event Notifications

1. Open **S3 Console**: https://console.aws.amazon.com/s3/
2. Select your bucket
3. Click **Properties** tab
4. Scroll to **Event notifications**
5. Click **Create event notification**
6. Configure:
   - **Name**: `flexible-graphrag-changes`
   - **Prefix** (optional): `documents/` (monitor specific folder)
   - **Suffix** (optional): `.pdf` (monitor specific file types)
   - **Event types**:
     - ✅ All object create events
     - ✅ All object delete events
   - **Destination**: SQS queue
   - **SQS queue**: Select `flexible-graphrag-s3-events`
7. Click **Save changes**

### Step 4: Configure in Flexible GraphRAG

**Via Web UI:**

1. Open http://localhost:5000
2. Go to **Processing** tab → **S3**
3. Fill in:
   - Bucket name: `your-bucket-name`
   - Prefix (optional): `documents/`
   - SQS Queue URL: `https://sqs.region.amazonaws.com/account/flexible-graphrag-s3-events`
4. Check ✅ **Enable automatic sync**
5. Check ✅ **Enable change stream** (uses SQS events)
6. Click **Process**

**Via REST API:**

```json
POST /api/ingest

{
  "data_source": "s3",
  "s3_config": {
    "bucket_name": "your-bucket-name",
    "prefix": "documents/",
    "sqs_queue_url": "https://sqs.us-east-1.amazonaws.com/123456789/flexible-graphrag-s3-events"
  },
  "enable_sync": true,
  "skip_graph": true,
  "sync_config": {
    "source_name": "S3 Documents",
    "enable_change_stream": true
  }
}
```

## Option B: AWS CLI Setup

Complete setup using AWS CLI commands.

### Step 1: Create SQS Queue

```bash
# Set variables
QUEUE_NAME="flexible-graphrag-s3-events"
BUCKET_NAME="your-bucket-name"
REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create queue
aws sqs create-queue \
  --queue-name $QUEUE_NAME \
  --region $REGION \
  --attributes VisibilityTimeout=300,ReceiveMessageWaitTimeSeconds=20

# Get queue URL and ARN
QUEUE_URL=$(aws sqs get-queue-url --queue-name $QUEUE_NAME --region $REGION --query QueueUrl --output text)
QUEUE_ARN="arn:aws:sqs:${REGION}:${ACCOUNT_ID}:${QUEUE_NAME}"

echo "Queue URL: $QUEUE_URL"
echo "Queue ARN: $QUEUE_ARN"
```

### Step 2: Set SQS Access Policy

```bash
# Create policy document
cat > /tmp/sqs-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "s3.amazonaws.com"
      },
      "Action": "SQS:SendMessage",
      "Resource": "${QUEUE_ARN}",
      "Condition": {
        "ArnLike": {
          "aws:SourceArn": "arn:aws:s3:::${BUCKET_NAME}"
        }
      }
    }
  ]
}
EOF

# Apply policy to queue
aws sqs set-queue-attributes \
  --queue-url $QUEUE_URL \
  --attributes file:///tmp/sqs-policy.json
```

### Step 3: Configure S3 Event Notifications

```bash
# Create notification configuration
cat > /tmp/s3-notification.json <<EOF
{
  "QueueConfigurations": [
    {
      "QueueArn": "${QUEUE_ARN}",
      "Events": [
        "s3:ObjectCreated:*",
        "s3:ObjectRemoved:*"
      ],
      "Filter": {
        "Key": {
          "FilterRules": [
            {
              "Name": "prefix",
              "Value": "documents/"
            }
          ]
        }
      }
    }
  ]
}
EOF

# Apply notification to bucket
aws s3api put-bucket-notification-configuration \
  --bucket $BUCKET_NAME \
  --notification-configuration file:///tmp/s3-notification.json

echo "Setup complete!"
echo "Queue URL: $QUEUE_URL"
```

### Step 4: Configure in Flexible GraphRAG

Use the Queue URL from Step 1:

```bash
# Add to .env or configure via UI/API
SQS_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/123456789/flexible-graphrag-s3-events"
```

## Option C: Terraform Setup

Complete infrastructure as code.

```hcl
# variables.tf
variable "bucket_name" {
  description = "S3 bucket name"
  type        = string
}

variable "prefix" {
  description = "S3 prefix to monitor (optional)"
  type        = string
  default     = ""
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

# sqs.tf
resource "aws_sqs_queue" "graphrag_s3_events" {
  name                       = "flexible-graphrag-s3-events"
  visibility_timeout_seconds = 300
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20
  
  tags = {
    Application = "flexible-graphrag"
    Purpose     = "S3 event notifications"
  }
}

# SQS policy to allow S3 to send messages
resource "aws_sqs_queue_policy" "graphrag_s3_events" {
  queue_url = aws_sqs_queue.graphrag_s3_events.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action   = "SQS:SendMessage"
        Resource = aws_sqs_queue.graphrag_s3_events.arn
        Condition = {
          ArnLike = {
            "aws:SourceArn" = "arn:aws:s3:::${var.bucket_name}"
          }
        }
      }
    ]
  })
}

# s3.tf
resource "aws_s3_bucket_notification" "graphrag_events" {
  bucket = var.bucket_name

  queue {
    queue_arn     = aws_sqs_queue.graphrag_s3_events.arn
    events        = ["s3:ObjectCreated:*", "s3:ObjectRemoved:*"]
    filter_prefix = var.prefix
  }

  depends_on = [aws_sqs_queue_policy.graphrag_s3_events]
}

# outputs.tf
output "queue_url" {
  description = "SQS Queue URL for flexible-graphrag"
  value       = aws_sqs_queue.graphrag_s3_events.url
}

output "queue_arn" {
  description = "SQS Queue ARN"
  value       = aws_sqs_queue.graphrag_s3_events.arn
}
```

**Usage:**

```bash
# Initialize and apply
terraform init
terraform plan -var="bucket_name=your-bucket-name"
terraform apply -var="bucket_name=your-bucket-name"

# Get queue URL
terraform output queue_url
```

## Testing

### Test Event Delivery

1. Upload a file to your S3 bucket:
   ```bash
   echo "test content" > test.txt
   aws s3 cp test.txt s3://your-bucket-name/documents/test.txt
   ```

2. Check SQS queue for messages:
   ```bash
   aws sqs receive-message \
     --queue-url https://sqs.region.amazonaws.com/account/queue-name \
     --max-number-of-messages 1
   ```

3. Check Flexible GraphRAG logs:
   ```
   INFO: EVENT: CREATE detected for test.txt
   INFO: Processing test.txt via backend (full pipeline)
   INFO: SUCCESS: Processed test.txt via backend pipeline
   ```

### Verify Setup

**Check SQS Messages:**
```bash
aws sqs get-queue-attributes \
  --queue-url YOUR_QUEUE_URL \
  --attribute-names ApproximateNumberOfMessages
```

**Check Backend Logs:**
```
INFO: S3 detector started with SQS queue
INFO: Polling SQS queue for events...
```

## Monitoring

### CloudWatch Metrics

Monitor in AWS Console → CloudWatch:

**SQS Metrics:**
- `NumberOfMessagesSent` - Events from S3
- `NumberOfMessagesReceived` - Events processed by Flexible GraphRAG
- `ApproximateAgeOfOldestMessage` - Processing lag

**S3 Metrics:**
- `AllRequests` - Total S3 requests
- `4xxErrors`, `5xxErrors` - Request failures

### Application Logs

Check Flexible GraphRAG backend logs:

```bash
# Look for event processing
grep "EVENT: CREATE" logs/flexible-graphrag.log
grep "EVENT: DELETE" logs/flexible-graphrag.log

# Check for errors
grep "ERROR" logs/flexible-graphrag.log | grep -i "s3\|sqs"
```

## Troubleshooting

### No Events Received

**Check SQS queue has messages:**
```bash
aws sqs get-queue-attributes \
  --queue-url YOUR_QUEUE_URL \
  --attribute-names ApproximateNumberOfMessages
```

**If queue is empty:**
1. Verify S3 event notification is configured
2. Check SQS access policy allows S3 to send messages
3. Test by uploading a file to S3
4. Check CloudWatch Events for delivery failures

**If queue has messages but not processed:**
1. Check backend logs for SQS polling errors
2. Verify `enable_change_stream = true` in datasource config
3. Check AWS credentials are valid
4. Ensure SQS queue URL is correct in configuration

### Duplicate Processing

**Symptom:** Same file processed multiple times

**Causes:**
1. Multiple event notifications configured for same bucket
2. SQS visibility timeout too short (file still processing when message becomes visible again)
3. Multiple Flexible GraphRAG instances polling same queue

**Solutions:**
1. Remove duplicate event notifications in S3 bucket settings
2. Increase SQS visibility timeout to 300+ seconds
3. Use separate queues for different Flexible GraphRAG instances

### High SQS Costs

**Symptom:** Unexpected SQS charges

**Causes:**
1. Too many empty receives (short polling)
2. Very high event volume
3. Messages not being deleted after processing

**Solutions:**
1. Enable long polling (`receive_wait_time_seconds = 20`)
2. Use filtering in S3 event notifications (prefix/suffix)
3. Check backend is deleting messages after processing

### Permission Errors

**Error:** `Access Denied` when polling SQS

**Solution:** Add IAM policy to Flexible GraphRAG execution role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:region:account:flexible-graphrag-s3-events"
    }
  ]
}
```

## Cost Optimization

### Reduce SQS Costs

1. **Enable Long Polling:** Set `receive_wait_time_seconds = 20`
   - Reduces empty receives by 90%
   
2. **Filter Events:** Use prefix/suffix in S3 event notifications
   - Only get events for relevant files
   
3. **Batch Processing:** Process multiple events per poll
   - Configured in S3 detector (default: 10 messages per poll)

### Estimated Costs

**Example: 10,000 file changes per day**

| Service | Usage | Cost (us-east-1) |
|---------|-------|------------------|
| SQS | 10,000 messages + 4,320 receives (every 20s) | $0.00 (free tier: 1M requests/month) |
| S3 Events | 10,000 notifications | $0.00 (included with S3) |
| S3 API | ~400 LIST requests (fallback polling at 5min interval) | $0.00 (free tier: 2,000 LIST/month) |
| **Total** | | **~$0.00/month** (within free tier) |

**Without SQS (polling only):**
| Service | Usage | Cost |
|---------|-------|------|
| S3 API | ~8,640 LIST requests per day | $0.43/month |

**Savings: ~$5/month + 720x faster updates**

## Security Best Practices

1. **Least Privilege IAM Policies**
   - Grant only necessary permissions
   - Separate roles for different components

2. **SQS Access Policy**
   - Restrict to specific S3 bucket ARN
   - Use condition keys for additional security

3. **Encryption**
   - Enable SQS encryption at rest (optional)
   - Use S3 bucket encryption

4. **VPC Endpoints** (Enterprise)
   - Use VPC endpoints for S3 and SQS
   - Avoid internet traffic for better security

5. **Monitor Access**
   - Enable CloudTrail logging
   - Review SQS/S3 access patterns regularly

## Advanced Configuration

### Multiple Buckets

Monitor multiple S3 buckets with separate queues:

```bash
# Bucket 1 → Queue 1
aws s3api put-bucket-notification-configuration \
  --bucket bucket1 \
  --notification-configuration '{
    "QueueConfigurations": [{
      "QueueArn": "arn:aws:sqs:region:account:queue1",
      "Events": ["s3:ObjectCreated:*"]
    }]
  }'

# Bucket 2 → Queue 2
aws s3api put-bucket-notification-configuration \
  --bucket bucket2 \
  --notification-configuration '{
    "QueueConfigurations": [{
      "QueueArn": "arn:aws:sqs:region:account:queue2",
      "Events": ["s3:ObjectCreated:*"]
    }]
  }'
```

Configure separate datasources in Flexible GraphRAG for each queue.

### Event Filtering

**By file type:**
```json
{
  "Filter": {
    "Key": {
      "FilterRules": [
        {
          "Name": "suffix",
          "Value": ".pdf"
        }
      ]
    }
  }
}
```

**By folder:**
```json
{
  "Filter": {
    "Key": {
      "FilterRules": [
        {
          "Name": "prefix",
          "Value": "documents/reports/"
        }
      ]
    }
  }
}
```

### SNS Fan-Out (Multiple Consumers)

If you have multiple applications that need S3 events:

```
S3 Bucket → SNS Topic → SQS Queue 1 → Flexible GraphRAG
                     ↓
                     └→ SQS Queue 2 → Other App
```

See AWS documentation for SNS fan-out setup.

## Next Steps

- **[Setup Guide](./SETUP-GUIDE.md)** - Configure other data sources
- **[API Reference](./API-REFERENCE.md)** - Manage datasources via API
- **[Quick Start](./QUICKSTART.md)** - Test your setup
- **AWS S3 Event Notifications**: https://docs.aws.amazon.com/AmazonS3/latest/userguide/NotificationHowTo.html
- **AWS SQS Long Polling**: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-short-and-long-polling.html
