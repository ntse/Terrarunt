"""
Custom exceptions for Terrarunt
"""


class TerraruntError(Exception):
    """Base exception for all Terrarunt errors"""
    pass


class StackNotFoundError(TerraruntError):
    """Raised when a stack cannot be found"""
    pass


class DependencyError(TerraruntError):
    """Raised when there are dependency issues"""
    pass


class TerraformError(TerraruntError):
    """Raised when Terraform commands fail"""
    def __init__(self, message, command=None, returncode=None, output=None):
        super().__init__(message)
        self.command = command
        self.returncode = returncode
        self.output = output


class AWSError(TerraruntError):
    """Raised when AWS operations fail"""
    pass


class BootstrapError(TerraruntError):
    """Raised when bootstrap operations fail"""
    pass


class ConfigurationError(TerraruntError):
    """Raised when configuration is invalid"""
    pass