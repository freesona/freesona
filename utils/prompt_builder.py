# utils/prompt_builder.py: Explicit, inspectable prompt assembly via independent context providers.
# Architecture per AGENTS.md Step 1 — PromptBuilder with independent context providers.

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("FreesonaBot")


# =============================================================================
# ContextBlock — Structured context contribution with metadata
# =============================================================================

class Mutability(Enum):
    """Mutability classification for a context block."""
    IMMUTABLE = "immutable"      # Canonical knowledge, persona definition
    MUTABLE = "mutable"          # User memory, character memory
    PLACEHOLDER = "placeholder"  # Not yet implemented


@dataclass
class ContextBlock:
    """
    A structured context contribution from a single provider.
    
    This replaces plain strings to support:
    - Inspection/debugging (see which provider contributed what)
    - Token accounting (estimate tokens per block)
    - Selective context management (include/exclude by mutability)
    - Explicit ordering (priority is part of the block)
    """
    name: str              # Provider identifier
    priority: int          # Assembly priority (lower = earlier)
    mutability: Mutability # Content mutability classification
    content: str           # The actual context text (could be empty)
    
    @property
    def is_empty(self) -> bool:
        """Whether this block contributes any content."""
        return not self.content.strip()
    
    def __len__(self) -> int:
        return len(self.content)


# =============================================================================
# ContextProvider Protocol
# =============================================================================

class ContextProvider(ABC):
    """
    Abstract base for a context provider. Each provider contributes one
    independent block of context to the final system prompt.
    
    Providers MUST NOT depend on other providers' output. Ordering is
    declared explicitly in PromptBuilder, not inferred from provider logic.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this provider (used in debug output)."""
        ...
    
    @property
    @abstractmethod
    def priority(self) -> int:
        """
        Assembly priority. Lower values appear earlier in the final prompt.
        Standard priorities (see PromptBuilder.DEFAULT_PROVIDERS):
            10  - System instructions
            20  - Persona definition
            30  - Conversation continuity (provider-specific interaction IDs)
            40  - Long-term user memory (facts)
            50  - Character memory (placeholder for Step 3)
            60  - Persona Knowledge Base (RAG)
        """
        ...
    
    @property
    @abstractmethod
    def mutability(self) -> Mutability:
        """Mutability classification of this provider's output."""
        ...
    
    @abstractmethod
    async def build(self, context: PromptBuildContext) -> ContextBlock:
        """
        Build this provider's context block.
        
        Args:
            context: Shared build context with all parameters needed by providers.
            
        Returns:
            A ContextBlock with metadata and content (empty string if no contribution).
        """
        ...


@dataclass
class PromptBuildContext:
    """
    Immutable(ish) context passed to all providers during prompt assembly.
    Contains all parameters that any provider might need.
    """
    # Core identity
    guild_id: Optional[int] = None
    channel_id: Optional[int] = None
    user_id: Optional[int] = None
    username: str = ""
    persona_id: str = ""
    
    # Persona data (raw fields, not pre-assembled)
    persona_data: dict = field(default_factory=dict)
    current_persona_assembled: str = ""
    
    # Feature flags
    apply_persona: bool = True
    kb_enabled: bool = True
    kb_top_k: int = 3
    
    # Raw user message (for KB retrieval)
    user_message: str = ""
    
    # Instruction prefix (e.g., "[username]: ")
    instruction_prefix: str = ""
    
    # Guild World accessor (for environmental context)
    # Injected by caller; defaults to null accessor for framework-agnostic operation
    guild_world_accessor: Any = None


# =============================================================================
# Provider Registry — Single source of truth for provider ordering
# =============================================================================

# This list is the ONE place where provider ordering is declared.
# New providers are added here; no changes to PromptBuilder logic needed.
DEFAULT_PROVIDERS: list[ContextProvider] = []  # Populated lazily to avoid circular imports


def _get_default_providers() -> list[ContextProvider]:
    """Lazily load default providers to avoid circular imports."""
    global DEFAULT_PROVIDERS
    if not DEFAULT_PROVIDERS:
        from utils.prompt_builder_providers import (
            SystemContextProvider,
            PersonaContextProvider,
            CanonContextProvider,
            ConversationHistoryProvider,
            UserMemoryProvider,
            CharacterMemoryProvider,
            GuildWorldContextProvider,
            PersonaKnowledgeBaseProvider,
        )
        DEFAULT_PROVIDERS = [
            SystemContextProvider(),           # 10 - System instructions (immutable)
            PersonaContextProvider(),          # 20 - Persona definition (immutable)
            CanonContextProvider(),            # 25 - Canon definition (immutable)
            ConversationHistoryProvider(),     # 30 - Conversation history (mutable)
            UserMemoryProvider(),              # 40 - User memory (mutable)
            CharacterMemoryProvider(),         # 50 - Character memory (mutable)
            GuildWorldContextProvider(),       # 55 - Guild world context (mutable)
            PersonaKnowledgeBaseProvider(),    # 60 - Persona KB (immutable)
        ]
    return DEFAULT_PROVIDERS


# =============================================================================
# PromptBuilder
# =============================================================================

@dataclass
class PromptBuilder:
    """
    Assembles the final system prompt from an ordered list of ContextProviders.
    
    Design goals:
    - Explicit ordering: providers sorted by priority, not implicit concatenation
    - Inspectability: `inspect()` returns each provider's ContextBlock with metadata
    - Testability: each provider can be unit-tested in isolation
    - Extensibility: new providers register via priority, no code changes to builder
    - Framework-agnostic: no Discord or provider-specific dependencies
    """
    providers: list[ContextProvider] = field(default_factory=list)
    
    def __post_init__(self):
        # Sort by priority (lower = earlier in prompt)
        self.providers.sort(key=lambda p: p.priority)
    
    @classmethod
    def with_default_providers(cls) -> PromptBuilder:
        """Create a PromptBuilder with the standard provider set from the registry."""
        return cls(providers=_get_default_providers())
    
    @classmethod
    def with_providers(cls, providers: list[ContextProvider]) -> PromptBuilder:
        """Create a PromptBuilder with a custom provider list (for testing/extension)."""
        return cls(providers=providers)
    
    async def build(self, context: PromptBuildContext) -> str:
        """
        Assemble the complete system prompt from all providers.
        
        Returns:
            The concatenated system prompt string (could be empty).
        """
        blocks = []
        for provider in self.providers:
            try:
                context_block = await provider.build(context)
                if not context_block.is_empty:
                    blocks.append(context_block.content)
            except Exception as e:
                logger.warning(f"Context provider '{provider.name}' failed: {e}")
                # Fail open — continue with other providers
        return "\n\n".join(blocks)
    
    async def inspect(self, context: PromptBuildContext) -> dict[str, ContextBlock]:
        """
        Return each provider's ContextBlock for debugging/inspection.
        
        Returns:
            Dict mapping provider name -> ContextBlock (with metadata).
        """
        result = {}
        for provider in self.providers:
            try:
                block = await provider.build(context)
                result[provider.name] = block
            except Exception as e:
                logger.warning(f"Context provider '{provider.name}' failed during inspect: {e}")
                result[provider.name] = ContextBlock(
                    name=provider.name,
                    priority=provider.priority,
                    mutability=provider.mutability,
                    content=f"[ERROR: {e}]"
                )
        return result
    
    def get_provider_names(self) -> list[str]:
        """Return provider names in assembly order."""
        return [p.name for p in self.providers]
    
    def get_provider_metadata(self) -> list[dict]:
        """Return metadata for all providers without building context."""
        return [
            {
                "name": p.name,
                "priority": p.priority,
                "mutability": p.mutability.value
            }
            for p in self.providers
        ]


# =============================================================================
# Default provider priorities (documented here as the single source of truth)
# =============================================================================

class ProviderPriority:
    """Standard priority values for built-in providers. Lower = earlier in prompt."""
    SYSTEM = 10
    PERSONA = 20
    CANON = 25
    CONVERSATION_HISTORY = 30
    USER_MEMORY = 40
    CHARACTER_MEMORY = 50
    GUILD_WORLD = 55  # Planned for Phase 3
    PERSONA_KNOWLEDGE_BASE = 60


# =============================================================================
# Backwards-compatible helper for generation.py migration
# =============================================================================

async def build_system_prompt(
    *,
    current_persona: str,
    persona_id: str,
    guild_id: Optional[int],
    channel_id: Optional[int] = None,
    user_id: Optional[int],
    username: str,
    apply_persona: bool,
    instruction_prefix: str = "",
    kb_enabled: bool = True,
    kb_top_k: int = 3,
    user_message: str = "",
    persona_data: Optional[dict] = None,
    guild_world_accessor: Any = None,
) -> str:
    """
    Backwards-compatible wrapper that replicates the exact current prompt assembly
    using the new PromptBuilder architecture.
    
    This function exists to make the migration in generation.py a one-line change
    while preserving byte-for-byte identical output.
    """
    from utils.persona import PERSONA_DATA as GLOBAL_PERSONA_DATA
    
    # Use provided persona_data or fall back to global (for backwards compat during transition)
    pd = persona_data if persona_data is not None else GLOBAL_PERSONA_DATA
    
    context = PromptBuildContext(
        guild_id=guild_id,
        channel_id=channel_id,
        user_id=user_id,
        username=username,
        persona_id=persona_id,
        persona_data=pd,
        current_persona_assembled=current_persona,
        apply_persona=apply_persona,
        kb_enabled=kb_enabled,
        kb_top_k=kb_top_k,
        user_message=user_message,
        instruction_prefix=instruction_prefix,
        guild_world_accessor=guild_world_accessor,
    )
    
    builder = PromptBuilder.with_default_providers()
    return await builder.build(context)


__all__ = [
    "ContextProvider",
    "ContextBlock",
    "Mutability",
    "PromptBuildContext",
    "PromptBuilder",
    "ProviderPriority",
    "build_system_prompt",
    "_get_default_providers",
]