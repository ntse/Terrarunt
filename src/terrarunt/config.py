"""
Configuration management for Terrarunt
"""
import os
import logging
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class Config:
    """Terrarunt configuration"""
    
    # Terraform settings
    terraform_bin: str = "terraform"
    
    # AWS settings
    aws_region: Optional[str] = None
    aws_profile: Optional[str] = None
    
    # Stack settings
    stack_file_name: str = "dependencies.json"
    max_discovery_depth: int = 4
    
    # Bootstrap settings
    bootstrap_stacks: List[str] = None
    
    # Execution settings
    max_parallel: int = 4
    timeout: int = 3600
    
    # Logging
    log_level: str = "INFO"
    
    def __post_init__(self):
        if self.bootstrap_stacks is None:
            self.bootstrap_stacks = ["state-file", "oidc"]
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Create configuration from environment variables"""
        return cls(
            terraform_bin=os.getenv("TERRARUNT_TERRAFORM_BIN", "terraform"),
            aws_region=os.getenv("AWS_REGION"),
            aws_profile=os.getenv("AWS_PROFILE"),
            stack_file_name=os.getenv("TERRARUNT_STACK_FILE", "dependencies.json"),
            max_discovery_depth=int(os.getenv("TERRARUNT_MAX_DEPTH", "4")),
            max_parallel=int(os.getenv("TERRARUNT_MAX_PARALLEL", "4")),
            timeout=int(os.getenv("TERRARUNT_TIMEOUT", "3600")),
            log_level=os.getenv("TERRARUNT_LOG_LEVEL", "INFO"),
        )
    
    def is_localstack(self) -> bool:
        """Check if we're using LocalStack"""
        return self.terraform_bin.lower().endswith("tflocal")
    
    def setup_logging(self):
        """Setup logging based on configuration"""
        logging.basicConfig(
            level=getattr(logging, self.log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )


# Global configuration instance
config = Config.from_env()
config.setup_logging()