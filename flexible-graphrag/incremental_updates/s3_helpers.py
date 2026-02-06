"""
S3 Configuration Helpers and Validators

Utility functions to help users set up and validate S3 event-based change detection.
"""

import logging
from typing import Dict, Tuple, Optional
import json

logger = logging.getLogger("flexible_graphrag.incremental.s3_helpers")

try:
    import boto3
    from botocore.exceptions import ClientError, BotoCoreError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    ClientError = Exception
    BotoCoreError = Exception


class S3ConfigValidator:
    """
    Validates and helps troubleshoot S3 + SQS configuration.
    
    Usage:
        validator = S3ConfigValidator(config)
        is_valid, errors = validator.validate()
        if not is_valid:
            for error in errors:
                print(f"Error: {error}")
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.errors = []
        self.warnings = []
        
    def validate(self) -> Tuple[bool, list]:
        """
        Validate S3 configuration.
        
        Returns:
            (is_valid, errors) tuple
        """
        if not BOTO3_AVAILABLE:
            self.errors.append("boto3 library not installed - run: pip install boto3")
            return False, self.errors
        
        # Required fields
        if 'bucket' not in self.config:
            self.errors.append("Missing required field: 'bucket'")
        
        # Optional but recommended fields
        if 'sqs_queue_url' not in self.config:
            self.warnings.append("No SQS queue configured - will use periodic polling instead of events")
        
        # Validate AWS region
        aws_region = self.config.get('aws_region', 'us-east-1')
        valid_regions = [
            'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
            'eu-west-1', 'eu-central-1', 'ap-southeast-1', 'ap-southeast-2',
            'ap-northeast-1', 'sa-east-1', 'ca-central-1'
        ]
        if aws_region not in valid_regions:
            self.warnings.append(f"Unusual AWS region: {aws_region} - verify this is correct")
        
        # Validate credentials (if provided)
        if 'aws_access_key_id' in self.config:
            if 'aws_secret_access_key' not in self.config:
                self.errors.append("aws_access_key_id provided but aws_secret_access_key missing")
        
        if 'aws_secret_access_key' in self.config:
            if 'aws_access_key_id' not in self.config:
                self.errors.append("aws_secret_access_key provided but aws_access_key_id missing")
        
        # Validate SQS URL format
        if 'sqs_queue_url' in self.config:
            sqs_url = self.config['sqs_queue_url']
            if not sqs_url.startswith('https://sqs.'):
                self.errors.append(f"Invalid SQS queue URL format: {sqs_url}")
            if '.amazonaws.com' not in sqs_url:
                self.errors.append(f"SQS URL must contain .amazonaws.com: {sqs_url}")
        
        is_valid = len(self.errors) == 0
        return is_valid, self.errors


class S3ConfigHelper:
    """
    Helper to test S3 and SQS connectivity and generate configuration.
    
    Usage:
        helper = S3ConfigHelper(
            bucket='my-bucket',
            aws_region='us-east-1'
        )
        
        # Test bucket access
        if helper.test_bucket_access():
            print("✓ S3 bucket accessible")
        
        # Test SQS access
        if helper.test_sqs_access('https://sqs...'):
            print("✓ SQS queue accessible")
        
        # Generate configuration
        config = helper.generate_config(sqs_queue_url='https://sqs...')
    """
    
    def __init__(
        self,
        bucket: str,
        aws_region: str = 'us-east-1',
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        prefix: str = ''
    ):
        if not BOTO3_AVAILABLE:
            raise ImportError("boto3 library required - run: pip install boto3")
        
        self.bucket = bucket
        self.aws_region = aws_region
        self.prefix = prefix
        
        # Create boto session kwargs
        self.boto_kwargs = {'region_name': aws_region}
        if aws_access_key_id and aws_secret_access_key:
            self.boto_kwargs['aws_access_key_id'] = aws_access_key_id
            self.boto_kwargs['aws_secret_access_key'] = aws_secret_access_key
        
        self.s3_client = None
        self.sqs_client = None
    
    def test_bucket_access(self) -> bool:
        """
        Test if we can access the S3 bucket.
        
        Returns:
            True if accessible, False otherwise
        """
        try:
            if not self.s3_client:
                self.s3_client = boto3.client('s3', **self.boto_kwargs)
            
            # Try to list objects (limit 1)
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=self.prefix,
                MaxKeys=1
            )
            
            logger.info(f"✓ S3 bucket access verified: {self.bucket}")
            
            # Check if bucket is empty
            if 'Contents' not in response or len(response['Contents']) == 0:
                logger.warning(f"⚠ Bucket appears empty: {self.bucket}/{self.prefix}")
            else:
                file_count = response.get('KeyCount', 0)
                logger.info(f"  Bucket contains files (sampled {file_count})")
            
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            
            if error_code == 'NoSuchBucket':
                logger.error(f"✗ Bucket does not exist: {self.bucket}")
            elif error_code == 'AccessDenied':
                logger.error(f"✗ Access denied to bucket: {self.bucket}")
                logger.error(f"  Check IAM permissions: s3:ListBucket on arn:aws:s3:::{self.bucket}")
            else:
                logger.error(f"✗ Error accessing bucket: {error_code} - {error_msg}")
            
            return False
        
        except Exception as e:
            logger.exception(f"✗ Unexpected error testing bucket access: {e}")
            return False
    
    def test_sqs_access(self, sqs_queue_url: str) -> bool:
        """
        Test if we can access the SQS queue.
        
        Args:
            sqs_queue_url: SQS queue URL
        
        Returns:
            True if accessible, False otherwise
        """
        try:
            if not self.sqs_client:
                self.sqs_client = boto3.client('sqs', **self.boto_kwargs)
            
            # Try to get queue attributes
            response = self.sqs_client.get_queue_attributes(
                QueueUrl=sqs_queue_url,
                AttributeNames=['ApproximateNumberOfMessages', 'QueueArn']
            )
            
            queue_arn = response['Attributes'].get('QueueArn', 'unknown')
            num_messages = response['Attributes'].get('ApproximateNumberOfMessages', '0')
            
            logger.info(f"✓ SQS queue access verified: {sqs_queue_url}")
            logger.info(f"  Queue ARN: {queue_arn}")
            logger.info(f"  Messages in queue: {num_messages}")
            
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            
            if error_code in ('QueueDoesNotExist', 'AWS.SimpleQueueService.NonExistentQueue'):
                logger.error(f"✗ SQS queue does not exist: {sqs_queue_url}")
            elif error_code == 'AccessDenied':
                logger.error(f"✗ Access denied to SQS queue: {sqs_queue_url}")
                logger.error(f"  Check IAM permissions: sqs:GetQueueAttributes")
            else:
                logger.error(f"✗ Error accessing SQS queue: {error_code} - {error_msg}")
            
            return False
        
        except Exception as e:
            logger.exception(f"✗ Unexpected error testing SQS access: {e}")
            return False
    
    def check_s3_event_notification(self) -> Tuple[bool, Optional[Dict]]:
        """
        Check if S3 bucket has event notifications configured.
        
        Returns:
            (has_notification, notification_config) tuple
        """
        try:
            if not self.s3_client:
                self.s3_client = boto3.client('s3', **self.boto_kwargs)
            
            response = self.s3_client.get_bucket_notification_configuration(
                Bucket=self.bucket
            )
            
            # Check for SQS configurations
            queue_configs = response.get('QueueConfigurations', [])
            topic_configs = response.get('TopicConfigurations', [])
            
            if queue_configs:
                logger.info(f"✓ S3 bucket has {len(queue_configs)} SQS event notification(s)")
                for i, config in enumerate(queue_configs):
                    queue_arn = config.get('QueueArn', 'unknown')
                    events = config.get('Events', [])
                    logger.info(f"  Notification {i+1}: {queue_arn}")
                    logger.info(f"    Events: {', '.join(events)}")
                return True, response
            
            if topic_configs:
                logger.info(f"✓ S3 bucket has {len(topic_configs)} SNS event notification(s)")
                logger.info(f"  Note: If using SNS->SQS, verify SNS subscription")
                return True, response
            
            logger.warning(f"⚠ No event notifications configured on bucket: {self.bucket}")
            logger.warning(f"  Configure S3 event notifications to enable real-time detection")
            return False, response
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'NoSuchBucket':
                logger.error(f"✗ Bucket does not exist: {self.bucket}")
            else:
                logger.warning(f"⚠ Could not check event notifications: {error_code}")
            return False, None
        
        except Exception as e:
            logger.exception(f"✗ Error checking event notifications: {e}")
            return False, None
    
    def generate_config(
        self,
        sqs_queue_url: Optional[str] = None,
        include_credentials: bool = False
    ) -> Dict:
        """
        Generate a configuration dictionary for flexible-graphrag.
        
        Args:
            sqs_queue_url: Optional SQS queue URL for event-based detection
            include_credentials: Include AWS credentials in config (not recommended for production)
        
        Returns:
            Configuration dictionary
        """
        config = {
            'bucket': self.bucket,
            'aws_region': self.aws_region
        }
        
        if self.prefix:
            config['prefix'] = self.prefix
        
        if sqs_queue_url:
            config['sqs_queue_url'] = sqs_queue_url
        
        if include_credentials and 'aws_access_key_id' in self.boto_kwargs:
            config['aws_access_key_id'] = self.boto_kwargs['aws_access_key_id']
            config['aws_secret_access_key'] = self.boto_kwargs['aws_secret_access_key']
        
        return config
    
    def print_setup_summary(self, sqs_queue_url: Optional[str] = None):
        """
        Print a summary of the S3 setup and configuration.
        
        Args:
            sqs_queue_url: Optional SQS queue URL to test
        """
        print("\n" + "="*70)
        print("  S3 Configuration Summary")
        print("="*70)
        print(f"\n📦 S3 Bucket: {self.bucket}")
        print(f"🌍 Region: {self.aws_region}")
        if self.prefix:
            print(f"📁 Prefix: {self.prefix}")
        
        print("\n🔍 Testing connectivity...")
        
        # Test S3
        print("\n1. S3 Bucket Access:")
        bucket_ok = self.test_bucket_access()
        
        # Test SQS if provided
        if sqs_queue_url:
            print("\n2. SQS Queue Access:")
            sqs_ok = self.test_sqs_access(sqs_queue_url)
            
            print("\n3. S3 Event Notifications:")
            has_notification, _ = self.check_s3_event_notification()
            
            # Summary
            print("\n" + "="*70)
            print("  Configuration Status")
            print("="*70)
            
            if bucket_ok and sqs_ok and has_notification:
                print("\n✅ ALL CHECKS PASSED - Event-based detection ready!")
                print("\n📝 Configuration:")
                config = self.generate_config(sqs_queue_url)
                print(json.dumps(config, indent=2))
                
            elif bucket_ok and sqs_ok:
                print("\n⚠️  PARTIAL - S3 and SQS accessible, but no event notification")
                print("\n📖 Next step: Configure S3 event notification")
                print(f"   See: flexible-graphrag/incremental_updates/S3-SQS-SETUP.md")
                
            elif bucket_ok:
                print("\n⚠️  PARTIAL - S3 accessible, but SQS has issues")
                print("\n📖 Next step: Fix SQS access or omit sqs_queue_url for periodic mode")
                
            else:
                print("\n❌ FAILED - Cannot access S3 bucket")
                print("\n📖 Next step: Fix S3 bucket access and IAM permissions")
        
        else:
            print("\n2. Event Detection Mode:")
            print("   ⚠️  PERIODIC MODE - No SQS queue configured")
            print("   Will scan bucket every N seconds (polling)")
            
            print("\n" + "="*70)
            print("  Configuration Status")
            print("="*70)
            
            if bucket_ok:
                print("\n✅ S3 ACCESSIBLE - Periodic mode ready")
                print("\n📝 Configuration:")
                config = self.generate_config()
                print(json.dumps(config, indent=2))
                
                print("\n💡 Tip: Add SQS for real-time event detection")
                print(f"   See: flexible-graphrag/incremental_updates/S3-SQS-SETUP.md")
            else:
                print("\n❌ FAILED - Cannot access S3 bucket")
        
        print("\n" + "="*70 + "\n")


def validate_s3_config(config: Dict) -> Tuple[bool, list, list]:
    """
    Convenience function to validate S3 configuration.
    
    Args:
        config: S3 configuration dictionary
    
    Returns:
        (is_valid, errors, warnings) tuple
    """
    validator = S3ConfigValidator(config)
    is_valid, errors = validator.validate()
    return is_valid, errors, validator.warnings


def test_s3_setup(
    bucket: str,
    aws_region: str = 'us-east-1',
    prefix: str = '',
    sqs_queue_url: Optional[str] = None,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None
):
    """
    Test S3 and SQS setup and print summary.
    
    Example:
        test_s3_setup(
            bucket='my-docs',
            aws_region='us-east-1',
            sqs_queue_url='https://sqs.us-east-1.amazonaws.com/123/my-queue'
        )
    """
    helper = S3ConfigHelper(
        bucket=bucket,
        aws_region=aws_region,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        prefix=prefix
    )
    
    helper.print_setup_summary(sqs_queue_url)


# Example usage
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Test S3 + SQS configuration for flexible-graphrag')
    parser.add_argument('--bucket', required=True, help='S3 bucket name')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--prefix', default='', help='S3 prefix (optional)')
    parser.add_argument('--sqs-queue-url', help='SQS queue URL (optional)')
    parser.add_argument('--access-key-id', help='AWS access key ID (optional, uses default credentials if omitted)')
    parser.add_argument('--secret-access-key', help='AWS secret access key (optional)')
    
    args = parser.parse_args()
    
    test_s3_setup(
        bucket=args.bucket,
        aws_region=args.region,
        prefix=args.prefix,
        sqs_queue_url=args.sqs_queue_url,
        aws_access_key_id=args.access_key_id,
        aws_secret_access_key=args.secret_access_key
    )
