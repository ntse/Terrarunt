"""
Stack discovery and dependency management
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from collections import defaultdict
from .config import config
from .exceptions import StackNotFoundError, DependencyError
import os
logger = logging.getLogger(__name__)


@dataclass
class Stack:
    """Represents a Terraform stack"""
    name: str
    path: Path
    relative_path: str
    dependencies: List[str]
    skip_on_destroy: bool = False
    
    @classmethod
    def from_path(cls, path: Path) -> 'Stack':
        stack_file = path / config.stack_file_name
        relative_path = f"./{os.path.relpath(path, Path.cwd())}"

        try:
            with open(stack_file) as f:
                stack_config = json.load(f)
        except json.JSONDecodeError as e:
            raise DependencyError(f"Invalid JSON in {stack_file}: {e}")

        raw_dependencies = stack_config.get("dependencies", {"paths": []})
        normalized_dependencies = {
            "paths": [Path(dep).name for dep in raw_dependencies.get("paths", [])]
        }

        skip_on_destroy = stack_config.get("skip_on_destroy", False)

        return cls(
            name=path.name,
            path=path,
            relative_path=relative_path,
            dependencies=normalized_dependencies,
            skip_on_destroy=skip_on_destroy
        )


class StackManager:
    """Manages stack discovery and dependencies"""
    
    def __init__(self, root_path: Optional[Path] = None):
        self.root_path = root_path or Path.cwd()
        # TODO: Is the extra complexity added by having a cache worth the slight I/O improvement?
        self._stacks_cache: Optional[Dict[str, Stack]] = None
    
    def discover_stacks(self) -> Dict[str, Stack]:
        """Discover all stacks in the directory tree"""
        if self._stacks_cache is not None:
            return self._stacks_cache
        
        logger.info(f"Discovering stacks in {self.root_path}")
        stacks = {}
        
        for path in self.root_path.rglob("*/"):
            relative_path = path.relative_to(self.root_path)
            if len(relative_path.parts) > config.max_discovery_depth:
                continue
            
            # Check if this directory contains a stack
            stack_file = path / config.stack_file_name
            has_terraform = any([
                (path / "main.tf").exists(),
                (path / "backend.tf").exists(),
                stack_file.exists()
            ])
            
            if has_terraform:
                try:
                    stack = Stack.from_path(path)
                    stacks[stack.name] = stack
                    logger.debug(f"Found stack: {stack.name} at {stack.path}")
                except Exception as e:
                    logger.warning(f"Failed to load stack at {path}: {e}")
        
        logger.info(f"Discovered {len(stacks)} stacks: {list(stacks.keys())}")
        self._stacks_cache = stacks
        return stacks
    
    def get_stack(self, name: str) -> Stack:
        """Get a specific stack by name"""
        stacks = self.discover_stacks()
        if name not in stacks:
            available = ", ".join(stacks.keys())
            raise StackNotFoundError(f"Stack '{name}' not found. Available: {available}")
        return stacks[name]
    
    def resolve_dependencies(self) -> Tuple[List[Stack], Set[str]]:
        """
        Resolve stack dependencies and return ordered list of stacks.
        Returns: (ordered_stacks, skip_on_destroy_set)
        """
        stacks = self.discover_stacks()

        # Build dependency graph
        graph = defaultdict(list)
        skip_on_destroy = set()

        for stack in stacks.values():
            dep_paths = stack.dependencies.get("paths", [])
            for dep_name in dep_paths:
                if dep_name not in stacks:
                    logger.warning(f"Stack '{stack.name}' depends on unknown stack '{dep_name}'")
                    continue
                graph[dep_name].append(stack.name)

            if stack.skip_on_destroy:
                skip_on_destroy.add(stack.name)

        # Topological sort with cycle detection
        visited = set()
        temp_visited = set()
        result = []

        def visit(stack_name: str):
            if stack_name in temp_visited:
                raise DependencyError(f"Circular dependency detected involving: {stack_name}")

            if stack_name not in visited:
                temp_visited.add(stack_name)

                # Visit all dependents
                for dependent in graph[stack_name]:
                    visit(dependent)

                temp_visited.remove(stack_name)
                visited.add(stack_name)
                result.append(stack_name)

        for stack_name in stacks.keys():
            if stack_name not in visited:
                visit(stack_name)

        # Convert to Stack objects and reverse (dependencies first)
        ordered_stacks = [stacks[name] for name in reversed(result)]

        logger.info(f"Dependency order: {[s.name for s in ordered_stacks]}")

        return ordered_stacks, skip_on_destroy
    
    def get_independent_stacks(self) -> List[Stack]:
        """Get stacks that have no dependencies"""
        stacks = self.discover_stacks()
        return [stack for stack in stacks.values() if not stack.dependencies["paths"]]
    
    def clear_cache(self):
        """Clear the stacks cache"""
        self._stacks_cache = None
    
    def validate_stacks(self) -> List[str]:
        """Validate all stacks and return list of issues"""
        issues = []
        
        try:
            stacks = self.discover_stacks()
            
            # Check for dependency issues
            for stack in stacks.values():
                for dep_name in stack.dependencies["paths"]:
                    if dep_name not in stacks:
                        issues.append(f"Stack '{stack.name}' depends on unknown stack '{dep_name}'")
            
            # Check for required files
            for stack in stacks.values():
                if not (stack.path / "backend.tf").exists():
                    issues.append(f"Stack '{stack.name}' missing backend.tf")
                
                if not any((stack.path / f).exists() for f in ["main.tf", "*.tf"]):
                    logger.warning(f"Stack '{stack.name}' has no .tf files")
            
            # Try to resolve dependencies (will catch cycles)
            try:
                self.resolve_dependencies()
            except DependencyError as e:
                issues.append(str(e))
                
        except Exception as e:
            issues.append(f"Stack validation error: {e}")
        
        return issues


# Global stack manager instance
stack_manager = StackManager()