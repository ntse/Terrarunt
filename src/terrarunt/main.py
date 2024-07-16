#!/usr/bin/env python3
import os
import sys

from terrarunt.custom_logger import Logger
from terrarunt.dependencies import Graph  # noqa
from terrarunt.dependencies import process_stack_files
from terrarunt.terraform import run_command
from terrarunt.terraform import TerraformStack

logger = Logger(__name__)


def main():
    working_dir = os.getcwd()

    graph = process_stack_files(working_dir)
    sorted_nodes = graph.topological_sort()

    terraform_stacks = [TerraformStack(stack.name) for stack in sorted_nodes]

    if len(sys.argv) == 1:
        print(run_command(working_dir, ["--help"]))
        exit(127)

    args = sys.argv[2:]
    command = sys.argv[1]

    if command == "destroy":
        terraform_stacks.reverse()

    if command in ["init", "plan", "apply", "destroy"]:
        logger.info(
            f"Terraform {command} will run against {len(terraform_stacks)} Terraform stacks",
        )
        for stack in terraform_stacks:
            print(getattr(stack, f"tf_{command}")(args))
    else:
        print(run_command(working_dir, sys.argv[1::]))

    for stack in terraform_stacks:
        stack.cleanup_files()


if __name__ == "__main__":
    main()
