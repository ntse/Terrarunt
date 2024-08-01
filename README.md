# Terrarunt

A very light Terraform wrapper used to manage Terraform stacks.

## Install

```shell
pip install git+https://github.com/ntse/terrarunt.git
```

## How to use

Run this in the same way that you would run ordinary `terraform` commands.

The Terraform `init`, `plan`, `apply`, `destroy`, `show`, `output`, `refresh`, `workspace` and `validate` commands are run in each stack. Every other command (e.g. `terrarunt version`) is passed directly to Terraform and run once from the current working directory.

### Examples

#### Terraform Apply

The below deploys every stack in the [devops-terraform-example-project](https://github.com/UKHSA-Internal/devops-terraform-example-project). It will create a `tfplan` file in each stack directory before applying the tfplan. This command does a `cd` into each directory, runs `terraform init` on each stack, followed by a `terraform plan -out tfplan` in each stack, finally followed by a `terraform apply tfplan` in each stack.

```shell
cd devops-terraform-example-project
aws-vault exec dev-uat -- terrarunt --environment=dev init -input=false
aws-vault exec dev-uat -- terrarunt --environment=dev plan -out tfplan
aws-vault exec dev-uat -- terrarunt --environment=dev apply -auto-approve -input=false tfplan
```

#### Terraform Destroy

This will run `terraform destroy` against each stack in the reverse order of how a `terrarunt apply` would run.

```shell
cd devops-terraform-example-project
aws-vault exec dev-uat -- terrarunt --environment=dev init -input=false
aws-vault exec dev-uat -- terrarunt --environment=dev destroy -auto-approve -input=false
```
