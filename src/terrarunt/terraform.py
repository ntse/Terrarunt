"""
Terraform command execution
"""
import os
import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Optional

from .config import config
from .aws import aws_provider
from .exceptions import TerraformError

logger = logging.getLogger(__name__)


class TerraformRunner:
    """Handles Terraform command execution"""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.executed_commands = []
    
    def run_command(self, args: List[str], cwd: Path, env_vars: Optional[Dict[str, str]] = None) -> bool:
        """Run a Terraform command"""
        command = [config.terraform_bin] + args
        
        if self.dry_run:
            self.executed_commands.append({
                'command': command,
                'cwd': str(cwd),
                'env_vars': env_vars or {}
            })
            logger.info(f"[DRY RUN] Would execute: {' '.join(command)} in {cwd}")
            return True
        
        return self._execute_command(command, cwd, env_vars)
    
    def _execute_command(self, command: List[str], cwd: Path, env_vars: Optional[Dict[str, str]] = None) -> bool:
        """Execute the actual Terraform command"""
        logger.info(f"Executing: {' '.join(command)} in {cwd}")
        
        # Prepare environment
        cmd_env = os.environ.copy()
        if env_vars:
            cmd_env.update(env_vars)
        
        # Add LocalStack environment if needed
        if config.is_localstack():
            cmd_env.update({
                'AWS_ACCESS_KEY_ID': 'test',
                'AWS_SECRET_ACCESS_KEY': 'test',
                'AWS_REGION': 'us-east-1',
                'AWS_ENDPOINT_URL': 'http://localhost:4566'
            })
        
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=cmd_env
            )
            
            # Stream output in real time
            output_lines = []
            for line in process.stdout:
                print(line, end='')
                output_lines.append(line)
            
            process.wait()
            
            if process.returncode != 0:
                output = ''.join(output_lines)
                raise TerraformError(
                    f"Terraform command failed with exit code {process.returncode}",
                    command=command,
                    returncode=process.returncode,
                    output=output
                )
            
            return True
            
        except subprocess.TimeoutExpired:
            process.kill()
            raise TerraformError(f"Terraform command timed out after {config.timeout} seconds")
        except FileNotFoundError:
            raise TerraformError(f"Terraform binary not found: {config.terraform_bin}")
        except Exception as e:
            raise TerraformError(f"Failed to execute Terraform command: {e}")
    
    def get_tfvars_args(self, env: str, stack_path: Path) -> List[str]:
        """Get tfvars arguments for a stack"""
        args = []
        
        # Look for tfvars files in various locations
        tfvars_candidates = [
            Path.cwd() / "environment" / f"{env}.tfvars",
            Path.cwd() / f"{env}.tfvars",
            Path.cwd() / "globals.tfvars",
            stack_path / "tfvars" / f"{env}.tfvars",
            stack_path / f"{env}.tfvars",
        ]
        
        for tfvars_path in tfvars_candidates:
            tfvars_path = tfvars_path.resolve()
            if tfvars_path.exists():
                args.append(f"-var-file={tfvars_path}")
                logger.debug(f"Using tfvars: {tfvars_path}")
        
        return args
    
    def init(self, env: str, stack_name: str, stack_path: Path) -> bool:
        """Initialize a Terraform stack"""
        logger.info(f"Initializing stack: {stack_name}")
        
        # Get backend configuration
        backend_args = aws_provider.get_backend_args(env, stack_name)
        tfvars_args = self.get_tfvars_args(env, stack_path)
        
        args = ["init"] + backend_args + tfvars_args
        return self.run_command(args, stack_path)
    
    def plan(self, env: str, stack_name: str, stack_path: Path, extra_args: Optional[List[str]] = None) -> bool:
        """Plan a Terraform stack"""
        logger.info(f"Planning stack: {stack_name}")
        
        tfvars_args = self.get_tfvars_args(env, stack_path)
        args = ["plan"] + tfvars_args
        
        if extra_args:
            args.extend(extra_args)
        
        return self.run_command(args, stack_path)
    
    def apply(self, env: str, stack_name: str, stack_path: Path, extra_args: Optional[List[str]] = None) -> bool:
        """Apply a Terraform stack"""
        logger.info(f"Applying stack: {stack_name}")
        
        tfvars_args = self.get_tfvars_args(env, stack_path)
        args = ["apply", "-auto-approve"] + tfvars_args
        
        if extra_args:
            args.extend(extra_args)
        
        return self.run_command(args, stack_path)
    
    def destroy(self, env: str, stack_name: str, stack_path: Path, extra_args: Optional[List[str]] = None) -> bool:
        """Destroy a Terraform stack"""
        logger.info(f"Destroying stack: {stack_name}")
        
        tfvars_args = self.get_tfvars_args(env, stack_path)
        args = ["destroy", "-auto-approve"] + tfvars_args
        
        if extra_args:
            args.extend(extra_args)
        
        return self.run_command(args, stack_path)
    
    def show_dry_run_summary(self):
        """Show summary of commands that would be executed"""
        if not self.dry_run or not self.executed_commands:
            return
        
        print("\n" + "="*60)
        print("DRY RUN SUMMARY")
        print("="*60)
        
        for i, cmd_info in enumerate(self.executed_commands, 1):
            print(f"\n{i}. Command: {' '.join(cmd_info['command'])}")
            print(f"   Directory: {cmd_info['cwd']}")
            if cmd_info['env_vars']:
                print(f"   Environment: {cmd_info['env_vars']}")
        
        print(f"\nTotal commands: {len(self.executed_commands)}")
        print("="*60)


class StackOperations:
    """High-level stack operations"""
    
    def __init__(self, dry_run: bool = False):
        self.runner = TerraformRunner(dry_run)
    
    def init_stack(self, env: str, stack_name: str) -> bool:
        """Initialize a single stack"""
        from .stacks import stack_manager
        
        stack = stack_manager.get_stack(stack_name)
        return self.runner.init(env, stack_name, stack.path)
    
    def plan_stack(self, env: str, stack_name: str, extra_args: Optional[List[str]] = None) -> bool:
        """Plan a single stack"""
        from .stacks import stack_manager
        
        stack = stack_manager.get_stack(stack_name)
        return self.runner.plan(env, stack_name, stack.path, extra_args)
    
    def apply_stack(self, env: str, stack_name: str, extra_args: Optional[List[str]] = None) -> bool:
        """Apply a single stack"""
        from .stacks import stack_manager
        
        stack = stack_manager.get_stack(stack_name)
        return self.runner.apply(env, stack_name, stack.path, extra_args)
    
    def destroy_stack(self, env: str, stack_name: str, extra_args: Optional[List[str]] = None) -> bool:
        """Destroy a single stack"""
        from .stacks import stack_manager
        
        stack = stack_manager.get_stack(stack_name)
        
        if stack.skip_on_destroy:
            logger.info(f"Skipping destroy for {stack_name} (skip_on_destroy=true)")
            return True
        
        return self.runner.destroy(env, stack_name, stack.path, extra_args)
    
    def apply_all(self, env: str, extra_args: Optional[List[str]] = None) -> bool:
        """Apply all stacks in dependency order"""
        from .stacks import stack_manager
        
        ordered_stacks, _ = stack_manager.resolve_dependencies()
        
        logger.info(f"Applying {len(ordered_stacks)} stacks in dependency order")
        
        for stack in ordered_stacks:
            try:
                success = self.apply_stack(env, stack.name, extra_args)
                if not success:
                    logger.error(f"Failed to apply {stack.name}, stopping")
                    return False
            except Exception as e:
                logger.error(f"Error applying {stack.name}: {e}")
                return False
        
        logger.info("All stacks applied successfully")
        return True
    
    def destroy_all(self, env: str, extra_args: Optional[List[str]] = None) -> bool:
        """Destroy all stacks in reverse dependency order"""
        from .stacks import stack_manager
        
        ordered_stacks, skip_set = stack_manager.resolve_dependencies()
        
        # Reverse order for destruction and filter out skipped stacks
        destroy_stacks = [s for s in reversed(ordered_stacks) if s.name not in skip_set]
        
        logger.info(f"Destroying {len(destroy_stacks)} stacks in reverse dependency order")
        
        if skip_set:
            logger.info(f"Skipping: {', '.join(skip_set)} (skip_on_destroy=true)")
        
        for stack in destroy_stacks:
            try:
                success = self.destroy_stack(env, stack.name, extra_args)
                if not success:
                    logger.error(f"Failed to destroy {stack.name}, stopping")
                    return False
            except Exception as e:
                logger.error(f"Error destroying {stack.name}: {e}")
                return False
        
        logger.info("All stacks destroyed successfully")
        return True
    
    def plan_all(self, env: str, extra_args: Optional[List[str]] = None) -> bool:
        """Plan all stacks"""
        from .stacks import stack_manager
        
        ordered_stacks, _ = stack_manager.resolve_dependencies()
        
        logger.info(f"Planning {len(ordered_stacks)} stacks")
        
        success_count = 0
        for stack in ordered_stacks:
            try:
                success = self.plan_stack(env, stack.name, extra_args)
                if success:
                    success_count += 1
                else:
                    logger.error(f"Plan failed for {stack.name}")
            except Exception as e:
                logger.error(f"Error planning {stack.name}: {e}")
        
        logger.info(f"Planning completed: {success_count}/{len(ordered_stacks)} successful")
        return success_count == len(ordered_stacks)
    
    def init_all(self, env: str, extra_args: Optional[List[str]] = None) -> bool:
        """Initialize all stacks"""
        from .stacks import stack_manager
        
        ordered_stacks, _ = stack_manager.resolve_dependencies()
        
        logger.info(f"Initializing {len(ordered_stacks)} stacks")
        
        success_count = 0
        for stack in ordered_stacks:
            try:
                success = self.init_stack(env, stack.name, extra_args)
                if success:
                    success_count += 1
                else:
                    logger.error(f"Init failed for {stack.name}")
            except Exception as e:
                logger.error(f"Error initializing {stack.name}: {e}")
        
        logger.info(f"Initialization completed: {success_count}/{len(ordered_stacks)} successful")
        return success_count == len(ordered_stacks)