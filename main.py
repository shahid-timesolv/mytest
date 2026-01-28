"""
Main orchestrator - Syncs database connection from AWS Secrets Manager to Git repository.
"""
import sys
import argparse
import logging
import config
from get_secret import create_skill as create_get_secret
from update_db_connection import create_skill as create_update_db

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def main(dry_run: bool = False, verbose: bool = False) -> int:
    """
    Main workflow:
    1. Get database connection string from AWS Secrets Manager
    2. Update the properties file in Git repository if value changed

    Args:
        dry_run: If True, show what would change without committing
        verbose: If True, enable debug logging

    Returns:
        int: Exit code (0 for success, 1 for failure)
    """
    setup_logging(verbose)

    logger.info("=" * 50)
    logger.info("DB Connection Sync")
    if dry_run:
        logger.info("[DRY RUN MODE - No changes will be made]")
    logger.info("=" * 50)

    # Step 1: Get secret from AWS
    logger.info("Step 1: Fetching secret from AWS Secrets Manager...")

    get_secret = create_get_secret()
    secret_result = get_secret.execute(json_key=config.AWS_SECRET_JSON_KEY)

    if not secret_result.success:
        logger.error(f"Failed to retrieve secret: {secret_result.error}")
        return 1

    if not secret_result.value:
        logger.error("Secret retrieved but value is empty")
        return 1

    logger.info("Secret retrieved successfully!")

    # Step 2: Update Git repository
    logger.info("Step 2: Updating Git repository...")

    update_db = create_update_db()
    update_result = update_db.execute(
        properties_file=config.PROPERTIES_FILE,
        property_key=config.DB_PROPERTY_KEY,
        new_value=secret_result.value,
        username=config.GITHUB_USERNAME,
        token=config.GITHUB_TOKEN,
        branch_prefix=config.BRANCH_PREFIX,
        dry_run=dry_run
    )

    if not update_result.success:
        logger.error(f"Failed to update: {update_result.error}")
        return 1

    # Summary
    logger.info("=" * 50)
    if dry_run:
        logger.info("Dry run completed - no changes made")
    elif update_result.updated:
        logger.info("Sync completed - changes committed!")
        logger.info(f"  Branch: {update_result.branch_name}")
    else:
        logger.info("Sync completed - no changes needed")
    logger.info("=" * 50)

    return 0


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Sync database connection from AWS Secrets Manager to Git repository'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Show what would change without making changes'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose (debug) logging'
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(main(dry_run=args.dry_run, verbose=args.verbose))
