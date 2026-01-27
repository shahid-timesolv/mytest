"""
Configuration file for Git Properties Agent
All configurable values are centralized here.
"""
import os

# Git Repository Configuration
REPO_URL = "https://github.com/shahid-timesolv/mytest.git"
BRANCH = "main"

# Properties File Configuration
PROPERTIES_FILE = "test.properties"

# AWS Secrets Manager Configuration
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")
AWS_SECRET_NAME = "TimeSolvDB/dev"  # Name of the secret in AWS Secrets Manager
AWS_PROFILE = os.environ.get("AWS_PROFILE", "migration")  # AWS profile name (None = default credentials chain)
AWS_SECRET_JSON_KEY = "dev_url"  # If secret is JSON, extract this key's value (None = return raw string as-is)

# Target property key - the property name in test.properties to update
TARGET_PROPERTY_KEY = "db.url"

# Git Commit Configuration
COMMIT_MESSAGE = "Update DB configuration properties"

# GitHub Credentials
# In production, use environment variables instead of hardcoded values
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "shahid-timesolv")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# Working Directory Configuration
# Set to None to use current working directory, or specify an absolute path
WORKING_DIR = None
