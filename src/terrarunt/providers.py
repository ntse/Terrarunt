import os
import boto3
from terrarunt.custom_logger import get_logger

logger = get_logger()

def is_localstack():
    return os.getenv("TF_WRAPPER_BIN", "").lower() == "tflocal"

class aws:
    def __init__(self) -> None:
        if is_localstack():
            logger.info("Localstack mode detected. Using dummy AWS account ID and default region.")
            self.account_id = "000000000000"
            self.region = os.environ.get("AWS_REGION", "us-east-1")
        else:
            try:
                session = boto3.session.Session()
                self.account_id = boto3.client("sts").get_caller_identity()["Account"]
                self.region = session.region_name or "us-east-1"
            except boto3.exceptions.Boto3Error as e:
                logger.error(f"Failed to get AWS account info: {e}")
                raise
        logger.debug(f"AWS account: {self.account_id}, region: {self.region}")