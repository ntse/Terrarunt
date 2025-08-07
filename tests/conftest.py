import pytest
import tempfile
import json
import shutil
from pathlib import Path
from unittest.mock import Mock, patch
import sys

src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from terrarunt.config import Config

@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests"""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    return Config(
        terraform_bin="terraform",
        aws_region="us-east-1",
        stack_file_name="dependencies.json",
        max_discovery_depth=3,
        max_parallel=2,
        timeout=30,
        log_level="INFO"
    )

@pytest.fixture
def terraform_files_setup(temp_dir):
    """Used when we're not mocking the Terraform"""
    # VPC stack
    vpc_dir = temp_dir / "vpc"
    vpc_dir.mkdir()
    print(vpc_dir)
    (vpc_dir / "main.tf").write_text("# VPC resources")
    (vpc_dir / "backend.tf").write_text('terraform { backend "s3" {} }')
    (vpc_dir / "dependencies.json").write_text(json.dumps({
        "dependencies": {"paths": []},
        "skip_on_destroy": False
    }))
    
    # Security groups stack
    sg_dir = temp_dir / "security-groups"
    sg_dir.mkdir()
    (sg_dir / "main.tf").write_text("# Security group resources")
    (sg_dir / "backend.tf").write_text('terraform { backend "s3" {} }')
    (sg_dir / "dependencies.json").write_text(json.dumps({
        "dependencies": {"paths": ["vpc"]},
        "skip_on_destroy": False
    }))
    
    # App stack
    app_dir = temp_dir / "app"
    app_dir.mkdir()
    (app_dir / "main.tf").write_text("# App resources")
    (app_dir / "backend.tf").write_text('terraform { backend "s3" {} }')
    (app_dir / "dependencies.json").write_text(json.dumps({
        "dependencies": {"paths": ["vpc", "security-groups"]},
        "skip_on_destroy": False
    }))
    
    # Bootstrap stacks
    state_dir = temp_dir / "state-file"
    state_dir.mkdir()
    (state_dir / "main.tf").write_text("# State bucket")
    (state_dir / "backend.tf").write_text('terraform { backend "s3" {} }')
    (state_dir / "dependencies.json").write_text(json.dumps({
        "dependencies": {"paths": []},
        "skip_on_destroy": True
    }))
    
    oidc_dir = temp_dir / "oidc"
    oidc_dir.mkdir()
    (oidc_dir / "main.tf").write_text("# OIDC provider")
    (oidc_dir / "backend.tf").write_text('terraform { backend "s3" {} }')
    (oidc_dir / "dependencies.json").write_text(json.dumps({
        "dependencies": {"paths": ["state-file"]},
        "skip_on_destroy": True
    }))
    
    return temp_dir


@pytest.fixture
def mock_subprocess():
    """Mock subprocess for Terraform command execution"""
    with patch('subprocess.Popen') as mock_popen:
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.stdout = iter(["Terraform output line 1\n", "Success!\n"])
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process
        yield mock_popen


@pytest.fixture
def mock_stack_manager():
    """Mock stack manager with predefined stacks"""
    with patch('terrarunt.stacks.stack_manager') as mock:
        # Create mock stacks
        vpc_stack = Mock()
        vpc_stack.name = "vpc"
        vpc_stack.path = Path("/mock/vpc")
        vpc_stack.dependencies = {"paths": []}
        vpc_stack.skip_on_destroy = False
        
        sg_stack = Mock()
        sg_stack.name = "security-groups"
        sg_stack.path = Path("/mock/security-groups")
        sg_stack.dependencies = {"paths": ["vpc"]}
        sg_stack.skip_on_destroy = False
        
        app_stack = Mock()
        app_stack.name = "app"
        app_stack.path = Path("/mock/app")
        app_stack.dependencies = {"paths": ["vpc", "security-groups"]}
        app_stack.skip_on_destroy = False

        state_file_stack = Mock()
        state_file_stack.name = "app"
        state_file_stack.path = Path("/mock/state-file")
        state_file_stack.dependencies = {"paths": []}
        state_file_stack.skip_on_destroy = True
        
        mock_stacks = {
            "vpc": vpc_stack,
            "security-groups": sg_stack,
            "app": app_stack,
            "state-file": state_file_stack
        }
        
        mock.discover_stacks.return_value = mock_stacks
        mock.get_stack.side_effect = lambda name: mock_stacks[name]
        mock.resolve_dependencies.return_value = (
            [vpc_stack, sg_stack, app_stack, state_file_stack],
            set()
        )
        
        yield mock


@pytest.fixture(autouse=True)
def reset_modules():
    """Reset module-level state between tests"""
    # Clear any cached stack managers
    from terrarunt.stacks import stack_manager
    if hasattr(stack_manager, '_stacks_cache'):
        stack_manager._stacks_cache = None
    
    yield
    
    # Clean up after test
    if hasattr(stack_manager, '_stacks_cache'):
        stack_manager._stacks_cache = None


@pytest.fixture
def clean_files_setup(temp_dir):
    """Create Terraform files that need cleaning"""
    stack_dir = temp_dir / "test-stack"
    stack_dir.mkdir()
    
    (stack_dir / "main.tf").write_text("# Main terraform file")
    (stack_dir / "backend.tf").write_text('terraform { backend "s3" {} }')
    
    (stack_dir / ".terraform.lock.hcl").write_text("# Lock file")
    (stack_dir / "terraform.tfstate.backup").write_text('{"version": 4}')
    (stack_dir / "crash.log").write_text("Error log")
    (stack_dir / "terraform.tfstate").write_text('{"version": 4}')
    
    terraform_dir = stack_dir / ".terraform"
    terraform_dir.mkdir()
    (terraform_dir / "terraform.tfstate").write_text('{"version": 4}')
    (terraform_dir / "providers.lock.json").write_text('{}')
    
    return stack_dir