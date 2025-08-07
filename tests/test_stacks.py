"""
Tests for stack discovery and dependency management
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from terrarunt.stacks import Stack, StackManager
from terrarunt.exceptions import StackNotFoundError, DependencyError


class TestStack:
    """Test Stack class"""    
    def test_stack_with_skip_on_destroy(self, temp_dir):
        """Test stack with skip_on_destroy flag"""
        stack_dir = temp_dir / "skip-stack"
        stack_dir.mkdir()
        
        config = {
            "dependencies": {"paths": []},
            "skip_on_destroy": True
        }
        
        (stack_dir / "main.tf").write_text("# Skip stack")
        (stack_dir / "dependencies.json").write_text(json.dumps(config))
        
        with patch.object(Path, 'cwd', return_value=temp_dir):
            stack = Stack.from_path(stack_dir)
        
        assert stack.skip_on_destroy is True
    
    def test_stack_invalid_json(self, temp_dir):
        """Test stack with invalid JSON configuration"""
        stack_dir = temp_dir / "invalid-stack"
        stack_dir.mkdir()
        
        (stack_dir / "main.tf").write_text("# Invalid stack")
        (stack_dir / "dependencies.json").write_text("{ invalid json }")
        
        with pytest.raises(DependencyError, match="Invalid JSON"):
            with patch.object(Path, 'cwd', return_value=temp_dir):
                Stack.from_path(stack_dir)


class TestStackManager:
    """Test StackManager class"""

    def test_discover_stacks(self, terraform_files_setup, mock_config):
        """Test stack discovery"""
        with patch('terrarunt.stacks.config', mock_config):
            # Pretend we're in the tmp directory
            with patch.object(Path, 'cwd', return_value=terraform_files_setup):
                manager = StackManager(root_path=terraform_files_setup)
                stacks = manager.discover_stacks()
        
        assert len(stacks) == 5
        assert "vpc" in stacks
        assert "security-groups" in stacks
        assert "app" in stacks
        assert "state-file" in stacks
        assert "oidc" in stacks
        
        assert stacks["vpc"].dependencies == {"paths": []}
        assert stacks["security-groups"].dependencies == {"paths": ["vpc"]}
        assert stacks["app"].dependencies == {"paths": ["vpc", "security-groups"]}
    
    def test_get_stack(self, terraform_files_setup, mock_config):
        """Test getting a specific stack"""
        with patch('terrarunt.stacks.config', mock_config):
            with patch.object(Path, 'cwd', return_value=terraform_files_setup):
                manager = StackManager(terraform_files_setup)
                
                vpc_stack = manager.get_stack("vpc")
                assert vpc_stack.name == "vpc"
                assert vpc_stack.dependencies == {"paths": []}
    
    def test_get_nonexistent_stack(self, terraform_files_setup, mock_config):
        """Test getting a stack that doesn't exist"""
        with patch('terrarunt.stacks.config', mock_config):
            with patch.object(Path, 'cwd', return_value=terraform_files_setup):
                manager = StackManager(terraform_files_setup)
                
                with pytest.raises(StackNotFoundError, match="Stack 'nonexistent' not found"):
                    manager.get_stack("nonexistent")
    
    def test_resolve_dependencies(self, terraform_files_setup, mock_config):
        """Test dependency resolution"""
        with patch('terrarunt.stacks.config', mock_config):
            with patch.object(Path, 'cwd', return_value=terraform_files_setup):
                manager = StackManager(terraform_files_setup)
                ordered_stacks, skip_set = manager.resolve_dependencies()
        
        stack_names = [s.name for s in ordered_stacks]
        
        vpc_idx = stack_names.index("vpc")
        sg_idx = stack_names.index("security-groups")
        app_idx = stack_names.index("app")
        
        assert vpc_idx < sg_idx
        assert sg_idx < app_idx
        
        assert "state-file" in skip_set
        assert "oidc" in skip_set
    
    def test_circular_dependency(self, temp_dir, mock_config):
        """Test circular dependency detection with dependencies in A -> B -> A order"""
        stack_a = temp_dir / "stack-a"
        stack_a.mkdir()
        (stack_a / "main.tf").write_text("# Stack A")
        (stack_a / "dependencies.json").write_text(json.dumps({
            "dependencies": {"paths": ["stack-b"]},
            "skip_on_destroy": False
        }))
        
        stack_b = temp_dir / "stack-b"
        stack_b.mkdir()
        (stack_b / "main.tf").write_text("# Stack B")
        (stack_b / "dependencies.json").write_text(json.dumps({
            "dependencies": {"paths": ["stack-a"]},
            "skip_on_destroy": False
        }))
        
        with patch('terrarunt.stacks.config', mock_config):
            with patch.object(Path, 'cwd', return_value=temp_dir):
                manager = StackManager(temp_dir)
                
                with pytest.raises(DependencyError, match="Circular dependency"):
                    manager.resolve_dependencies()
    
    def test_get_independent_stacks(self, terraform_files_setup, mock_config):
        """Test getting stacks with no dependencies"""
        with patch('terrarunt.stacks.config', mock_config):
            with patch.object(Path, 'cwd', return_value=terraform_files_setup):
                manager = StackManager(terraform_files_setup)
                independent = manager.get_independent_stacks()
        
        independent_names = [s.name for s in independent]
        assert "vpc" in independent_names
        assert "state-file" in independent_names
        assert "security-groups" not in independent_names 
        assert "app" not in independent_names
    
    def test_validate_stacks(self, terraform_files_setup, mock_config):
        """Test stack validation"""
        with patch('terrarunt.stacks.config', mock_config):
            with patch.object(Path, 'cwd', return_value=terraform_files_setup):
                manager = StackManager(terraform_files_setup)
                issues = manager.validate_stacks()
        
        assert len(issues) == 0
    
    def test_validate_stacks_with_missing_dependency(self, temp_dir, mock_config):
        """Test validation with missing dependency"""
        stack_dir = temp_dir / "test-stack"
        stack_dir.mkdir()
        (stack_dir / "main.tf").write_text("# Test stack")
        (stack_dir / "backend.tf").write_text('terraform { backend "s3" {} }')
        (stack_dir / "dependencies.json").write_text(json.dumps({
            "dependencies": {"paths": ["nonexistent-stack"]},
            "skip_on_destroy": False
        }))
        
        with patch('terrarunt.stacks.config', mock_config):
            with patch.object(Path, 'cwd', return_value=temp_dir):
                manager = StackManager(temp_dir)
                issues = manager.validate_stacks()
        
        assert len(issues) == 1
        assert "depends on unknown stack 'nonexistent-stack'" in issues[0]
    
    def test_validate_stacks_missing_backend(self, temp_dir, mock_config):
        """Test validation with missing backend.tf"""
        stack_dir = temp_dir / "test-stack"
        stack_dir.mkdir()
        (stack_dir / "main.tf").write_text("# Test stack")
        # No backend.tf file
        (stack_dir / "dependencies.json").write_text(json.dumps({
            "dependencies": {"paths": []},
            "skip_on_destroy": False
        }))
        
        with patch('terrarunt.stacks.config', mock_config):
            with patch.object(Path, 'cwd', return_value=temp_dir):
                manager = StackManager(temp_dir)
                issues = manager.validate_stacks()
        
        assert len(issues) == 1
        assert "missing backend.tf" in issues[0]
    
    def test_cache_clearing(self, terraform_files_setup, mock_config):
        """Test cache clearing functionality"""
        with patch('terrarunt.stacks.config', mock_config):
            with patch.object(Path, 'cwd', return_value=terraform_files_setup):
                manager = StackManager(terraform_files_setup)
                
                stacks1 = manager.discover_stacks()

                # Shouldn't scan file system again and return cached result    
                stacks2 = manager.discover_stacks()
            
                assert stacks1 is stacks2 
                
                manager.clear_cache()
                
                stacks3 = manager.discover_stacks()
                assert stacks1 is not stacks3
                assert len(stacks1) == len(stacks3) 