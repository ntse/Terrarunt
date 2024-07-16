import os

import boto3
from terrarunt.custom_logger import Logger

logger = Logger(__name__)


class aws:
    def __init__(self) -> None:
        client = boto3.client("sts")
        self.account_id = client.get_caller_identity()["Account"]
        self.region = os.environ.get("AWS_REGION")
