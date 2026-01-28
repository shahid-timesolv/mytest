"""
UpdateDbConnection Skill - Updates database connection in Git repository properties files.
"""
import os
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from git import Repo
from git.exc import GitCommandError
import logging

logger = logging.getLogger(__name__)


@dataclass
class UpdateResult:
    """Result object containing the update operation status."""
    success: bool
    error: Optional[str] = None
    updated: bool = False
    branch_name: Optional[str] = None


class UpdateDbConnection:
    """
    Updates database connection in Git repository properties files.

    Usage:
        updater = UpdateDbConnection(repo_url="https://github.com/user/repo.git")
        result = updater.execute(
            properties_file="config.properties",
            property_key="db.url",
            new_value="jdbc:mysql://localhost:3306/db"
        )
    """

    def __init__(self, repo_url: str, branch: str = "main", working_dir: str = None):
        """
        Initialize UpdateDbConnection.

        Args:
            repo_url: Git repository URL
            branch: Branch to work on (default: main)
            working_dir: Working directory (default: current directory)
        """
        self.repo_url = repo_url
        self.branch = branch
        self.working_dir = working_dir or os.getcwd()
        self.repo = None
        self._original_branch = None
        self._stash_created = False

    def _setup_auth(self, username: str, token: str) -> None:
        """Configure git credentials using environment variables (more secure)."""
        if username and token:
            os.environ['GIT_USERNAME'] = username
            os.environ['GIT_PASSWORD'] = token
            # Use credential helper that reads from env vars
            self.repo.config_writer().set_value(
                'credential', 'helper',
                '!f() { echo "username=$GIT_USERNAME"; echo "password=$GIT_PASSWORD"; }; f'
            ).release()

    def _cleanup_auth(self) -> None:
        """Clean up git credentials from environment."""
        os.environ.pop('GIT_USERNAME', None)
        os.environ.pop('GIT_PASSWORD', None)

    def _stash_changes(self) -> bool:
        """Stash any local changes before pull."""
        if self.repo.is_dirty(untracked_files=True):
            logger.info("Stashing local changes...")
            self.repo.git.stash('push', '-m', 'auto-stash-before-sync')
            self._stash_created = True
            return True
        return False

    def _restore_stash(self) -> None:
        """Restore stashed changes if any."""
        if self._stash_created:
            logger.info("Restoring stashed changes...")
            try:
                self.repo.git.stash('pop')
            except GitCommandError as e:
                logger.warning(f"Could not restore stash: {e}")
            self._stash_created = False

    def _clone_or_pull(self) -> str:
        """Clone repository if not exists, or pull latest changes."""
        git_dir = Path(self.working_dir) / ".git"

        if git_dir.exists():
            logger.info("Repository exists, pulling latest...")
            try:
                self.repo = Repo(self.working_dir)
                self._original_branch = self.repo.active_branch.name

                # Stash any local changes first
                self._stash_changes()

                origin = self.repo.remote(name='origin')
                origin.fetch()
                self.repo.git.checkout(self.branch)
                self.repo.git.pull('--rebase', 'origin', self.branch)
                return self.working_dir
            except GitCommandError as e:
                self._restore_stash()
                raise Exception(f"Failed to pull: {e}")
        else:
            logger.info("Cloning repository...")
            try:
                self.repo = Repo.clone_from(self.repo_url, self.working_dir, branch=self.branch)
                return self.working_dir
            except GitCommandError as e:
                raise Exception(f"Failed to clone: {e}")

    def _read_property(self, file_path: str, key: str) -> Optional[str]:
        """Read a specific property value from file."""
        full_path = Path(self.working_dir) / file_path
        if not full_path.exists():
            return None

        with open(full_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    k, v = line.split('=', 1)
                    if k.strip() == key:
                        return v.strip()
        return None

    def _update_property(self, file_path: str, key: str, new_value: str) -> bool:
        """Update a property in file while preserving structure."""
        full_path = Path(self.working_dir) / file_path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")

        lines = []
        updated = False

        with open(full_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith('#') and '=' in stripped:
                    k = stripped.split('=', 1)[0].strip()
                    if k == key:
                        lines.append(f"{key}={new_value}\n")
                        updated = True
                        continue
                lines.append(line)

        if not updated:
            lines.append(f"{key}={new_value}\n")

        with open(full_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        return True

    def _rollback(self, feature_branch: str = None) -> None:
        """Rollback changes on failure."""
        logger.warning("Rolling back changes...")
        try:
            if self.repo:
                # Discard uncommitted changes
                self.repo.git.checkout('--', '.')

                # Return to original branch
                if self._original_branch:
                    self.repo.git.checkout(self._original_branch)
                elif self.branch:
                    self.repo.git.checkout(self.branch)

                # Delete feature branch if created
                if feature_branch:
                    try:
                        self.repo.git.branch('-D', feature_branch)
                        logger.info(f"Deleted branch: {feature_branch}")
                    except GitCommandError:
                        pass

                self._restore_stash()
        except Exception as e:
            logger.error(f"Rollback failed: {e}")

    def _commit_and_push(self, message: str, username: str = None,
                         token: str = None, branch_prefix: str = "db-update") -> str:
        """Create feature branch, commit, merge to main, and push."""
        if self.repo is None:
            raise Exception("Repository not initialized")

        self.repo.git.add(A=True)

        if not self.repo.is_dirty():
            logger.info("No changes to commit")
            return None

        feature_branch = None

        try:
            # Setup authentication via environment (more secure)
            if username and token:
                remote_url = self.repo_url.replace("https://", f"https://{username}:{token}@")
                self.repo.git.remote("set-url", "origin", remote_url)

            # Create feature branch
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            feature_branch = f"{branch_prefix}-{timestamp}"
            logger.info(f"Creating branch: {feature_branch}")
            self.repo.git.checkout('-b', feature_branch)

            # Commit
            self.repo.index.commit(message)
            logger.info(f"Committed: {message}")

            # Push feature branch
            origin = self.repo.remote(name='origin')
            origin.push(feature_branch)
            logger.info(f"Pushed branch: {feature_branch}")

            # Merge to main
            self.repo.git.checkout(self.branch)

            try:
                self.repo.git.merge(feature_branch, '--no-edit')
            except GitCommandError as e:
                if 'CONFLICT' in str(e):
                    logger.error("Merge conflict detected, aborting merge")
                    self.repo.git.merge('--abort')
                    raise Exception("Merge conflict - manual resolution required")
                raise

            origin.push(self.branch)
            logger.info(f"Merged to {self.branch} and pushed")

            return feature_branch

        except GitCommandError as e:
            self._rollback(feature_branch)
            raise Exception(f"Failed to commit/push: {e}")

    def execute(self, properties_file: str, property_key: str, new_value: str,
                username: str = None, token: str = None,
                branch_prefix: str = "db-update", dry_run: bool = False) -> UpdateResult:
        """
        Update database connection property in Git repository.

        Args:
            properties_file: Path to properties file
            property_key: Property key to update (e.g., 'db.url')
            new_value: New value for the property
            username: GitHub username
            token: GitHub token
            branch_prefix: Prefix for feature branch
            dry_run: If True, show what would change without committing

        Returns:
            UpdateResult: Contains success status and details.
        """
        logger.info("Starting update...")
        logger.info(f"File: {properties_file}, Key: {property_key}")

        try:
            # Clone or pull
            self._clone_or_pull()

            # Check current value
            current_value = self._read_property(properties_file, property_key)
            if current_value == new_value:
                logger.info("Value unchanged, skipping")
                self._restore_stash()
                return UpdateResult(success=True, updated=False)

            if dry_run:
                logger.info(f"[DRY RUN] Would update '{property_key}':")
                logger.info(f"  Current: {current_value}")
                logger.info(f"  New: {new_value}")
                self._restore_stash()
                return UpdateResult(success=True, updated=False)

            logger.info("Updating value...")

            # Update property
            self._update_property(properties_file, property_key, new_value)

            # Commit and push
            commit_msg = f"Update {property_key} in {properties_file}"
            branch_name = self._commit_and_push(
                message=commit_msg,
                username=username,
                token=token,
                branch_prefix=branch_prefix
            )

            self._restore_stash()
            logger.info("Update completed!")
            return UpdateResult(success=True, updated=True, branch_name=branch_name)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error: {error_msg}")
            self._restore_stash()
            return UpdateResult(success=False, error=error_msg)


def create_skill():
    """Factory function using config values."""
    import config
    return UpdateDbConnection(
        repo_url=config.REPO_URL,
        branch=config.BRANCH,
        working_dir=config.WORKING_DIR
    )


if __name__ == "__main__":
    import config
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    skill = create_skill()
    result = skill.execute(
        properties_file=config.PROPERTIES_FILE,
        property_key=config.DB_PROPERTY_KEY,
        new_value="test_value",
        username=config.GITHUB_USERNAME,
        token=config.GITHUB_TOKEN,
        branch_prefix=config.BRANCH_PREFIX,
        dry_run=True  # Safe default for testing
    )
    print(f"Success: {result.success}, Updated: {result.updated}")
