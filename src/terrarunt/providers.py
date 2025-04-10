import os

import boto3
from terrarunt.custom_logger import get_logger

logger = get_logger()

class aws:
    def __init__(self) -> None:
        client = boto3.client("sts")
        self.account_id = client.get_caller_identity()["Account"]
        self.region = os.environ.get("AWS_REGION")
