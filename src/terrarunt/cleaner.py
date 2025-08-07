import os
import shutil
import logging
from pathlib import Path
from typing import List, Set, Dict, Optional

from .config import config
from .stacks import stack_manager
from .exceptions import TerraruntError

logger = logging.getLogger(__name__)


class TerraformCleaner:
    """Handles cleaning of Terraform-generated files"""
    
    # Files and directories to clean. Not sure about .terraform.lock.hcl
    TERRAFORM_FILES = {
        '.terraform.lock.hcl',
        'terraform.tfstate.backup',
        'crash.log',
        '.terraformrc',
        'terraform.log'
    }
    
    TERRAFORM_DIRS = {
        '.terraform'
    }
    
    STATE_FILES = {
        'terraform.tfstate'
    }
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.cleaned_files = []
        self.cleaned_dirs = []
        self.total_bytes_freed = 0
        self.errors = []
    
    def clean_stack(self, stack_name: str, include_state: bool = False) -> bool:
        try:
            stack = stack_manager.get_stack(stack_name)
            
            logger.info(f"Cleaning stack: {stack_name}")
            
            files_to_clean = self.TERRAFORM_FILES.copy()
            if include_state:
                files_to_clean.update(self.STATE_FILES)
            
            success = True
            
            for filename in files_to_clean:
                file_path = stack.path / filename
                if file_path.exists():
                    if not self._remove_file(file_path):
                        success = False
            
            for dirname in self.TERRAFORM_DIRS:
                dir_path = stack.path / dirname
                if dir_path.exists() and dir_path.is_dir():
                    if not self._remove_directory(dir_path):
                        success = False
            
            if success:
                logger.info(f"Successfully cleaned stack: {stack_name}")
            else:
                logger.error(f"Failed to fully clean stack: {stack_name}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error cleaning stack {stack_name}: {e}")
            self.errors.append(f"Stack {stack_name}: {e}")
            return False
    
    def clean_all(self, include_state: bool = False) -> bool:
        try:
            # Get all stacks (dependency order doesn't matter for cleaning)
            stacks = stack_manager.discover_stacks()
            
            logger.info(f"Cleaning {len(stacks)} stacks")
            
            success_count = 0
            for stack_name in stacks.keys():
                try:
                    if self.clean_stack(stack_name, include_state):
                        success_count += 1
                    else:
                        logger.error(f"Failed to clean {stack_name}")
                except Exception as e:
                    logger.error(f"Error cleaning {stack_name}: {e}")
            
            logger.info(f"Cleaning completed: {success_count}/{len(stacks)} successful")
            return success_count == len(stacks)
            
        except Exception as e:
            logger.error(f"Error in clean_all: {e}")
            return False
    
    def _remove_file(self, file_path: Path) -> bool:
        """Remove a single file"""
        try:
            size = file_path.stat().st_size
            
            if self.dry_run:
                logger.info(f"[DRY RUN] Would remove file: {file_path}")
            else:
                file_path.unlink()
                logger.debug(f"Removed file: {file_path}")
            
            self.cleaned_files.append(str(file_path))
            self.total_bytes_freed += size
            return True
            
        except Exception as e:
            error_msg = f"Failed to remove {file_path}: {e}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return False
    
    def _remove_directory(self, dir_path: Path) -> bool:
        """Remove a directory and all contents"""
        try:
            size = self._get_directory_size(dir_path)
            
            if self.dry_run:
                logger.info(f"[DRY RUN] Would remove directory: {dir_path}")
            else:
                shutil.rmtree(dir_path)
                logger.debug(f"Removed directory: {dir_path}")
            
            self.cleaned_dirs.append(str(dir_path))
            self.total_bytes_freed += size
            return True
            
        except Exception as e:
            error_msg = f"Failed to remove {dir_path}: {e}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return False
    
    def _get_directory_size(self, path: Path) -> int:
        """Calculate total size of directory"""
        total_size = 0
        try:
            for item in path.rglob('*'):
                if item.is_file():
                    total_size += item.stat().st_size
        except Exception as e:
            logger.debug(f"Error calculating size for {path}: {e}")
        return total_size
    
    def _format_size(self, size_bytes: int) -> str:
        """Format size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def show_summary(self):
        """Show cleaning summary - similar to dry_run_summary"""
        if not (self.cleaned_files or self.cleaned_dirs or self.errors):
            return
        
        print("\n" + "="*60)
        print("CLEAN SUMMARY")
        print("="*60)
        
        print(f"Files removed: {len(self.cleaned_files)}")
        print(f"Directories removed: {len(self.cleaned_dirs)}")
        print(f"Space freed: {self._format_size(self.total_bytes_freed)}")
        
        if self.errors:
            print(f"Errors: {len(self.errors)}")
            for error in self.errors:
                print(f"  - {error}")
        
        print("="*60)


class CleanOperations:
    """High-level clean operations"""
    
    def __init__(self, dry_run: bool = False):
        self.cleaner = TerraformCleaner(dry_run)
    
    def clean_stack(self, stack_name: str, include_state: bool = False) -> bool:
        """Clean a single stack"""
        return self.cleaner.clean_stack(stack_name, include_state)
    
    def clean_all(self, include_state: bool = False) -> bool:
        """Clean all stacks"""
        return self.cleaner.clean_all(include_state)