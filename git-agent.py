"""
Git Properties Update Agent
Updates properties in a .properties file within a Git repository.
Fetches property values from AWS Secrets Manager.
"""
import json
import os
from pathlib import Path
from git import Repo
from git.exc import GitCommandError
import boto3
from botocore.exceptions import ClientError

# Import configuration from central config file
import config


class AWSSecretsManager:
    """
    Agent to retrieve secrets from AWS Secrets Manager.
    """
    def __init__(self, region: str, secret_name: str, profile_name: str = None):
        """
        Args:
            region: AWS region
            secret_name: Name of the secret in AWS Secrets Manager
            profile_name: AWS profile name (None = use default credentials chain)
        """
        self.region = region
        self.secret_name = secret_name
        self.profile_name = profile_name
        self.client = None

    def _get_client(self):
        """
        Get or create boto3 Secrets Manager client.
        Uses a boto3 Session to support AWS profile specification.
        """
        if self.client is None:
            session = boto3.Session(
                profile_name=self.profile_name,
                region_name=self.region
            )
            self.client = session.client(service_name='secretsmanager')
        return self.client

    def get_secret(self, json_key: str = None) -> str:
        """
        Retrieve secret from AWS Secrets Manager and return as plain string.

        Args:
            json_key: If secret is JSON, extract this key's value.
                      If None, returns the raw secret string as-is.

        Returns:
            str: Secret value as plain string
        """
        print(f"Fetching secret '{self.secret_name}' from AWS Secrets Manager...")
        try:
            client = self._get_client()
            response = client.get_secret_value(SecretId=self.secret_name)

            if 'SecretString' in response:
                secret_string = response['SecretString']
                print(f"Secret retrieved successfully")

                # If json_key is specified, parse JSON and extract that key
                if json_key:
                    try:
                        secret_json = json.loads(secret_string)
                        if isinstance(secret_json, dict) and json_key in secret_json:
                            value = secret_json[json_key]
                            print(f"Extracted '{json_key}' from JSON secret")
                            return str(value)
                        else:
                            print(f"Warning: Key '{json_key}' not found in JSON, returning raw string")
                    except json.JSONDecodeError:
                        print(f"Warning: Secret is not JSON, returning raw string")

                # Return raw secret string as-is
                return secret_string
            else:
                raise Exception("Secret is binary, expected string")

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                raise Exception(f"Secret '{self.secret_name}' not found")
            elif error_code == 'AccessDeniedException':
                raise Exception(f"Access denied to secret '{self.secret_name}'")
            else:
                raise Exception(f"Failed to retrieve secret: {e}")


class GitPropertiesAgent:
    """
    Agent to update properties in a Git repository.
    Clones if repo doesn't exist, pulls if it does.
    """
    def __init__(self, repo_url: str, branch: str = "main", working_dir: str = None):
        """
        Args:
            repo_url: The Git repository URL
            branch: Branch to work on (default: main)
            working_dir: Directory to work in (default: current directory)
        """
        self.repo_url = repo_url
        self.branch = branch
        self.working_dir = working_dir or os.getcwd()
        self.repo = None

    def clone_or_pull_repository(self) -> str:
        """
        Clone the repository if not exists, or pull latest if already exists.

        Returns:
            str: Path to repository
        """
        git_dir = Path(self.working_dir) / ".git"

        if git_dir.exists():
            # Repository already exists - open and pull latest
            print(f"Repository already exists at: {self.working_dir}")
            try:
                self.repo = Repo(self.working_dir)

                # Fetch latest from remote
                print("Fetching latest changes from remote...")
                origin = self.repo.remote(name='origin')
                origin.fetch()

                # Checkout branch and pull with rebase to handle divergent branches
                print(f"Pulling latest changes for branch: {self.branch}")
                self.repo.git.checkout(self.branch)
                self.repo.git.pull('--rebase', 'origin', self.branch)

                print("Repository updated successfully!")
                return self.working_dir
            except GitCommandError as e:
                raise Exception(f"Failed to fetch/pull repository: {e}")
        else:
            # Repository doesn't exist - clone it
            print(f"Cloning repository to: {self.working_dir}")
            try:
                self.repo = Repo.clone_from(
                    self.repo_url,
                    self.working_dir,
                    branch=self.branch
                )
                print(f"Successfully cloned {self.repo_url}")
                return self.working_dir
            except GitCommandError as e:
                raise Exception(f"Failed to clone repository: {e}")

    def read_properties(self, file_path: str) -> dict:
        """
        Read a .properties file into a dictionary.

        Args:
            file_path: Relative path to properties file from repo root

        Returns:
            dict: Properties as key-value pairs
        """
        full_path = Path(self.working_dir) / file_path
        properties = {}

        if not full_path.exists():
            raise FileNotFoundError(f"Properties file not found: {full_path}")

        with open(full_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith('#') or line.startswith('!'):
                    continue

                # Split on first '=' or ':'
                for separator in ['=', ':']:
                    if separator in line:
                        key, value = line.split(separator, 1)
                        properties[key.strip()] = value.strip()
                        break

        return properties

    def write_properties(self, file_path: str, properties: dict,
                         preserve_comments: bool = True):
        """
        Write properties back to file, optionally preserving comments.

        Args:
            file_path: Relative path to properties file
            properties: Dictionary of properties to write
            preserve_comments: Keep original comments and structure
        """
        full_path = Path(self.working_dir) / file_path

        if preserve_comments and full_path.exists():
            self._update_preserving_structure(full_path, properties)
        else:
            with open(full_path, 'w', encoding='utf-8') as f:
                for key, value in properties.items():
                    f.write(f"{key}={value}\n")

    def _update_preserving_structure(self, full_path: Path, properties: dict):
        """
        Update properties while keeping comments and original structure.
        """
        lines = []
        updated_keys = set()

        with open(full_path, 'r', encoding='utf-8') as f:
            for line in f:
                original_line = line
                stripped = line.strip()

                # Keep comments and empty lines as-is
                if not stripped or stripped.startswith('#') or stripped.startswith('!'):
                    lines.append(original_line)
                    continue

                # Try to update property if it matches
                updated = False
                for separator in ['=', ':']:
                    if separator in stripped:
                        key = stripped.split(separator, 1)[0].strip()
                        if key in properties:
                            lines.append(f"{key}={properties[key]}\n")
                            updated_keys.add(key)
                            updated = True
                        break

                if not updated:
                    lines.append(original_line)

        # Add any new properties that weren't in original file
        for key, value in properties.items():
            if key not in updated_keys:
                lines.append(f"{key}={value}\n")

        with open(full_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

    def update_properties(self, file_path: str, updates: dict):
        """
        Update specific properties in a file.

        Args:
            file_path: Relative path to properties file
            updates: Dictionary of properties to update
        """
        print(f"Updating properties in {file_path}...")

        current = self.read_properties(file_path)

        for key, new_value in updates.items():
            old_value = current.get(key, "<NOT SET>")
            print(f"  {key}: '{old_value}' -> '{new_value}'")
            current[key] = new_value

        self.write_properties(file_path, current)
        print("Properties updated successfully!")

    def commit_and_push(self, commit_message: str,
                        username: str = None, token: str = None):
        """
        Commit changes and push to remote.

        Args:
            commit_message: Git commit message
            username: GitHub username (for authentication)
            token: GitHub personal access token (for authentication)
        """
        if self.repo is None:
            raise Exception("Repository not initialized. Call clone_or_pull_repository() first.")

        # Stage all changes
        self.repo.git.add(A=True)

        # Check if there are changes to commit
        if not self.repo.is_dirty() and not self.repo.untracked_files:
            print("No changes to commit.")
            return

        self.repo.index.commit(commit_message)
        print(f"Committed: {commit_message}")

        try:
            if username and token:
                remote_url = self.repo_url.replace(
                    "https://",
                    f"https://{username}:{token}@"
                )
                self.repo.git.remote("set-url", "origin", remote_url)

            origin = self.repo.remote(name='origin')
            origin.push()
            print("Changes pushed successfully!")
        except GitCommandError as e:
            raise Exception(f"Failed to push: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        return False


def main():
    """
    Main function demonstrating the agent.
    Uses configuration from config.py
    """
    working_dir = config.WORKING_DIR or os.getcwd()
    print(f"Working directory: {working_dir}")

    try:
        # Step 1: Fetch secrets from AWS Secrets Manager
        secrets_manager = AWSSecretsManager(
            region=config.AWS_REGION,
            secret_name=config.AWS_SECRET_NAME,
            profile_name=config.AWS_PROFILE
        )
        # Get secret as plain string (extracts from JSON if json_key is specified)
        secret_value = secrets_manager.get_secret(json_key=config.AWS_SECRET_JSON_KEY)
        print(f"Retrieved secret value successfully")

        # Step 2: Create properties update with target property key
        properties_updates = {config.TARGET_PROPERTY_KEY: secret_value}
        print(f"Will update: {config.TARGET_PROPERTY_KEY}")

        # Step 3: Update Git repository
        with GitPropertiesAgent(
            repo_url=config.REPO_URL,
            branch=config.BRANCH,
            working_dir=working_dir
        ) as agent:
            # Clone or pull the repository
            agent.clone_or_pull_repository()

            # Update the properties with values from AWS
            agent.update_properties(config.PROPERTIES_FILE, properties_updates)

            # Commit and push
            agent.commit_and_push(
                commit_message=config.COMMIT_MESSAGE,
                username=config.GITHUB_USERNAME,
                token=config.GITHUB_TOKEN
            )

            print("\nAgent completed successfully!")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Make sure the properties file exists in the repository.")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
