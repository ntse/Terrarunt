import argparse
from pathlib import Path
from terrarunt.terraform import apply_stack, plan_stack, destroy_stack, init_stack, bootstrap_backend, auto_bootstrap_backends, set_terraform_bin, resolve_stack_dependencies
from terrarunt.custom_logger import get_logger

logger = get_logger()

def main():
    parser = argparse.ArgumentParser(description="Terraform Stack Wrapper")
    parser.add_argument("--terraform-flags", nargs=argparse.REMAINDER, help="Additional flags to pass to Terraform (e.g. --reconfigure)")
    parser.add_argument("--env", required=True, help="Environment name (e.g. dev, prod)")
    parser.add_argument("--terraform-bin", help="Path to Terraform binary (e.g. tflocal, opentofu)")
    parser.add_argument("--version", action="store_true", help="Show version and exit")

    subparsers = parser.add_subparsers(dest="command")

    for cmd in ["apply", "plan", "destroy", "init"]:
        sp = subparsers.add_parser(cmd, help=f"{cmd.title()} a Terraform stack")
        sp.add_argument("--stack", required=True, help="Stack name to operate on")

    sp_boot = subparsers.add_parser("bootstrap", help="Bootstrap backend for one or more stacks")
    sp_boot.add_argument("--stack", help="Stack to bootstrap (optional)")

    sp_graph = subparsers.add_parser("graph", help="Resolve and print stack dependency order")

    sp_apply_all = subparsers.add_parser("apply-all", help="Apply all stacks in dependency order")
    sp_destroy_all = subparsers.add_parser("destroy-all", help="Destroy all stacks in reverse dependency order")
    sp_plan_all = subparsers.add_parser("plan-all", help="Plan all stacks in dependency order")
    sp_init_all = subparsers.add_parser("init-all", help="Init all stacks in dependency order")

    args = parser.parse_args()

    if args.terraform_bin:
        set_terraform_bin(args.terraform_bin)

    if args.version:
        print(__version__)
        return

    if args.command == "apply":
        apply_stack(args.env, args.stack, args.terraform_flags)
    elif args.command == "plan":
        plan_stack(args.env, args.stack, args.terraform_flags)
    elif args.command == "destroy":
        destroy_stack(args.env, args.stack, args.terraform_flags)
    elif args.command == "bootstrap":
        if args.stack:
            bootstrap_backend(args.env, args.stack)
        else:
            auto_bootstrap_backends(args.env)
    elif args.command == "graph":
        order, _ = resolve_stack_dependencies()
        for path in order:
            print(path)
    elif args.command == "apply-all":
        import concurrent.futures
        order, _ = resolve_stack_dependencies()
        logger.info("Applying stacks in parallel where possible")
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(apply_stack, args.env, Path(path).name, args.terraform_flags): Path(path).name for path in order
            }
            for future in concurrent.futures.as_completed(futures):
                stack_name = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    logger.error(f"Apply failed for {stack_name}: {exc}")
    elif args.command == "destroy-all":
        order, skip = resolve_stack_dependencies()
        for path in reversed(order):
            stack = Path(path).name
            if stack in skip:
                logger.info(f"Skipping {stack} during destroy (marked skip_when_destroying)")
                continue
            destroy_stack(args.env, stack)
    elif args.command == "init":
        init_stack(args.env, args.stack, args.terraform_flags)
    elif args.command == "init-all":
        order, _ = resolve_stack_dependencies()
        for path in order:
            stack = Path(path).name
            init_stack(args.env, stack, args.terraform_flags)
    elif args.command == "plan-all":
        import concurrent.futures
        order, _ = resolve_stack_dependencies()
        logger.info("Running plans in parallel for independent stacks")
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(plan_stack, args.env, Path(path).name, args.terraform_flags): Path(path).name for path in order
            }
            for future in concurrent.futures.as_completed(futures):
                stack_name = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    logger.error(f"Plan failed for {stack_name}: {exc}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
