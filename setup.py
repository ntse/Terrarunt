# setup.py
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="terrarunt",
    version="2.0.0", 
    description="A simple Terraform wrapper for managing stacks",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ntse/terrarunt",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    classifiers=[
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.12",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "terrarunt=terrarunt.main:main",
        ],
    },
)