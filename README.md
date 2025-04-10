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