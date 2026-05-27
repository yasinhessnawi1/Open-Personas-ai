"""Domain exceptions for persona-core."""


class PersonaError(Exception):
    """Base exception for all persona-core errors."""


class SchemaVersionMismatchError(PersonaError):
    """Raised when a persona YAML's schema_version is not supported."""


class PersonaNotFoundError(PersonaError):
    """Raised when a persona cannot be found."""


class RuntimeWriteForbiddenError(PersonaError):
    """Raised when a write is attempted on a store that forbids runtime writes."""


class ToolNotAllowedError(PersonaError):
    """Raised when a tool call targets a tool not in the persona's allow-list."""


class ToolExecutionError(PersonaError):
    """Raised when a tool execution fails."""


class SandboxViolationError(PersonaError):
    """Raised when a file operation attempts to escape the sandbox."""
