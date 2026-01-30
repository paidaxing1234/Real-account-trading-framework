"""
Custom exception hierarchy for FactorLib.

This module defines all custom exceptions used throughout the library,
providing clear error messages and proper exception chaining.
"""


class FactorLibError(Exception):
    """Base exception for all FactorLib errors."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self):
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


# Data Errors
class DataError(FactorLibError):
    """Base exception for data-related errors."""
    pass


class DataLoadError(DataError):
    """Error loading data from source."""
    pass


class DataValidationError(DataError):
    """Data validation failed."""
    pass


class MissingColumnError(DataValidationError):
    """Required column is missing from DataFrame."""

    def __init__(self, columns: list, available: list = None):
        self.columns = columns
        self.available = available or []
        message = f"Missing required columns: {columns}"
        if available:
            message += f". Available: {available}"
        super().__init__(message, {'missing': columns, 'available': available})


class EmptyDataError(DataError):
    """Data is empty when non-empty data was expected."""
    pass


# Factor Errors
class FactorError(FactorLibError):
    """Base exception for factor computation errors."""
    pass


class FactorComputationError(FactorError):
    """Error during factor computation."""

    def __init__(self, factor_name: str, message: str, original_error: Exception = None):
        self.factor_name = factor_name
        self.original_error = original_error
        full_message = f"Factor '{factor_name}' computation failed: {message}"
        super().__init__(full_message, {'factor': factor_name})


class FactorValidationError(FactorError):
    """Factor validation failed."""
    pass


class InvalidFactorConfigError(FactorError):
    """Invalid factor configuration."""
    pass


# Backtest Errors
class BacktestError(FactorLibError):
    """Base exception for backtest errors."""
    pass


class BacktestValidationError(BacktestError):
    """Backtest validation failed."""
    pass


class InsufficientDataError(BacktestError):
    """Not enough data for backtest."""

    def __init__(self, required: int, available: int):
        message = f"Insufficient data: required {required}, got {available}"
        super().__init__(message, {'required': required, 'available': available})


# Database Errors
class DatabaseError(FactorLibError):
    """Base exception for database errors."""
    pass


class ConnectionError(DatabaseError):
    """Database connection failed."""
    pass


class QueryError(DatabaseError):
    """Database query failed."""
    pass


# Configuration Errors
class ConfigError(FactorLibError):
    """Configuration error."""
    pass


class InvalidConfigError(ConfigError):
    """Invalid configuration value."""
    pass


# IO Errors
class IOError(FactorLibError):
    """Base exception for IO errors."""
    pass


class FileNotFoundError(IOError):
    """File not found."""

    def __init__(self, path: str):
        super().__init__(f"File not found: {path}", {'path': path})


class FileWriteError(IOError):
    """Error writing to file."""
    pass


# Processing Errors
class ProcessingError(FactorLibError):
    """Base exception for processing errors."""
    pass


class MemoryError(ProcessingError):
    """Memory limit exceeded."""
    pass


class TimeoutError(ProcessingError):
    """Operation timed out."""
    pass
