#!/usr/bin/env python3
import argparse
import os

from terrarunt.custom_logger import Logger
from terrarunt.dependencies import Graph  # noqa
from terrarunt.dependencies import process_stack_files
from terrarunt.terraform import run_command
from terrarunt.terraform import TerraformStack

logger = Logger(__name__)


def main():
    working_dir = os.getcwd()

    parser = argparse.ArgumentParser(description="Terraform wrapper script")
    parser.add_argument(
        "command",
        help="Terraform command to execute",
    )
    parser.add_argument(
        "--environment",
        help="The name of the environment to use for variable lookups, etc",
    )
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Additional arguments for the Terraform command",
    )

    parsed_args = parser.parse_args()
    command = parsed_args.command
    args = parsed_args.args
    environment = parsed_args.environment

    graph = process_stack_files(working_dir)
    sorted_nodes = graph.topological_sort()

    terraform_stacks = [
        TerraformStack(
            stack.name, environment=environment,
        ) for stack in sorted_nodes
    ]

    if command == "destroy" or "-destroy" in args:
        # If we're going to destroy a stack, we should do it backwards so avoid breaking depenencies.
        terraform_stacks.reverse()

    function_name = f"tf_{command}"

    if hasattr(TerraformStack, function_name) and callable(
        getattr(TerraformStack, function_name),
    ):
        logger.info(
            f"Terraform {command} will run against {len(terraform_stacks)} Terraform stacks",
        )
        for stack in terraform_stacks:
            print(f"Output from {stack.name}: ")
            print(getattr(stack, function_name)(args))
    else:
        print(run_command(working_dir, [command], args))

    for stack in terraform_stacks:
        stack.cleanup_files()


if __name__ == "__main__":
    main()
