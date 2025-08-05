"""
Terrarunt CLI - A simple Terraform wrapper for managing stacks
"""
import sys
import argparse
import logging
from typing import Optional

from .config import config
from .stacks import stack_manager
from .terraform import StackOperations
from .bootstrap import BootstrapManager, BootstrapStage
from .exceptions import TerraruntError, StackNotFoundError, DependencyError, TerraformError

logger = logging.getLogger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser"""
    parser = argparse.ArgumentParser(
        description="Terrarunt - A simple Terraform wrapper for managing stacks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  terrarunt --env dev apply --stack my-app
  terrarunt --env prod apply-all
  terrarunt --env dev bootstrap
  terrarunt --env dev destroy-all --confirm
  terrarunt list-stacks
        """
    )
    
    # Global options
    parser.add_argument("--env", required=True, help="Environment (e.g., dev, staging, prod)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without executing")
    parser.add_argument("--terraform-bin", help="Path to terraform binary")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Single stack commands
    for cmd in ["init", "plan", "apply", "destroy"]:
        sp = subparsers.add_parser(cmd, help=f"{cmd.title()} a single stack")
        sp.add_argument("--stack", required=True, help="Stack name")
        sp.add_argument("--tf-args", nargs="*", help="Additional Terraform arguments")
    
    # Bulk commands
    for cmd in ["init-all", "plan-all", "apply-all", "destroy-all"]:
        sp = subparsers.add_parser(cmd, help=f"{cmd.replace('-', ' ').title()}")
        sp.add_argument("--tf-args", nargs="*", help="Additional Terraform arguments")
        if cmd == "destroy-all":
            sp.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")
    
    # Bootstrap command
    bootstrap_parser = subparsers.add_parser("bootstrap", help="Bootstrap backend infrastructure")
    bootstrap_parser.add_argument("--status", action="store_true", help="Show bootstrap status only")
    
    # Utility commands
    subparsers.add_parser("list-stacks", help="List all discovered stacks")
    subparsers.add_parser("validate", help="Validate stack configurations")
    subparsers.add_parser("graph", help="Show dependency graph")
    
    return parser


def handle_single_stack_command(args, operations: StackOperations) -> int:
    """Handle single stack commands (init, plan, apply, destroy)"""
    try:
        command_map = {
            "init": operations.init_stack,
            "plan": operations.plan_stack,
            "apply": operations.apply_stack,
            "destroy": operations.destroy_stack,
        }
        
        command_func = command_map[args.command]
        
        if args.command in ["plan", "apply", "destroy"]:
            success = command_func(args.env, args.stack, args.tf_args)
        else:  # init
            success = command_func(args.env, args.stack)
        
        return 0 if success else 1
        
    except StackNotFoundError as e:
        logger.error(str(e))
        return 1
    except TerraformError as e:
        logger.error(f"Terraform error: {e}")
        return 1


def handle_bulk_command(args, operations: StackOperations) -> int:
    """Handle bulk commands (init-all, plan-all, apply-all, destroy-all)"""
    try:
        if args.command == "destroy-all" and not args.confirm:
            # Confirmation prompt for destroy-all
            ordered_stacks, skip_set = stack_manager.resolve_dependencies()
            destroy_stacks = [s for s in reversed(ordered_stacks) if s.name not in skip_set]
            
            print(f"This will destroy {len(destroy_stacks)} stacks:")
            for stack in destroy_stacks:
                print(f"  - {stack.name}")
            
            if skip_set:
                print(f"Skipping: {', '.join(skip_set)} (skip_on_destroy=true)")
            
            response = input("\nAre you sure? [y/N]: ")
            if response.lower() not in ['y', 'yes']:
                print("Cancelled")
                return 0
        
        command_map = {
            "init-all": operations.init_all,
            "plan-all": operations.plan_all,
            "apply-all": operations.apply_all,
            "destroy-all": operations.destroy_all,
        }
        
        command_func = command_map[args.command]
        success = command_func(args.env, args.tf_args)
        
        return 0 if success else 1
        
    except DependencyError as e:
        logger.error(f"Dependency error: {e}")
        return 1
    except TerraformError as e:
        logger.error(f"Terraform error: {e}")
        return 1


def handle_bootstrap_command(args) -> int:
    """Handle bootstrap command"""
    try:
        bootstrap_manager = BootstrapManager(args.dry_run)
        
        if args.status:
            bootstrap_manager.show_status(args.env)
            return 0
        
        # Check if bootstrap is needed
        current_stage = bootstrap_manager.get_current_stage(args.env)
        
        if current_stage == BootstrapStage.COMPLETED:
            print("Bootstrap is already complete")
            return 0
        
        print(f"Starting bootstrap from stage: {current_stage.value}")
        result = bootstrap_manager.bootstrap(args.env)
        
        if result.success:
            print(result.message)
            return 0
        else:
            print(result.message)
            if result.error:
                logger.error(f"Error details: {result.error}")
            return 1
            
    except Exception as e:
        logger.error(f"Bootstrap error: {e}")
        return 1


def handle_list_stacks_command() -> int:
    """Handle list-stacks command"""
    try:
        stacks = stack_manager.discover_stacks()
        
        if not stacks:
            print("No stacks found")
            return 0
        
        print(f"Found {len(stacks)} stacks:")
        print()
        
        for stack_name, stack in sorted(stacks.items()):
            deps = f"depends on: {', '.join(stack.dependencies)}" if stack.dependencies else "no dependencies"
            skip_marker = " [skip on destroy]" if stack.skip_on_destroy else ""
            
            print(f"  {stack_name:20s} {deps}{skip_marker}")
            print(f"    Path: {stack.path}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error listing stacks: {e}")
        return 1


def handle_validate_command() -> int:
    """Handle validate command"""
    try:
        issues = stack_manager.validate_stacks()
        
        if not issues:
            print("All stacks are valid")
            return 0
        else:
            print("Validation issues found:")
            for issue in issues:
                print(f"  - {issue}")
            return 1
            
    except Exception as e:
        logger.error(f"Validation error: {e}")
        return 1


def handle_graph_command() -> int:
    """Handle graph command"""
    try:
        ordered_stacks, skip_set = stack_manager.resolve_dependencies()
        
        print("Stack Dependency Graph:")
        print("=" * 40)
        
        for i, stack in enumerate(ordered_stacks, 1):
            skip_marker = " (skip on destroy)" if stack.name in skip_set else ""
            deps_info = f" <- {', '.join(stack.dependencies)}" if stack.dependencies else ""
            
            print(f"{i:2d}. {stack.name}{skip_marker}{deps_info}")
        
        return 0
        
    except DependencyError as e:
        logger.error(f"Dependency error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Error generating graph: {e}")
        return 1


def main() -> int:
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Override terraform binary if specified
    if args.terraform_bin:
        config.terraform_bin = args.terraform_bin
    
    try:
        # Handle commands
        if args.command in ["init", "plan", "apply", "destroy"]:
            operations = StackOperations(args.dry_run)
            return handle_single_stack_command(args, operations)
        
        elif args.command in ["init-all", "plan-all", "apply-all", "destroy-all"]:
            operations = StackOperations(args.dry_run)
            result = handle_bulk_command(args, operations)
            
            # Show dry run summary if applicable
            if args.dry_run:
                operations.runner.show_dry_run_summary()
            
            return result
        
        elif args.command == "bootstrap":
            return handle_bootstrap_command(args)
        
        elif args.command == "list-stacks":
            return handle_list_stacks_command()
        
        elif args.command == "validate":
            return handle_validate_command()
        
        elif args.command == "graph":
            return handle_graph_command()
        
        else:
            parser.print_help()
            return 1
    
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 130
    except TerraruntError as e:
        logger.error(str(e))
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())