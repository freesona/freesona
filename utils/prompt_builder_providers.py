# utils/prompt_builder_providers.py: Concrete ContextProvider implementations.
# Each provider is independent and contributes one ContextBlock to the system prompt.

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from utils.prompt_builder import ContextProvider, PromptBuildContext, ProviderPriority, ContextBlock, Mutability

logger = logging.getLogger("FreesonaBot")


# =============================================================================
# System Context Provider (Priority 10) — IMMUTABLE
# =============================================================================

class SystemContextProvider(ContextProvider):
    """
    Provides system-level instructions. Currently, this extracts the
    `system_instructions` field from persona data, which is the highest-priority
    block in the assembled prompt.
    """
    
    @property
    def name(self) -> str:
        return "system"
    
    @property
    def priority(self) -> int:
        return ProviderPriority.SYSTEM
    
    @property
    def mutability(self) -> Mutability:
        return Mutability.IMMUTABLE
    
    async def build(self, context: PromptBuildContext) -> ContextBlock:
        if not context.apply_persona:
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        
        # Extract system_instructions from persona data
        system_instructions = context.persona_data.get("system_instructions", "").strip()
        if not system_instructions:
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        
        # Match current XML tag format from persona.py assemble_persona()
        content = f"<system_instructions>\n{system_instructions}\n</system_instructions>"
        return ContextBlock(
            name=self.name,
            priority=self.priority,
            mutability=self.mutability,
            content=content
        )


# =============================================================================
# Persona Context Provider (Priority 20) — IMMUTABLE
# =============================================================================

class PersonaContextProvider(ContextProvider):
    """
    Provides the core persona definition (role, background, beliefs, language).
    This corresponds to the non-system-instructions fields in persona.py's
    ASSEMBLY_ORDER.
    """
    
    @property
    def name(self) -> str:
        return "persona"
    
    @property
    def priority(self) -> int:
        return ProviderPriority.PERSONA
    
    @property
    def mutability(self) -> Mutability:
        return Mutability.IMMUTABLE
    
    async def build(self, context: PromptBuildContext) -> ContextBlock:
        if not context.apply_persona:
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        
        # Replicate the exact assembly from persona.py: ASSEMBLY_ORDER minus system_instructions
        # Current order: system_instructions, core_personality, background, beliefs, language
        # We only do the last four here (system_instructions handled by SystemContextProvider)
        field_order = ["core_personality", "background", "beliefs", "language"]
        xml_tags = {
            "core_personality": "role",
            "background": "background",
            "beliefs": "beliefs",
            "language": "language",
        }
        
        parts = []
        for field_name in field_order:
            tag = xml_tags[field_name]
            value = context.persona_data.get(field_name, "").strip()
            if value:
                parts.append(f"<{tag}>\n{value}\n</{tag}>")
        
        content = "\n\n".join(parts)
        return ContextBlock(
            name=self.name,
            priority=self.priority,
            mutability=self.mutability,
            content=content
        )


# =============================================================================
# Canon Context Provider (Priority 25) — IMMUTABLE
# =============================================================================

class CanonContextProvider(ContextProvider):
    """
    Provides modular, immutable canon blocks that explain the *why* behind 
    persona behavior. Replaces monolithic persona with composable canon fragments.
    
    Components (in assembly order):
    - Core Identity: Who the character fundamentally is (name, origin, nature)
    - Core Beliefs: Foundational convictions that drive decisions
    - Motivations: What the character wants and why
    - Behavioral Rules: Explicit constraints on behavior with reasoning
    - World Assumptions: What the character takes for granted about their world
    - Canon Explanations: Deep-dive "author's notes" on key character aspects
    
    Scope: Per persona_id (global, not guild/user/channel specific)
    
    Boundaries (per ADR-0003 Canonical Truth Invariant):
    - ONLY CanonContextProvider and PersonaKnowledgeBaseProvider may define 
      objective facts about the persona
    - MUST NOT contain conversation-specific state
    - MUST NOT contain user-specific facts (that's User Memory)
    - MUST NOT contain shared experiences (that's Character Memory)
    - MUST NOT contain environmental context (that's Guild World Context)
    - MUST NOT be generated by LLM — only authored by humans
    - Timeline divergence happens AROUND canon, never BY overwriting canon
    """
    
    @property
    def name(self) -> str:
        return "canon"
    
    @property
    def priority(self) -> int:
        return ProviderPriority.CANON
    
    @property
    def mutability(self) -> Mutability:
        return Mutability.IMMUTABLE
    
    async def build(self, context: PromptBuildContext) -> ContextBlock:
        if not context.apply_persona:
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        if not context.persona_id or not context.persona_id.strip():
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        
        # Import here to avoid circular imports
        from utils.canon import build_canon_context
        
        try:
            canon_block = await build_canon_context(
                persona_id=context.persona_id,
            )
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=canon_block
            )
        except Exception as e:
            logger.warning(f"CanonContextProvider failed: {e}")
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )


# =============================================================================
# Conversation History Provider (Priority 30) — MUTABLE
# =============================================================================

class ConversationHistoryProvider(ContextProvider):
    """
    Provides Freesona-owned conversation history (short-term memory).
    
    This replaces provider-specific continuity (Gemini Interactions API) with a
    unified, provider-agnostic conversation history that works identically across
    all providers. The ConversationManager stores recent messages, handles token
    budgets, expiration, and context assembly.
    
    Scope: Per (guild_id, channel_id, user_id) — each user has their own
    conversation thread within a channel, matching the previous Gemini behavior.
    """
    
    @property
    def name(self) -> str:
        return "conversation_history"
    
    @property
    def priority(self) -> int:
        return ProviderPriority.CONVERSATION_HISTORY
    
    @property
    def mutability(self) -> Mutability:
        return Mutability.MUTABLE
    
    async def build(self, context: PromptBuildContext) -> ContextBlock:
        if not context.apply_persona:
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        if not context.guild_id or not context.user_id:
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        
        # channel_id must be provided; if missing, we cannot scope the conversation
        channel_id = getattr(context, "channel_id", None)
        if channel_id is None:
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        
        try:
            from utils.conversation import build_conversation_context
            history = await build_conversation_context(
                guild_id=context.guild_id,
                channel_id=channel_id,
                user_id=context.user_id,
            )
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=history
            )
        except Exception as e:
            logger.warning(f"ConversationHistoryProvider failed: {e}")
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )


# =============================================================================
# User Memory Provider (Priority 40) — MUTABLE
# =============================================================================

class UserMemoryProvider(ContextProvider):
    """
    Provides long-term user facts (from SQLite via utils.memory).
    Replicates the exact format from memory.py:get_user_facts_prompt().
    """
    
    @property
    def name(self) -> str:
        return "user_memory"
    
    @property
    def priority(self) -> int:
        return ProviderPriority.USER_MEMORY
    
    @property
    def mutability(self) -> Mutability:
        return Mutability.MUTABLE
    
    async def build(self, context: PromptBuildContext) -> ContextBlock:
        if not context.apply_persona:
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        if not context.guild_id or not context.user_id:
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        
        # Import here to avoid circular imports
        from utils.memory import get_user_facts_prompt
        
        try:
            memory_block = await get_user_facts_prompt(
                context.guild_id,
                context.user_id,
                context.username
            )
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=memory_block
            )
        except Exception as e:
            logger.warning(f"UserMemoryProvider failed: {e}")
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )


# =============================================================================
# Character Memory Provider (Priority 50) — MUTABLE
# =============================================================================

class CharacterMemoryProvider(ContextProvider):
    """
    Provides persistent shared history between the persona and the user.
    
    Stores: promises, shared experiences, recurring jokes, unfinished activities,
    relationship progression, persistent decisions.
    
    Scope: Per (guild_id, user_id, persona_id) triple — persists across channels
    within the same guild (per ADR-0003 Multi-Guild Identity philosophy).
    
    Boundaries (per ADR-0003):
    - MUST NOT store canonical facts (that's PKB/Canon)
    - MUST NOT store user facts (that's User Memory)
    - MUST NOT store conversation history (that's ConversationManager)
    - MUST consume ConversationManager as source for extraction pipeline
    - MUST handle persona switches correctly (memories scoped to persona)
    """
    
    @property
    def name(self) -> str:
        return "character_memory"
    
    @property
    def priority(self) -> int:
        return ProviderPriority.CHARACTER_MEMORY
    
    @property
    def mutability(self) -> Mutability:
        return Mutability.MUTABLE
    
    async def build(self, context: PromptBuildContext) -> ContextBlock:
        if not context.apply_persona:
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        if not context.guild_id or not context.user_id or not context.persona_id:
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        
        # Import here to avoid circular imports
        from utils.character_memory import build_character_memory_context
        
        try:
            memory_block = await build_character_memory_context(
                guild_id=context.guild_id,
                user_id=context.user_id,
                persona_id=context.persona_id,
                username=context.username,
            )
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=memory_block
            )
        except Exception as e:
            logger.warning(f"CharacterMemoryProvider failed: {e}")
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )


# =============================================================================
# Guild World Context Provider (Priority 55) — MUTABLE
# =============================================================================

class GuildWorldContextProvider(ContextProvider):
    """
    Provides environmental context: the Discord guild as the character's "world".
    
    Supplies lightweight metadata about where the conversation is happening:
    - Guild (server) name
    - Channel name
    - Channel topic/description
    - Approximate member count (population)
    
    This is NOT memory — it's the current environment. Fetched fresh every request.
    No persistence, no history, no cross-guild awareness.
    
    Scope: Per (guild_id, channel_id) — request-scoped.
    
    Boundaries (per ADR-0003):
    - MUST NOT store history (that's Conversation/Character Memory)
    - MUST NOT store user facts (that's User Memory)
    - MUST NOT store canonical facts (that's Canon/PKB)
    - MUST NOT require special permissions beyond standard guild/channel intents
    - This is *environment*, not *memory*
    """
    
    @property
    def name(self) -> str:
        return "guild_world"
    
    @property
    def priority(self) -> int:
        return ProviderPriority.GUILD_WORLD
    
    @property
    def mutability(self) -> Mutability:
        return Mutability.MUTABLE
    
    async def build(self, context: PromptBuildContext) -> ContextBlock:
        if not context.apply_persona:
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        if not context.guild_id or not context.channel_id:
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        
        # Import here to avoid circular imports
        from utils.guild_world import build_guild_world_context, GuildWorldAccessor, NULL_ACCESSOR
        
        # Get accessor from context (injected by caller) or use null accessor
        accessor = getattr(context, "guild_world_accessor", None) or NULL_ACCESSOR
        
        try:
            world_context = await build_guild_world_context(
                guild_id=context.guild_id,
                channel_id=context.channel_id,
                accessor=accessor,
            )
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=world_context
            )
        except Exception as e:
            logger.warning(f"GuildWorldContextProvider failed: {e}")
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )


# =============================================================================
# Persona Knowledge Base Provider (Priority 60) — IMMUTABLE
# =============================================================================

class PersonaKnowledgeBaseProvider(ContextProvider):
    """
    Provides relevant canonical context from the Persona Knowledge Base (RAG).
    Replicates the exact format from generation.py:retrieve_knowledge_context().
    """
    
    @property
    def name(self) -> str:
        return "persona_knowledge_base"
    
    @property
    def priority(self) -> int:
        return ProviderPriority.PERSONA_KNOWLEDGE_BASE
    
    @property
    def mutability(self) -> Mutability:
        return Mutability.IMMUTABLE
    
    async def build(self, context: PromptBuildContext) -> ContextBlock:
        if not context.apply_persona:
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        if not context.kb_enabled:
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        if not context.persona_id or not context.persona_id.strip():
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        if not context.user_message or not context.user_message.strip():
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )
        
        # Import here to avoid circular imports
        from utils.chroma import query_knowledge
        
        try:
            # Run query off-thread to avoid blocking (same as retrieve_knowledge_context)
            entries = await asyncio.to_thread(
                query_knowledge,
                context.user_message,
                limit=context.kb_top_k,
                persona=context.persona_id
            )
            
            if not entries:
                return ContextBlock(
                    name=self.name,
                    priority=self.priority,
                    mutability=self.mutability,
                    content=""
                )
            
            # Format entries as context — EXACT replica of generation.py lines 326-360
            lines = ["Relevant Canonical Context"]
            for i, entry in enumerate(entries, 1):
                meta = entry.get("metadata", {})
                document = entry.get("document", "").strip()
                source = meta.get("source", "unknown")
                entry_type = meta.get("entry_type", "unknown")
                scene = meta.get("scene", "")
                speaker = meta.get("speaker", "")
                chapter = meta.get("chapter", "")
                timestamp = meta.get("timestamp", "")
                canon_level = meta.get("canon_level", "")
                
                context_parts = [f"{i}. {document}"]
                details = []
                if source and source != "unknown":
                    details.append(f"Source: {source}")
                if entry_type and entry_type != "unknown":
                    details.append(f"Type: {entry_type}")
                if scene:
                    details.append(f"Scene: {scene}")
                if speaker:
                    details.append(f"Speaker: {speaker}")
                if chapter:
                    details.append(f"Chapter: {chapter}")
                if timestamp:
                    details.append(f"Timestamp: {timestamp}")
                if canon_level:
                    details.append(f"Canon: {canon_level}")
                
                if details:
                    context_parts.append(f"   ({', '.join(details)})")
                
                lines.extend(context_parts)
            
            content = "\n".join(lines)
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=content
            )
            
        except Exception as e:
            logger.warning(f"PersonaKnowledgeBaseProvider failed: {e}")
            return ContextBlock(
                name=self.name,
                priority=self.priority,
                mutability=self.mutability,
                content=""
            )


__all__ = [
    "SystemContextProvider",
    "PersonaContextProvider",
    "CanonContextProvider",
    "ConversationHistoryProvider",
    "UserMemoryProvider",
    "CharacterMemoryProvider",
    "GuildWorldContextProvider",
    "PersonaKnowledgeBaseProvider",
]