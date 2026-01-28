"""
GetSecret Skill - Retrieves secrets from AWS Secrets Manager.
"""
import json
import boto3
from botocore.exceptions import ClientError
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class SecretResult:
    """Result object containing the retrieved secret."""
    success: bool
    value: Optional[str] = None
    error: Optional[str] = None


class GetSecret:
    """
    Retrieves secrets from AWS Secrets Manager.

    Usage:
        secret = GetSecret(region="us-west-2", secret_name="MySecret")
        result = secret.execute(json_key="db_url")
        if result.success:
            print(result.value)
    """

    def __init__(self, region: str, secret_name: str, profile_name: str = None):
        """
        Initialize GetSecret.

        Args:
            region: AWS region (e.g., 'us-west-2')
            secret_name: Name of the secret in AWS Secrets Manager
            profile_name: AWS profile name (optional)
        """
        self.region = region
        self.secret_name = secret_name
        self.profile_name = profile_name
        self._client = None

    @property
    def client(self):
        """Lazy-load boto3 Secrets Manager client."""
        if self._client is None:
            session = boto3.Session(
                profile_name=self.profile_name,
                region_name=self.region
            )
            self._client = session.client(service_name='secretsmanager')
        return self._client

    def execute(self, json_key: str = None) -> SecretResult:
        """
        Retrieve secret from AWS Secrets Manager.

        Args:
            json_key: If secret is JSON, extract this key's value.

        Returns:
            SecretResult: Contains success status and value or error.
        """
        logger.info(f"Fetching secret '{self.secret_name}'...")

        try:
            response = self.client.get_secret_value(SecretId=self.secret_name)

            if 'SecretString' not in response:
                return SecretResult(success=False, error="Secret is binary, expected string")

            secret_string = response['SecretString']

            if json_key:
                try:
                    secret_json = json.loads(secret_string)
                    if isinstance(secret_json, dict) and json_key in secret_json:
                        value = str(secret_json[json_key])
                        logger.info(f"Extracted key '{json_key}'")
                        return SecretResult(success=True, value=value)
                    else:
                        logger.warning(f"Key '{json_key}' not found, returning raw")
                except json.JSONDecodeError:
                    logger.warning("Secret is not JSON, returning raw string")

            return SecretResult(success=True, value=secret_string)

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                error_msg = f"Secret '{self.secret_name}' not found"
            elif error_code == 'AccessDeniedException':
                error_msg = f"Access denied to '{self.secret_name}'"
            else:
                error_msg = f"AWS error: {e}"
            logger.error(error_msg)
            return SecretResult(success=False, error=error_msg)
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(error_msg)
            return SecretResult(success=False, error=error_msg)


def create_skill():
    """Factory function using config values."""
    import config
    return GetSecret(
        region=config.AWS_REGION,
        secret_name=config.AWS_SECRET_NAME,
        profile_name=config.AWS_PROFILE
    )


if __name__ == "__main__":
    import config
    logging.basicConfig(level=logging.INFO)
    skill = create_skill()
    result = skill.execute(json_key=config.AWS_SECRET_JSON_KEY)
    if result.success and result.value:
        display = f"{result.value[:50]}..." if len(result.value) > 50 else result.value
        print(f"Secret: {display}")
    elif result.success:
        print("Secret retrieved but value is empty")
    else:
        print(f"Error: {result.error}")
