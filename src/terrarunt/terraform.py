import os
import re
import shutil
import subprocess
import sys

import terrarunt.providers
from terrarunt.custom_logger import Logger

logger = Logger(__name__)


class TerraformStack:
    def __init__(self, directory, environment):
        self.directory = directory
        self.environment = environment
        self.files_copied = []
        self.copy_files_to_stack()
        self.name = os.path.basename(directory)
        self.variable_files = self.find_variable_files()
        self.backend_type = self.determine_backend_type()

    def find_variable_files(self):
        return (
            self._find_env_var_files()
            + self._find_app_var_files()
            + self._find_global_files()
        )

    def _find_global_files(self):
        return [f"-var-file={os.path.abspath('globals.tfvars')}"]

    def _find_app_var_files(self):
        tfvars = os.path.join(
            self.directory,
            "tfvars",
            f"{self.name}-{self.environment}.tfvars",
        )
        json = os.path.join(
            self.directory,
            "tfvars",
            f"{self.name}-{self.environment}.tfvars.json",
        )

        if os.path.isfile(tfvars):
            return [f"-var-file={os.path.abspath(tfvars)}"]
        elif os.path.isfile(json):
            return [f"-var-file={os.path.abspath(json)}"]

        return []

    def _find_env_var_files(self):
        tfvars = os.path.join("environment", f"{self.environment}.tfvars")
        json = os.path.join("environment", f"{self.environment}.tfvars.json")

        if os.path.isfile(tfvars):
            return [f"-var-file={os.path.abspath(tfvars)}"]
        elif os.path.isfile(json):
            return [f"-var-file={os.path.abspath(json)}"]

        return []

    def determine_backend_type(self):
        with open(os.path.join(self.directory, "backend.tf")) as f:
            content = f.read()
        match = re.search(r'backend\s+"?([^"\s]+)', content)
        if match:
            return match.group(1)
        else:
            raise ValueError("No backend type found in the backend.tf file")

    def cleanup_files(self):
        for file_name in self.files_copied:
            try:
                os.remove(file_name)
            except FileNotFoundError:
                pass

    def copy_files_to_stack(self):
        files_to_copy = ["providers.tf", "terraform.tf", "backend.tf"]
        current_dir = os.getcwd()

        destination_dir = os.path.join(current_dir, self.directory)

        for file_name in files_to_copy:
            source_file = os.path.join(current_dir, file_name)
            destination_file = os.path.join(destination_dir, file_name)

            if not os.path.exists(destination_file):
                try:
                    shutil.copyfile(source_file, destination_file)
                    print(f"Copied {file_name} to {destination_dir}")
                    self.files_copied.append(destination_file)
                except FileNotFoundError:
                    print(f"Error: {source_file} does not exist.")
                    sys.exit(1)
            else:
                logger.debug(
                    f"File {file_name} already exists in {self.directory}",
                )

    def tf_init(self, args=[]):
        command = ["init"]
        if self.backend_type is None:
            self.determine_backend_type()
            self.tf_init()
        elif self.backend_type == "s3":
            aws = terrarunt.providers.aws()
            command.extend(
                [
                    f"-backend-config=bucket={aws.account_id}-{aws.region}-state",
                    f"-backend-config=key={self.environment}/{self.name}/terraform.tfstate",
                    f"-backend-config=region={aws.region}",
                ],
            )
        elif self.backend_type == "local":
            logger.warn("Using local type backend. This is not advised.")
        else:
            raise ValueError(
                f"Backend type {self.backend_type} is not supported",
            )
        return run_command(self.directory, command, args)

    def tf_plan(self, args=[]):
        command = ["plan"] + self.variable_files
        return run_command(self.directory, command, args)

    def tf_validate(self, args=[]):
        command = ["validate"]
        return run_command(self.directory, command, args)

    def tf_refresh(self, args=[]):
        command = ["refresh"]
        return run_command(self.directory, command, args)

    def tf_workspace(self, args=[]):
        command = ["workspace"]
        return run_command(self.directory, command, args)

    def tf_output(self, args=[]):
        command = ["output"]
        return run_command(self.directory, command, args)

    def tf_show(self, args=[]):
        command = ["show"]
        return run_command(self.directory, command, args)

    def tf_apply(self, args=[]):
        command = ["apply"]
        if not os.path.isfile(args[-1]) and args[-1] != "tfplan":
            command.extend(self.variable_files)
        return run_command(self.directory, command, args)

    def tf_destroy(self, args=[]):
        command = ["destroy"]
        if not os.path.isfile(args[-1]):
            command.extend(self.variable_files)
        return run_command(self.directory, command, args)


def run_command(directory, command, args=[]):
    original_directory = os.getcwd()
    command.insert(0, "terraform")
    full_command = command + args
    os.chdir(directory)
    try:
        result = subprocess.run(
            full_command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(e.stderr)
        exit(1)
    os.chdir(original_directory)
    return result.stdout
