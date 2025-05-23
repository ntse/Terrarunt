# Terrarunt

A very light Terraform wrapper used to manage Terraform stacks.

## Install

```shell
pip install git+https://github.com/ntse/terrarunt.git
```

## How to use

Run Terrarunt the same way you would use ordinary terraform commands.

Terrarunt wraps and orchestrates Terraform commands per stack and runs common Terraform actions (init, plan, apply, destroy) in each stack, respecting dependency order and environment-specific configuration.

### CLI usage

```bash
# Apply a single stack
terrarunt --env dev apply --stack hello-world-api

# Apply all stacks with dependency awareness
terrarunt --env dev apply-all

# Destroy all stacks with dependency awareness
terrarunt --env dev destroy-all

# Bootstrap backend state - oidc and state-file
terrarunt --env dev bootstrap
```

### TODO

- [ ] Add `--dry-run` support for all commands (log actions, don't execute)
- [ ] Add `--only` and `--exclude` flags to filter stacks during `*-all` operations
- [ ] Show a post-run summary table (i.e.. success/failure per stack)
- [ ] Detect and warn about locked states (e.g. DynamoDB lock still held, native S3 locking)
- [ ] Validate `backend.tf` files are minimal (only declare the backend type)
- [ ] Warn when `.terraform/` folders exist but no `.tfstate` is present
- [ ] Improve formatting of `plan-all` output (grouped by stack name)
- [ ] Add `plan-diff` command to show changes since last plan (advanced)
- [ ] Add `terrarunt clean` command to remove `.terraform/` folders and locks
- [ ] Add `--confirm` prompt for `destroy-all`, with `--force` override