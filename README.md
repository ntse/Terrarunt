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

### Examples

#### Terraform Apply

The below deploys every stack in the [devops-terraform-example-project](https://github.com/UKHSA-Internal/devops-terraform-example-project). It will create a `tfplan` file in each stack directory before applying the tfplan.

```shell
cd devops-terraform-example-project
terrarunt init
terrarunt plan -out tfplan
terrarunt apply tfplan
```

#### Terraform Destroy

This will run `terraform destroy` against each stack in the reverse order of how a `terrarunt apply` would run.

```shell
cd devops-terraform-example-project
terrarunt init
terrarunt destroy -auto-approve -input=false
```
