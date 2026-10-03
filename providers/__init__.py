#!/usr/bin/env python3

from providers.base import BaseProvider
from providers.factory import get_provider

"""Provider package exposing the base provider interface and factory function.

The :class:`BaseProvider` defines the contract that all AI provider implementations
must satisfy, and :func:`get_provider` returns a concrete provider instance based on
configuration.
"""

__all__ = ["BaseProvider", "get_provider"]

