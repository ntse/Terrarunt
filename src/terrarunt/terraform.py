import subprocess
import json
import os
import shutil
import re
from pathlib import Path
from collections import defaultdict
from terrarunt.custom_logger import get_logger
from terrarunt.providers import aws

logger = get_logger()

BOOTSTRAP_STACKS = ["oidc", "state-file"]
TERRAFORM_BIN = os.getenv("TF_WRAPPER_BIN", "terraform")


def read_stack_dependencies(path: str) -> list[str]:
    path = Path(path)
    dep_file = path / "dependencies.json"
    config_file = path / "stack_config.json"

    if dep_file.exists():
        with open(dep_file) as f:
            data = json.load(f)
            return data.get("dependencies", {}).get("paths", [])

    if config_file.exists():
        with open(config_file) as f:
            data = json.load(f)
            return data.get("dependencies", {}).get("paths", [])

    return []


def set_terraform_bin(path):
    global TERRAFORM_BIN
    TERRAFORM_BIN = path
    logger.info(f"Terraform binary overridden: {TERRAFORM_BIN}")


def discover_stack_paths():
    cwd = Path.cwd()
    stack_paths = []
    for path in cwd.rglob("*/"):
        if len(path.relative_to(cwd).parts) <= 4:
            for name in ["stack_config.json", "dependencies.json"]:
                if (path / name).exists():
                    stack_paths.append(path)
                    break
    return stack_paths


def discover_stack_path(stack_name):
    for path in discover_stack_paths():
        if path.name == stack_name:
            return str(path)
    raise FileNotFoundError(
        f"Stack '{stack_name}' not found within 4 levels of current directory"
    )


def run_terraform_command(command_args, cwd, extra_flags=None):
    try:
        full_command = (
            [TERRAFORM_BIN] + command_args[1:]
            if command_args[0] == "terraform"
            else command_args
        )
        if extra_flags:
            full_command += extra_flags
        process = subprocess.Popen(
            full_command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in process.stdout:
            print(line, end="")
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, full_command)
    except subprocess.CalledProcessError:
        logger.error(f"Command failed: {' '.join(command_args)}")
        raise


def build_backend_config_args(backend_config):
    return [f"-backend-config={k}={v}" for k, v in backend_config.items()]


def get_tfvars_args(env, stack, stack_path):
    args = []
    cwd = Path.cwd()
    tfvars_candidates = [
        f"environment/{env}.tfvars",
        f"{cwd}/globals.tfvars",
        f"{stack_path}/tfvars/{env}.tfvars",
    ]

    for tfvars in tfvars_candidates:
        tfvars_path = Path(tfvars).resolve()
        if tfvars_path.exists():
            args.append(f"-var-file={str(tfvars_path)}")

    return args


def load_stack_config(stack_path):
    for name in ["stack_config.json", "dependencies.json"]:
        path = os.path.join(stack_path, name)
        if os.path.isfile(path):
            with open(path) as f:
                return json.load(f)
    return {}


def resolve_stack_dependencies():
    graph = defaultdict(list)
    name_to_path = {}
    skip_on_destroy = set()

    for path in discover_stack_paths():
        config = load_stack_config(path)
        name = path.name
        name_to_path[name] = str(path)

        # dependencies might be nested under "dependencies": { "paths": [...] }
        raw_deps = config.get("dependencies", [])
        if isinstance(raw_deps, dict):
            deps = raw_deps.get("paths", [])
        else:
            deps = raw_deps

        for dep in deps:
            graph[dep].append(name)

        if config.get("skip_when_destroying", False):
            skip_on_destroy.add(name)

    visited = set()
    result = []
    temp = set()

    def dfs(node):
        if node in temp:
            raise ValueError(f"Cycle detected involving: {node}")
        if node not in visited:
            temp.add(node)
            for neighbor in graph[node]:
                dfs(neighbor)
            temp.remove(node)
            visited.add(node)
            result.append(node)

    for node in name_to_path:
        if node not in visited:
            dfs(node)

    ordered_paths = [name_to_path[name] for name in reversed(result)]
    return ordered_paths, skip_on_destroy


def auto_bootstrap_backends(env):
    logger.info(
        f"Bootstrapping all known backend stacks: {', '.join(BOOTSTRAP_STACKS)}"
    )
    for stack in BOOTSTRAP_STACKS:
        try:
            bootstrap_backend(env, stack)
        except FileNotFoundError:
            logger.warning(f"Skipping missing bootstrap stack: {stack}")


def plan_stack(env, stack, extra_flags=None):
    stack_path = discover_stack_path(stack)
    tfvars_args = get_tfvars_args(env, stack, stack_path)
    logger.debug(f"Running {stack} plan with args: {tfvars_args}")
    run_terraform_command(
        [TERRAFORM_BIN, "plan"] + tfvars_args, cwd=stack_path, extra_flags=extra_flags
    )


def init_stack(env, stack, extra_flags=None):
    stack_path = discover_stack_path(stack)
    tfvars_args = get_tfvars_args(env, stack, stack_path)
    backend_file = os.path.join(stack_path, "backend.tf")
    is_tflocal = TERRAFORM_BIN.endswith("tflocal")

    with open(backend_file) as f:
        content = f.read()
    match = re.search(r'backend\s+"?([^"\s]+)', content)
    if not match:
        raise ValueError("No backend type found in the backend.tf file")

    backend_type = match.group(1)
    backend_args = []

    if backend_type == "s3":
        aws_info = aws()
        # Inject LocalStack-compatible backend config for tflocal
        if is_tflocal:
            logger.debug("Detected tflocal – injecting LocalStack backend overrides.")
            backend_args.extend(
                [
                    "-backend-config=access_key=fake",
                    "-backend-config=secret_key=fake",
                    "-backend-config=endpoint=http://localhost:4566",
                    "-backend-config=skip_credentials_validation=true",
                    "-backend-config=skip_metadata_api_check=true",
                    "-backend-config=skip_requesting_account_id=true",
                    "-backend-config=force_path_style=true",
                ]
            )

        # Common S3 backend config
        backend_args.extend(
            [
                f"-backend-config=bucket={aws_info.account_id}-{aws_info.region}-state",
                f"-backend-config=key={env}/{stack}/terraform.tfstate",
                f"-backend-config=region={aws_info.region}",
            ]
        )
        logger.debug(f"Init for {stack} with {backend_args}")

    elif backend_type == "local":
        logger.warning("Using local backend. Not recommended for team use.")

    else:
        raise ValueError(f"Backend type '{backend_type}' is not supported")

    run_terraform_command(
        [TERRAFORM_BIN, "init"] + backend_args + tfvars_args,
        cwd=stack_path,
        extra_flags=extra_flags,
    )


def bootstrap_backend(env, stack):
    stack_path = discover_stack_path(stack)
    tfvars_args = get_tfvars_args(env, stack, stack_path)
    backend_file = os.path.join(stack_path, "backend.tf")
    backend_backup = backend_file + ".bak"

    with open(backend_file) as f:
        content = f.read()
    match = re.search(r'backend\s+"?([^"\s]+)', content)
    if not match:
        raise ValueError("No backend type found in the backend.tf file")

    backend_type = match.group(1)
    backend_args = []

    if backend_type == "s3":
        aws_info = aws()
        backend_args.extend(
            [
                f"-backend-config=bucket={aws_info.account_id}-{aws_info.region}-state",
                f"-backend-config=key={env}/{stack}/terraform.tfstate",
                f"-backend-config=region={aws_info.region}",
            ]
        )
    elif backend_type == "local":
        logger.warning("Using local backend. Not recommended for team use.")
    else:
        raise ValueError(f"Backend type '{backend_type}' is not supported")

    if os.path.exists(backend_file):
        logger.info("Temporarily disabling remote backend...")
        shutil.move(backend_file, backend_backup)

    logger.info("Initializing Terraform in local mode...")
    run_terraform_command([TERRAFORM_BIN, "init", "-backend=false"], cwd=stack_path)

    logger.info("Applying bootstrap resources (local state)...")
    run_terraform_command(
        [TERRAFORM_BIN, "apply", "-auto-approve"] + tfvars_args, cwd=stack_path
    )

    if os.path.exists(backend_backup):
        logger.info("Restoring backend.tf...")
        shutil.move(backend_backup, backend_file)

    logger.info("Reinitializing Terraform with backend and migrating state...")
    run_terraform_command(
        [TERRAFORM_BIN, "init", "-migrate-state", "-force-copy"]
        + backend_args
        + tfvars_args,
        cwd=stack_path,
    )


def apply_stack(env, stack, extra_flags=None):
    stack_path = discover_stack_path(stack)
    tfvars_args = get_tfvars_args(env, stack, stack_path)
    logger.debug(f"Running {stack} apply with args: {tfvars_args}")
    run_terraform_command(
        [TERRAFORM_BIN, "apply", "-auto-approve"] + tfvars_args, cwd=stack_path
    )


def destroy_stack(env, stack, extra_flags=None):
    stack_path = discover_stack_path(stack)
    config = load_stack_config(stack_path)
    if config.get("skip_when_destroying", False):
        logger.info(f"Skipping destroy for {stack} (skip_when_destroying is true)")
        return
    tfvars_args = get_tfvars_args(env, stack, stack_path)
    run_terraform_command(
        [TERRAFORM_BIN, "destroy", "-auto-approve"] + tfvars_args,
        cwd=stack_path,
        extra_flags=extra_flags,
    )
