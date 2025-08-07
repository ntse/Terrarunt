"""
AWS provider for Terrarunt
"""
import os
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

from .config import config
from .exceptions import AWSError

logger = logging.getLogger(__name__)


@dataclass
class AWSInfo:
    """AWS account and region information"""
    account_id: str
    region: str
    profile: Optional[str] = None
    is_localstack: bool = False


class AWSProvider:
    """AWS provider for Terraform backend and operations"""
    
    def __init__(self):
        self._info: Optional[AWSInfo] = None
    
    def get_info(self) -> AWSInfo:
        """Get AWS account and region information"""
        if self._info is None:
            self._info = self._fetch_aws_info()
        return self._info
    
    def _fetch_aws_info(self) -> AWSInfo:
        """Fetch AWS information from environment or AWS API"""
        if config.is_localstack():
            logger.info("LocalStack mode detected")
            return AWSInfo(
                account_id="000000000000",
                region=config.aws_region or "us-east-1",
                is_localstack=True
            )
        
        try:
            import boto3
            from botocore.exceptions import NoCredentialsError, ClientError
            
            # Create session with optional profile
            session_kwargs = {}
            if config.aws_profile:
                session_kwargs['profile_name'] = config.aws_profile
            
            session = boto3.Session(**session_kwargs)
            
            # Get account ID
            sts_client = session.client('sts')
            identity = sts_client.get_caller_identity()
            account_id = identity['Account']
            
            # Get region
            region = session.region_name or config.aws_region or "us-east-1"
            
            logger.info(f"AWS Account: {account_id}, Region: {region}")
            
            return AWSInfo(
                account_id=account_id,
                region=region,
                profile=config.aws_profile
            )
            
        except ImportError:
            raise AWSError("boto3 is required for AWS operations. Install with: pip install boto3")
        except NoCredentialsError:
            raise AWSError("AWS credentials not found. Configure with aws configure or set environment variables.")
        except ClientError as e:
            raise AWSError(f"AWS API error: {e}")
        except Exception as e:
            raise AWSError(f"Failed to get AWS information: {e}")
    
    def get_backend_config(self, env: str, stack_name: str) -> Dict[str, str]:
        """Get S3 backend configuration for a stack"""
        aws_info = self.get_info()
        
        backend_config = {
            "bucket": f"{aws_info.account_id}-{aws_info.region}-state",
            "key": f"{env}/{stack_name}/terraform.tfstate",
            "region": aws_info.region,
            "encrypt": "true"
        }
        
        # Add LocalStack specific configuration
        if aws_info.is_localstack:
            backend_config.update({
                "access_key": "test",
                "secret_key": "test", 
                "endpoint": "http://localhost:4566",
                "skip_credentials_validation": "true",
                "skip_metadata_api_check": "true",
                "skip_requesting_account_id": "true",
                "force_path_style": "true"
            })
        
        return backend_config
    
    def get_backend_args(self, env: str, stack_name: str) -> List[str]:
        """Get backend configuration as Terraform CLI arguments"""
        backend_config = self.get_backend_config(env, stack_name)
        return [f"-backend-config={key}={value}" for key, value in backend_config.items()]
    
    def bucket_exists(self, bucket_name: str) -> bool:
        """Check if an S3 bucket exists"""
        try:
            aws_info = self.get_info()
            
            if aws_info.is_localstack:
                return self._check_localstack_bucket(bucket_name)
            else:
                return self._check_aws_bucket(bucket_name)
                
        except Exception as e:
            logger.debug(f"Error checking bucket {bucket_name}: {e}")
            return False
    
    def _check_aws_bucket(self, bucket_name: str) -> bool:
        """Check if bucket exists in AWS"""
        try:
            import boto3
            from botocore.exceptions import ClientError
            
            session_kwargs = {}
            if config.aws_profile:
                session_kwargs['profile_name'] = config.aws_profile
                
            session = boto3.Session(**session_kwargs)
            s3_client = session.client('s3')
            
            s3_client.head_bucket(Bucket=bucket_name)
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code in ['404', 'NoSuchBucket']:
                return False
            raise
    
    def _check_localstack_bucket(self, bucket_name: str) -> bool:
        """Check if bucket exists in LocalStack"""
        try:
            import boto3
            
            s3_client = boto3.client(
                's3',
                endpoint_url='http://localhost:4566',
                aws_access_key_id='test',
                aws_secret_access_key='test', 
                region_name='us-east-1'
            )
            
            s3_client.head_bucket(Bucket=bucket_name)
            return True
            
        except Exception:
            return False
    
    def state_exists(self, env: str, stack_name: str) -> bool:
        """Check if Terraform state exists for a stack"""
        try:
            aws_info = self.get_info()
            bucket_name = f"{aws_info.account_id}-{aws_info.region}-state"
            key = f"{env}/{stack_name}/terraform.tfstate"
            
            if aws_info.is_localstack:
                return self._check_localstack_state(bucket_name, key)
            else:
                return self._check_aws_state(bucket_name, key)
                
        except Exception as e:
            logger.debug(f"Error checking state for {stack_name}: {e}")
            return False
    
    def _check_aws_state(self, bucket_name: str, key: str) -> bool:
        """Check if state file exists in AWS S3"""
        try:
            import boto3
            from botocore.exceptions import ClientError
            
            session_kwargs = {}
            if config.aws_profile:
                session_kwargs['profile_name'] = config.aws_profile
                
            session = boto3.Session(**session_kwargs)
            s3_client = session.client('s3')
            
            s3_client.head_object(Bucket=bucket_name, Key=key)
            return True
            
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') == '404':
                return False
            raise
    
    def _check_localstack_state(self, bucket_name: str, key: str) -> bool:
        """Check if state file exists in LocalStack"""
        try:
            import boto3
            
            s3_client = boto3.client(
                's3',
                endpoint_url='http://localhost:4566',
                aws_access_key_id='test',
                aws_secret_access_key='test',
                region_name='us-east-1'
            )
            
            s3_client.head_object(Bucket=bucket_name, Key=key)
            return True
            
        except Exception:
            return False


aws_provider = AWSProvider()