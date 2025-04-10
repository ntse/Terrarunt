import os

import boto3
from terrarunt.custom_logger import get_logger

logger = get_logger()

def is_localstack():
    return os.getenv("TF_WRAPPER_BIN", "").lower() == "tflocal"

class aws:
    def __init__(self) -> None:
        if is_localstack():
            self.account_id="000000000000"
        else:
            client = boto3.client("sts")
            self.account_id = client.get_caller_identity()["Account"]
        self.region = os.environ.get("AWS_REGION")
