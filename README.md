# Git Properties Agent

A Python agent that fetches secrets from AWS Secrets Manager and updates `.properties` files in a Git repository.

## Features

- Fetch secrets from AWS Secrets Manager
- Map AWS secret keys to properties file keys
- Clone a repository or fetch latest if already cloned
- Read and parse `.properties` files
- Update property values while preserving comments and structure
- Commit and push changes to remote

## Project Structure

```
mytest/
├── git-agent.py    # Main agent classes (AWSSecretsManager, GitPropertiesAgent)
├── config.py       # Central configuration file
├── README.md
└── test.properties # Example properties file
```

## Configuration

All settings are centralized in `config.py`:

### Git Configuration

| Setting | Description |
|---------|-------------|
| `REPO_URL` | Git repository URL |
| `BRANCH` | Branch to work on (default: main) |
| `PROPERTIES_FILE` | Path to the properties file |
| `COMMIT_MESSAGE` | Git commit message |
| `GITHUB_USERNAME` | GitHub username for authentication |
| `GITHUB_TOKEN` | GitHub personal access token |
| `WORKING_DIR` | Working directory (None = current directory) |

### AWS Secrets Manager Configuration

| Setting | Description |
|---------|-------------|
| `AWS_REGION` | AWS region (default: us-west-2) |
| `AWS_SECRET_NAME` | Name of the secret in AWS Secrets Manager |
| `AWS_PROFILE` | AWS profile name (None = default credentials chain) |
| `AWS_SECRET_JSON_KEY` | Key to extract from JSON secret (None = return raw string) |
| `TARGET_PROPERTY_KEY` | Property name in test.properties to update |

## AWS Secret Format

The secret in AWS Secrets Manager can be stored as:

**Plain string:**
```
jdbc:sqlserver://server:1433;databaseName=MyDB;user=admin;password=secret
```

**JSON format:**
```json
{
    "dev_url": "jdbc:sqlserver://server:1433;databaseName=MyDB;user=admin;password=secret"
}
```

Set `AWS_SECRET_JSON_KEY = "dev_url"` in config.py to extract from JSON.

## Installation

Install the required dependencies:

```bash
pip install GitPython boto3
```

## AWS Credentials

The agent uses boto3 which looks for AWS credentials in this order:
1. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
2. Shared credential file (`~/.aws/credentials`)
3. AWS config file with profile (`AWS_PROFILE`)
4. IAM role (when running on AWS EC2/ECS/Lambda)

## Usage

1. Create a secret in AWS Secrets Manager with your property values
2. Edit `config.py` with your configuration
3. Run the agent:

```bash
python git-agent.py
```

The agent will:
1. Fetch secrets from AWS Secrets Manager
2. Clone the repository (or pull latest if already exists)
3. Update the properties file
4. Commit and push the changes

## Classes

### AWSSecretsManager

| Method | Description |
|--------|-------------|
| `get_secret(json_key)` | Retrieve secret from AWS Secrets Manager |

### GitPropertiesAgent

| Method | Description |
|--------|-------------|
| `clone_or_pull_repository()` | Clone repo if not exists, or pull latest |
| `read_properties(file_path)` | Read properties file into a dictionary |
| `write_properties(file_path, properties)` | Write properties to file |
| `update_properties(file_path, updates)` | Update specific properties |
| `commit_and_push(message, username, token)` | Commit and push changes |

## Security Notes

- Store GitHub credentials in environment variables
- Use IAM roles when running on AWS infrastructure
- The agent supports `AWS_REGION`, `AWS_PROFILE`, `GITHUB_USERNAME`, and `GITHUB_TOKEN` environment variables
