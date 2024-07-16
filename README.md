# Terrarunt

A very light Terraform wrapper used to manage Terraform stacks.

## Install

```shell
git clone git@github.com:ntse/terrarunt.git
cd terrarunt
pip install .
```

## How to use

Run this in the same way that you would run ordinary `terraform` commands.

The Terraform `init`, `plan`, `apply`, `destroy` commands are run in each stack.

### Example

The below deploys every stack in the [devops-terraform-example-project](https://github.com/UKHSA-Internal/devops-terraform-example-project).

```shell
cd devops-terraform-example-project
terrarunt init
terrarunt plan -out tfplan
terrarunt apply tfplan
```
