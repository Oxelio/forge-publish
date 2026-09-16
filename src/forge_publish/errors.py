class ForgePublishError(Exception):
    """Base exception for expected forge-publish errors."""


class ConfigurationError(ForgePublishError):
    """Raised when local forge-publish configuration is invalid."""


class PackageError(ForgePublishError):
    """Raised when a package cannot be validated or prepared."""
