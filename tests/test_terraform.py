"""
Tests for Terraform command execution
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from moto import mock_aws

from terrarunt.terraform import TerraformRunner, StackOperations
from terrarunt.exceptions import TerraformError


class TestTerraformRunner:
    """Test TerraformRunner class"""
    
    def test_dry_run_mode(self, temp_dir, mock_config):
        """Test dry run mode doesn't execute commands"""
        runner = TerraformRunner(dry_run=True)
        
        result = runner.run_command(["init"], temp_dir)
        
        assert result is True
        assert len(runner.executed_commands) == 1
        assert runner.executed_commands[0]['command'] == ['terraform', 'init']
        assert runner.executed_commands[0]['cwd'] == str(temp_dir)
    
    def test_successful_command_execution(self, temp_dir, mock_subprocess, mock_config):
        """Test successful command execution"""
        with patch('terrarunt.terraform.config', mock_config):
            runner = TerraformRunner(dry_run=False)
            
            result = runner.run_command(["init"], temp_dir)
            
            assert result is True
            mock_subprocess.assert_called_once()
            
            call_args = mock_subprocess.call_args
            assert call_args[0][0] == ['terraform', 'init']
            assert call_args[1]['cwd'] == temp_dir
    
    def test_failed_command_execution(self, temp_dir, mock_config):
        """Test failed command execution"""
        with patch('subprocess.Popen') as mock_popen:
            mock_process = Mock()
            mock_process.returncode = 1
            mock_process.stdout = iter(["Error: something went wrong\n"])
            mock_process.wait.return_value = None
            mock_popen.return_value = mock_process
            
            with patch('terrarunt.terraform.config', mock_config):
                runner = TerraformRunner(dry_run=False)
                
                with pytest.raises(TerraformError, match="Terraform command failed with exit code 1"):
                    runner.run_command(["apply"], temp_dir)
    
    def test_terraform_binary_not_found(self, temp_dir, mock_config):
        """Test handling of missing Terraform binary"""
        with patch('subprocess.Popen', side_effect=FileNotFoundError):
            with patch('terrarunt.terraform.config', mock_config):
                runner = TerraformRunner(dry_run=False)
                
                with pytest.raises(TerraformError, match="Terraform binary not found"):
                    runner.run_command(["init"], temp_dir)
    
    def test_localstack_environment(self, temp_dir, mock_subprocess):
        """Test LocalStack environment setup"""
        mock_config = Mock()
        mock_config.terraform_bin = "tflocal"
        mock_config.is_localstack.return_value = True
        
        with patch('terrarunt.terraform.config', mock_config):
            runner = TerraformRunner(dry_run=False)
            runner.run_command(["init"], temp_dir)
            
            # Check that LocalStack environment variables were set
            call_args = mock_subprocess.call_args
            env = call_args[1]['env']
            assert env['AWS_ACCESS_KEY_ID'] == 'test'
            assert env['AWS_SECRET_ACCESS_KEY'] == 'test'
            assert env['AWS_REGION'] == 'us-east-1'
            assert env['AWS_ENDPOINT_URL'] == 'http://localhost:4566'
    
    def test_get_tfvars_args(self, temp_dir, mock_config):
        """Test tfvars file discovery"""
        # Create various tfvars files
        (temp_dir / "globals.tfvars").write_text("global_var = 'value'")
        (temp_dir / "dev.tfvars").write_text("env_var = 'dev'")
        
        env_dir = temp_dir / "environment"
        env_dir.mkdir()
        (env_dir / "dev.tfvars").write_text("env_specific = 'dev'")
        
        stack_dir = temp_dir / "my-stack"
        stack_dir.mkdir()
        tfvars_dir = stack_dir / "tfvars"
        tfvars_dir.mkdir()
        (tfvars_dir / "dev.tfvars").write_text("stack_specific = 'dev'")
        
        with patch('terrarunt.terraform.config', mock_config):
            with patch.object(Path, 'cwd', return_value=temp_dir):
                runner = TerraformRunner()
                args = runner.get_tfvars_args("dev", stack_dir)
        
        # Should find multiple tfvars files
        assert len(args) > 0
        assert any("globals.tfvars" in arg for arg in args)
        assert any("dev.tfvars" in arg for arg in args)
    
    @mock_aws
    def test_init_command(self, temp_dir, mock_subprocess, mock_config):
        """Test Terraform init command"""
        with patch('terrarunt.terraform.config', mock_config):
            runner = TerraformRunner(dry_run=False)
            
            result = runner.init("dev", "test-stack", temp_dir)
            
            assert result is True
            mock_subprocess.assert_called_once()
            
            # Check command includes backend configuration
            call_args = mock_subprocess.call_args
            command = call_args[0][0]
            assert command[0] == 'terraform'
            assert command[1] == 'init'
            assert any('-backend-config=' in arg for arg in command)
    
    def test_apply_command(self, temp_dir, mock_subprocess, mock_config):
        """Test Terraform apply command"""
        with patch('terrarunt.terraform.config', mock_config):
            runner = TerraformRunner(dry_run=False)
            
            result = runner.apply("dev", "test-stack", temp_dir, ["-target=aws_instance.test"])
            
            assert result is True
            mock_subprocess.assert_called_once()
            
            call_args = mock_subprocess.call_args
            command = call_args[0][0]
            assert command[0] == 'terraform'
            assert command[1] == 'apply'
            assert '-auto-approve' in command
            assert '-target=aws_instance.test' in command
    
    def test_destroy_command(self, temp_dir, mock_subprocess, mock_config):
        """Test Terraform destroy command"""
        with patch('terrarunt.terraform.config', mock_config):
            runner = TerraformRunner(dry_run=False)
            
            result = runner.destroy("dev", "test-stack", temp_dir)
            
            assert result is True
            mock_subprocess.assert_called_once()
            
            call_args = mock_subprocess.call_args
            command = call_args[0][0]
            assert command[0] == 'terraform'
            assert command[1] == 'destroy'
            assert '-auto-approve' in command
    
    def test_show_dry_run_summary(self, temp_dir, mock_config, capsys):
        """Test dry run summary display"""
        runner = TerraformRunner(dry_run=True)
        
        runner.run_command(["init"], temp_dir)
        runner.run_command(["plan"], temp_dir)
        runner.run_command(["apply"], temp_dir)
        
        runner.show_dry_run_summary()
        
        captured = capsys.readouterr()
        assert "DRY RUN SUMMARY" in captured.out
        assert "Total commands: 3" in captured.out
        assert "terraform init" in captured.out
        assert "terraform plan" in captured.out
        assert "terraform apply" in captured.out


class TestStackOperations:
    """Test StackOperations high-level interface"""
    
    @mock_aws
    def test_apply_stack_success(self, mock_subprocess, mock_config, mock_stack_manager):
        """Test successful stack apply"""
        with patch('terrarunt.terraform.config', mock_config):
            with patch('terrarunt.stacks.stack_manager', mock_stack_manager):
                operations = StackOperations(dry_run=False)
                
                result = operations.apply_stack("dev", "vpc")
                
                assert result is True
                mock_subprocess.assert_called_once()
    
    def test_apply_stack_nonexistent(self, terraform_files_setup, mock_config):
        """Test applying nonexistent stack"""
        with patch('terrarunt.terraform.config', mock_config):
            with patch.object(Path, 'cwd', return_value=terraform_files_setup):
                operations = StackOperations()
                
                with pytest.raises(Exception):
                    operations.apply_stack("dev", "nonexistent")
    
    def test_destroy_stack_with_skip_flag(self, terraform_files_setup, mock_config, mock_stack_manager):
        """Test destroying stack with skip_on_destroy flag"""
        with patch('terrarunt.stacks.stack_manager', mock_stack_manager):
            with patch('terrarunt.terraform.config', mock_config):
                with patch.object(Path, 'cwd', return_value=terraform_files_setup):
                    operations = StackOperations()
                    
                    result = operations.destroy_stack("dev", "state-file")
                    
                    assert result is True 
        
    def test_apply_all_success(self, terraform_files_setup, mock_subprocess, mock_config, mock_stack_manager):
        """Test successful apply-all operation"""
        with patch('terrarunt.stacks.stack_manager', mock_stack_manager):
            with patch('terrarunt.terraform.config', mock_config):
                with patch.object(Path, 'cwd', return_value=terraform_files_setup):
                    operations = StackOperations(dry_run=False)
                    
                    result = operations.apply_all("dev")
                    
                    assert result is True
                    assert mock_subprocess.call_count == 4
    
    def test_apply_all_with_failure(self, terraform_files_setup, mock_config, mock_stack_manager):
        """Test apply-all with one stack failure"""
        with patch('subprocess.Popen') as mock_popen:
            # First call succeeds, second fails
            mock_success = Mock()
            mock_success.returncode = 0
            mock_success.stdout = iter(["Success\n"])
            mock_success.wait.return_value = None
            
            mock_failure = Mock()
            mock_failure.returncode = 1
            mock_failure.stdout = iter(["Error\n"])
            mock_failure.wait.return_value = None
            
            mock_popen.side_effect = [mock_success, mock_failure]
            
            with patch('terrarunt.stacks.stack_manager', mock_stack_manager):
                with patch('terrarunt.terraform.config', mock_config):
                    with patch.object(Path, 'cwd', return_value=terraform_files_setup):
                        operations = StackOperations(dry_run=False)
                        
                        result = operations.apply_all("dev")
                        
                        assert result is False
    
    def test_destroy_all_reverse_order(self, terraform_files_setup, mock_config):
        """Test destroy-all uses reverse dependency order"""
        with patch('terrarunt.terraform.config', mock_config):
            with patch.object(Path, 'cwd', return_value=terraform_files_setup):
                operations = StackOperations(dry_run=True)
                
                result = operations.destroy_all("dev")
                
                assert result is True
                
                commands = operations.runner.executed_commands
                
                executed_stacks = []
                for cmd in commands:
                    if 'destroy' in cmd['command']:
                        cwd_path = Path(cmd['cwd'])
                        executed_stacks.append(cwd_path.name)
                
                # App should be destroyed before its dependencies
                if 'app' in executed_stacks and 'vpc' in executed_stacks:
                    app_idx = executed_stacks.index('app')
                    vpc_idx = executed_stacks.index('vpc')
                    assert app_idx < vpc_idx
    
    @mock_aws
    def test_plan_all(self, terraform_files_setup, mock_subprocess, mock_config, mock_stack_manager):
        """Test plan-all operation"""
        with patch('terrarunt.stacks.stack_manager', mock_stack_manager):
            with patch('terrarunt.terraform.config', mock_config):
                with patch.object(Path, 'cwd', return_value=terraform_files_setup):
                    operations = StackOperations(dry_run=False)
                    
                    result = operations.plan_all("dev")
                    
                    assert result is True
                    assert mock_subprocess.call_count == 4
    
    @mock_aws
    def test_init_all(self, terraform_files_setup, mock_subprocess, mock_config, mock_stack_manager):
        """Test init-all operation"""
        with patch('terrarunt.stacks.stack_manager', mock_stack_manager):
            with patch('terrarunt.terraform.config', mock_config):
                with patch.object(Path, 'cwd', return_value=terraform_files_setup):
                    operations = StackOperations(dry_run=False)
                    
                    result = operations.init_all("dev")
                    
                    assert result is True
                    assert mock_subprocess.call_count == 4