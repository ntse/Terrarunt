"""
Bootstrap management for Terrarunt
Handles the circular dependency between state-file and oidc stacks
"""
import json
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum
from dataclasses import dataclass

from .config import config
from .aws import aws_provider
from .terraform import TerraformRunner
from .exceptions import BootstrapError

logger = logging.getLogger(__name__)


class BootstrapStage(Enum):
    """Bootstrap stages"""
    NOT_STARTED = "not_started"
    STATE_BUCKET_CREATED = "state_bucket_created"
    OIDC_CREATED = "oidc_created"
    COMPLETED = "completed"


@dataclass
class BootstrapResult:
    """Result of a bootstrap operation"""
    success: bool
    message: str
    stage: BootstrapStage
    error: Optional[Exception] = None


class BootstrapManager:
    """Manages the bootstrap process"""
    
    def __init__(self, dry_run: bool = False):
        self.runner = TerraformRunner(dry_run)
        self.dry_run = dry_run
    
    def get_current_stage(self, env: str) -> BootstrapStage:
        """Determine the current bootstrap stage"""
        try:
            aws_info = aws_provider.get_info()
            bucket_name = f"{aws_info.account_id}-{aws_info.region}-state"
            
            bucket_exists = aws_provider.bucket_exists(bucket_name)
            
            oidc_state_exists = aws_provider.state_exists(env, "oidc")
            
            state_bucket_state_exists = aws_provider.state_exists(env, "state-file")
            
            if not bucket_exists:
                return BootstrapStage.NOT_STARTED
            elif not oidc_state_exists:
                return BootstrapStage.STATE_BUCKET_CREATED
            elif not state_bucket_state_exists:
                return BootstrapStage.OIDC_CREATED
            else:
                # Check if state-file was updated after OIDC
                return BootstrapStage.COMPLETED
                
        except Exception as e:
            logger.debug(f"Error determining bootstrap stage: {e}")
            return BootstrapStage.NOT_STARTED
    
    def bootstrap(self, env: str) -> BootstrapResult:
        """Run the complete bootstrap process"""
        current_stage = self.get_current_stage(env)
        logger.info(f"Starting bootstrap from stage: {current_stage.value}")
        
        try:
            if current_stage == BootstrapStage.NOT_STARTED:
                result = self._bootstrap_stage_1(env)
                if not result.success:
                    return result
                current_stage = BootstrapStage.STATE_BUCKET_CREATED
            
            if current_stage == BootstrapStage.STATE_BUCKET_CREATED:
                result = self._bootstrap_stage_2(env)
                if not result.success:
                    return result
                current_stage = BootstrapStage.COMPLETED
                        
            return BootstrapResult(
                success=True,
                message="Bootstrap completed successfully",
                stage=BootstrapStage.COMPLETED
            )
            
        except Exception as e:
            logger.error(f"Bootstrap failed: {e}")
            return BootstrapResult(
                success=False,
                message=f"Bootstrap failed: {str(e)}",
                stage=current_stage,
                error=e
            )
    
    def _bootstrap_stage_1(self, env: str) -> BootstrapResult:
        """Stage 1: Create state bucket with local state"""
        logger.info("Stage 1: Creating state bucket with local state")
        
        try:
            from .stacks import stack_manager
            stack = stack_manager.get_stack("state-file")

            self._disable_backend(stack.path)
            
            try:
                self.runner.run_command(["init"], stack.path)
                
                tfvars_args = self.runner.get_tfvars_args(env, stack.path)
                self.runner.run_command(
                    ["apply", "-auto-approve"] + tfvars_args,
                    stack.path
                )
                
                self._enable_backend(stack.path)
                
                backend_args = aws_provider.get_backend_args(env, "state-file")
                self.runner.run_command(
                    ["init", "-migrate-state", "-force-copy"] + backend_args,
                    stack.path
                )
                
                return BootstrapResult(
                    success=True,
                    message="State bucket created successfully",
                    stage=BootstrapStage.STATE_BUCKET_CREATED
                )
                
            finally:
                self._enable_backend(stack.path)
                
        except Exception as e:
            raise BootstrapError(f"Stage 1 failed: {e}")
    
    def _bootstrap_stage_2(self, env: str) -> BootstrapResult:
        """Stage 2: Create OIDC stack using remote state"""
        logger.info("Stage 2: Creating OIDC stack using remote state")
        
        try:
            from .stacks import stack_manager
            stack = stack_manager.get_stack("oidc")
            
            # Initialize with remote backend (bucket exists now)
            backend_args = aws_provider.get_backend_args(env, "oidc")
            self.runner.run_command(["init"] + backend_args, stack.path)
            
            tfvars_args = self.runner.get_tfvars_args(env, stack.path)
            self.runner.run_command(
                ["apply", "-auto-approve"] + tfvars_args,
                stack.path
            )
            
            return BootstrapResult(
                success=True,
                message="OIDC stack created successfully",
                stage=BootstrapStage.OIDC_CREATED
            )
            
        except Exception as e:
            raise BootstrapError(f"Stage 2 failed: {e}")
                
    def _disable_backend(self, stack_path: Path):
        """Temporarily disable remote backend"""
        backend_file = stack_path / "backend.tf"
        backup_file = stack_path / "backend.tf.backup"
        
        if backend_file.exists():
            shutil.move(backend_file, backup_file, copy_function=shutil.copy2)
            logger.debug(f"Backed up backend.tf to {backup_file}")
    
    def _enable_backend(self, stack_path: Path):
        """Re-enable remote backend"""
        backend_file = stack_path / "backend.tf"
        backup_file = stack_path / "backend.tf.backup"
        
        if backup_file.exists():
            shutil.move(backup_file, backend_file)
            logger.debug("Restored backend.tf from backup")
    
    def _get_terraform_outputs(self, stack_path: Path) -> Dict[str, str]:
        """Get Terraform outputs from a stack"""
        try:
            import subprocess
            
            result = subprocess.run(
                [config.terraform_bin, "output", "-json"],
                cwd=stack_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            outputs = json.loads(result.stdout)
            
            # Extract values from Terraform output format
            simplified_outputs = {}
            for key, output_info in outputs.items():
                simplified_outputs[key] = output_info.get("value", "")
            
            return simplified_outputs
            
        except Exception as e:
            logger.warning(f"Could not get Terraform outputs: {e}")
            return {}
    
    def show_status(self, env: str):
        """Show current bootstrap status"""
        current_stage = self.get_current_stage(env)
        
        print(f"\nBootstrap Status for Environment: {env}")
        print("=" * 50)
        
        stages = [
            (BootstrapStage.NOT_STARTED, "Not started"),
            (BootstrapStage.STATE_BUCKET_CREATED, "State bucket created"),
            (BootstrapStage.OIDC_CREATED, "OIDC stack created"),
            (BootstrapStage.COMPLETED, "Bootstrap completed")
        ]
        
        for stage, description in stages:
            if stage == current_stage:
                print(f"👉 {stage.value:25s} {description} (CURRENT)")
            elif stage.value < current_stage.value:
                print(f"✅ {stage.value:25s} {description}")
            else:
                print(f"⏳ {stage.value:25s} {description}")
        
        print()
        
        if current_stage == BootstrapStage.COMPLETED:
            print("🎉 Bootstrap is complete!")
        else:
            print(f"Next: Run 'terrarunt --env {env} bootstrap' to continue")