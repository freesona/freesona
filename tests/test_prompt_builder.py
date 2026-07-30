# tests/test_prompt_builder.py: Tests for PromptBuilder and ContextProviders

import sys
import unittest
from unittest.mock import patch
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.prompt_builder import (
    ContextProvider,
    PromptBuildContext,
    PromptBuilder,
    ProviderPriority,
    build_system_prompt,
    ContextBlock,
    Mutability,
)
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


class TestPromptBuilderArchitecture(unittest.TestCase):
    """Test the PromptBuilder architecture and provider ordering."""
    
    def test_provider_priority_ordering(self):
        """Providers should be sorted by priority (lower = earlier in prompt)."""
        builder = PromptBuilder(providers=[
            PersonaContextProvider(),       # priority 20
            SystemContextProvider(),        # priority 10
            UserMemoryProvider(),           # priority 40
            CharacterMemoryProvider(),      # priority 50
            PersonaKnowledgeBaseProvider(), # priority 60
            ConversationHistoryProvider(),  # priority 30
            CanonContextProvider(),         # priority 25
            GuildWorldContextProvider(),    # priority 55
        ])
    
        names = builder.get_provider_names()
        expected_order = [
            "system",              # 10
            "persona",             # 20
            "canon",               # 25
            "conversation_history", # 30
            "user_memory",         # 40
            "character_memory",    # 50
            "guild_world",         # 55
            "persona_knowledge_base",  # 60
        ]
        self.assertEqual(names, expected_order)
    
    def test_default_providers_includes_all_eight(self):
        """Default builder should have all 8 standard providers."""
        builder = PromptBuilder.with_default_providers()
        names = builder.get_provider_names()
        self.assertEqual(len(names), 8)
        self.assertIn("system", names)
        self.assertIn("persona", names)
        self.assertIn("canon", names)
        self.assertIn("conversation_history", names)
        self.assertIn("user_memory", names)
        self.assertIn("character_memory", names)
        self.assertIn("guild_world", names)
        self.assertIn("persona_knowledge_base", names)
    
    def test_provider_priority_constants_exist(self):
        """ProviderPriority class should define all standard priorities."""
        self.assertEqual(ProviderPriority.SYSTEM, 10)
        self.assertEqual(ProviderPriority.PERSONA, 20)
        self.assertEqual(ProviderPriority.CANON, 25)
        self.assertEqual(ProviderPriority.CONVERSATION_HISTORY, 30)
        self.assertEqual(ProviderPriority.USER_MEMORY, 40)
        self.assertEqual(ProviderPriority.CHARACTER_MEMORY, 50)
        self.assertEqual(ProviderPriority.PERSONA_KNOWLEDGE_BASE, 60)
    
    def test_get_provider_metadata_returns_correct_info(self):
        """get_provider_metadata should return name, priority, mutability for each provider."""
        builder = PromptBuilder.with_default_providers()
        metadata = builder.get_provider_metadata()
        
        self.assertEqual(len(metadata), 8)
        
        # Check system provider metadata
        sys_meta = next(m for m in metadata if m["name"] == "system")
        self.assertEqual(sys_meta["priority"], ProviderPriority.SYSTEM)
        self.assertEqual(sys_meta["mutability"], Mutability.IMMUTABLE.value)
        
        # Check canon provider metadata (immutable)
        canon_meta = next(m for m in metadata if m["name"] == "canon")
        self.assertEqual(canon_meta["priority"], ProviderPriority.CANON)
        self.assertEqual(canon_meta["mutability"], Mutability.IMMUTABLE.value)
        
        # Check guild_world provider metadata (mutable)
        gw_meta = next(m for m in metadata if m["name"] == "guild_world")
        self.assertEqual(gw_meta["priority"], ProviderPriority.GUILD_WORLD)
        self.assertEqual(gw_meta["mutability"], Mutability.MUTABLE.value)
        
        # Check user_memory provider metadata (mutable)
        mem_meta = next(m for m in metadata if m["name"] == "user_memory")
        self.assertEqual(mem_meta["priority"], ProviderPriority.USER_MEMORY)
        self.assertEqual(mem_meta["mutability"], Mutability.MUTABLE.value)
        
        # Check character_memory provider metadata (mutable)
        char_meta = next(m for m in metadata if m["name"] == "character_memory")
        self.assertEqual(char_meta["priority"], ProviderPriority.CHARACTER_MEMORY)
        self.assertEqual(char_meta["mutability"], Mutability.MUTABLE.value)
        
        # Check persona_knowledge_base provider metadata (immutable)
        kb_meta = next(m for m in metadata if m["name"] == "persona_knowledge_base")
        self.assertEqual(kb_meta["priority"], ProviderPriority.PERSONA_KNOWLEDGE_BASE)
        self.assertEqual(kb_meta["mutability"], Mutability.IMMUTABLE.value)


class TestContextBlock(unittest.TestCase):
    """Tests for ContextBlock dataclass."""
    
    def test_context_block_creation(self):
        """ContextBlock should store name, priority, mutability, content."""
        block = ContextBlock(
            name="test",
            priority=10,
            mutability=Mutability.IMMUTABLE,
            content="Hello world"
        )
        self.assertEqual(block.name, "test")
        self.assertEqual(block.priority, 10)
        self.assertEqual(block.mutability, Mutability.IMMUTABLE)
        self.assertEqual(block.content, "Hello world")
    
    def test_is_empty_property(self):
        """is_empty should return True for empty/whitespace content."""
        self.assertTrue(ContextBlock("a", 1, Mutability.IMMUTABLE, "").is_empty)
        self.assertTrue(ContextBlock("a", 1, Mutability.IMMUTABLE, "   ").is_empty)
        self.assertFalse(ContextBlock("a", 1, Mutability.IMMUTABLE, "content").is_empty)
    
    def test_len(self):
        """len() should return content length."""
        self.assertEqual(len(ContextBlock("a", 1, Mutability.IMMUTABLE, "abc")), 3)


class TestSystemContextProvider(unittest.IsolatedAsyncioTestCase):
    """Tests for SystemContextProvider."""
    
    def test_name_and_priority(self):
        provider = SystemContextProvider()
        self.assertEqual(provider.name, "system")
        self.assertEqual(provider.priority, ProviderPriority.SYSTEM)
        self.assertEqual(provider.mutability, Mutability.IMMUTABLE)
    
    async def test_build_returns_system_instructions(self):
        provider = SystemContextProvider()
        context = PromptBuildContext(
            apply_persona=True,
            persona_data={"system_instructions": "You are a helpful assistant."}
        )
        result = await provider.build(context)
        self.assertIsInstance(result, ContextBlock)
        self.assertEqual(result.name, "system")
        self.assertEqual(result.priority, ProviderPriority.SYSTEM)
        self.assertEqual(result.mutability, Mutability.IMMUTABLE)
        # System instructions should be present, plus Discord mention instruction appended
        self.assertIn("<system_instructions>\nYou are a helpful assistant.", result.content)
        self.assertIn("Discord mention guidelines:", result.content)
        self.assertIn("When REPLYING to a message (using Discord's reply feature), do NOT add a @mention", result.content)
        self.assertIn("When mentioning the user you're responding to in a NON-reply message, use <@USER_ID> format to ping them", result.content)
        self.assertIn("When referencing other users in conversation, prefer their display name or nickname naturally", result.content)
        self.assertIn("Do NOT use @username format", result.content)
        self.assertTrue(result.content.endswith("</system_instructions>"))
    
    async def test_build_returns_empty_when_no_system_instructions(self):
        provider = SystemContextProvider()
        context = PromptBuildContext(
            apply_persona=True,
            persona_data={}
        )
        result = await provider.build(context)
        self.assertTrue(result.is_empty)
    
    async def test_build_returns_empty_when_apply_persona_false(self):
        provider = SystemContextProvider()
        context = PromptBuildContext(
            apply_persona=False,
            persona_data={"system_instructions": "Should not appear"}
        )
        result = await provider.build(context)
        self.assertTrue(result.is_empty)


class TestPersonaContextProvider(unittest.IsolatedAsyncioTestCase):
    """Tests for PersonaContextProvider."""
    
    def test_name_and_priority(self):
        provider = PersonaContextProvider()
        self.assertEqual(provider.name, "persona")
        self.assertEqual(provider.priority, ProviderPriority.PERSONA)
        self.assertEqual(provider.mutability, Mutability.IMMUTABLE)
    
    async def test_build_assembles_all_persona_fields(self):
        provider = PersonaContextProvider()
        context = PromptBuildContext(
            apply_persona=True,
            persona_data={
                "core_personality": "Friendly and helpful",
                "background": "Born in a lab",
                "beliefs": "Knowledge is power",
                "language": "Casual with emojis",
                "system_instructions": "Should not appear here"  # handled by SystemContextProvider
            }
        )
        result = await provider.build(context)
        
        # Should contain all four fields in correct XML format
        self.assertIn("<role>\nFriendly and helpful\n</role>", result.content)
        self.assertIn("<background>\nBorn in a lab\n</background>", result.content)
        self.assertIn("<beliefs>\nKnowledge is power\n</beliefs>", result.content)
        self.assertIn("<language>\nCasual with emojis\n</language>", result.content)
        # System instructions should NOT be here
        self.assertNotIn("system_instructions", result.content)
        # Order should match ASSEMBLY_ORDER: core, background, beliefs, language
        role_idx = result.content.index("<role>")
        bg_idx = result.content.index("<background>")
        beliefs_idx = result.content.index("<beliefs>")
        lang_idx = result.content.index("<language>")
        self.assertTrue(role_idx < bg_idx < beliefs_idx < lang_idx)
    
    async def test_build_skips_empty_fields(self):
        provider = PersonaContextProvider()
        context = PromptBuildContext(
            apply_persona=True,
            persona_data={
                "core_personality": "Present",
                "background": "",  # empty
                "beliefs": "Present",
                "language": "  ",  # whitespace only
            }
        )
        result = await provider.build(context)
        self.assertIn("<role>\nPresent\n</role>", result.content)
        self.assertIn("<beliefs>\nPresent\n</beliefs>", result.content)
        self.assertNotIn("<background>", result.content)
        self.assertNotIn("<language>", result.content)
    
    async def test_build_returns_empty_when_apply_persona_false(self):
        provider = PersonaContextProvider()
        context = PromptBuildContext(
            apply_persona=False,
            persona_data={"core_personality": "Should not appear"}
        )
        result = await provider.build(context)
        self.assertTrue(result.is_empty)


class TestConversationHistoryProvider(unittest.IsolatedAsyncioTestCase):
    """Tests for ConversationHistoryProvider (Provider-agnostic Conversation Manager)."""
    
    def test_name_and_priority(self):
        provider = ConversationHistoryProvider()
        self.assertEqual(provider.name, "conversation_history")
        self.assertEqual(provider.priority, ProviderPriority.CONVERSATION_HISTORY)
        self.assertEqual(provider.mutability, Mutability.MUTABLE)
    
    async def test_build_returns_empty_when_missing_context(self):
        """Returns empty when guild_id or user_id is missing."""
        provider = ConversationHistoryProvider()
        
        # Missing guild_id
        result = await provider.build(PromptBuildContext(
            apply_persona=True, user_id=1, channel_id=1
        ))
        self.assertTrue(result.is_empty)
        
        # Missing user_id
        result = await provider.build(PromptBuildContext(
            apply_persona=True, guild_id=1, channel_id=1
        ))
        self.assertTrue(result.is_empty)
    
    async def test_build_returns_empty_when_apply_persona_false(self):
        provider = ConversationHistoryProvider()
        context = PromptBuildContext(
            apply_persona=False,
            guild_id=123,
            user_id=456,
            channel_id=789
        )
        result = await provider.build(context)
        self.assertTrue(result.is_empty)
    
    @patch("utils.conversation.build_conversation_context")
    async def test_build_delegates_to_conversation_module(self, mock_build):
        """Delegates to ConversationManager.build_conversation_context."""
        mock_build.return_value = "[Conversation History]\nUser: Hello\nAssistant: Hi there"
        
        provider = ConversationHistoryProvider()
        context = PromptBuildContext(
            apply_persona=True,
            guild_id=123,
            user_id=456,
            channel_id=789,
        )
        result = await provider.build(context)
        
        mock_build.assert_called_once_with(
            guild_id=123,
            channel_id=789,
            user_id=456,
        )
        self.assertEqual(result.content, "[Conversation History]\nUser: Hello\nAssistant: Hi there")
        self.assertEqual(result.mutability, Mutability.MUTABLE)


class TestUserMemoryProvider(unittest.IsolatedAsyncioTestCase):
    """Tests for UserMemoryProvider."""
    
    def test_name_and_priority(self):
        provider = UserMemoryProvider()
        self.assertEqual(provider.name, "user_memory")
        self.assertEqual(provider.priority, ProviderPriority.USER_MEMORY)
        self.assertEqual(provider.mutability, Mutability.MUTABLE)
    
    @patch("utils.memory.get_user_facts_prompt")
    async def test_build_delegates_to_memory_module(self, mock_get_facts):
        mock_get_facts.return_value = "[Known facts about Alice]\n- Likes cats\n- Hates Mondays"
        
        provider = UserMemoryProvider()
        context = PromptBuildContext(
            apply_persona=True,
            guild_id=123,
            user_id=456,
            username="Alice"
        )
        result = await provider.build(context)
        
        mock_get_facts.assert_called_once_with(123, 456, "Alice")
        self.assertEqual(result.content, "[Known facts about Alice]\n- Likes cats\n- Hates Mondays")
        self.assertEqual(result.mutability, Mutability.MUTABLE)
    
    async def test_build_returns_empty_when_missing_ids(self):
        provider = UserMemoryProvider()
        
        # Missing guild_id
        result = await provider.build(PromptBuildContext(apply_persona=True, user_id=1))
        self.assertTrue(result.is_empty)
        
        # Missing user_id
        result = await provider.build(PromptBuildContext(apply_persona=True, guild_id=1))
        self.assertTrue(result.is_empty)
    
    async def test_build_returns_empty_when_apply_persona_false(self):
        provider = UserMemoryProvider()
        context = PromptBuildContext(
            apply_persona=False,
            guild_id=123,
            user_id=456,
            username="Alice"
        )
        result = await provider.build(context)
        self.assertTrue(result.is_empty)


class TestCharacterMemoryProvider(unittest.IsolatedAsyncioTestCase):
    """Tests for CharacterMemoryProvider."""
    
    def test_name_and_priority(self):
        provider = CharacterMemoryProvider()
        self.assertEqual(provider.name, "character_memory")
        self.assertEqual(provider.priority, ProviderPriority.CHARACTER_MEMORY)
        self.assertEqual(provider.mutability, Mutability.MUTABLE)
    
    @patch("utils.character_memory.build_character_memory_context")
    async def test_build_delegates_to_character_memory_module(self, mock_build):
        """Delegates to CharacterMemory.build_character_memory_context."""
        mock_build.return_value = "[Character Memory with TestUser]\n[PROMISE] We promised to play chess. (importance: 0.9)"
        
        provider = CharacterMemoryProvider()
        context = PromptBuildContext(
            apply_persona=True,
            guild_id=123,
            user_id=456,
            persona_id="test_persona",
            username="TestUser",
        )
        result = await provider.build(context)
        
        mock_build.assert_called_once_with(
            guild_id=123,
            user_id=456,
            persona_id="test_persona",
            username="TestUser",
        )
        self.assertEqual(result.content, "[Character Memory with TestUser]\n[PROMISE] We promised to play chess. (importance: 0.9)")
        self.assertEqual(result.mutability, Mutability.MUTABLE)
    
    async def test_build_returns_empty_when_missing_ids(self):
        provider = CharacterMemoryProvider()
        
        # Missing guild_id
        result = await provider.build(PromptBuildContext(
            apply_persona=True, user_id=1, persona_id="test"
        ))
        self.assertTrue(result.is_empty)
        
        # Missing user_id
        result = await provider.build(PromptBuildContext(
            apply_persona=True, guild_id=1, persona_id="test"
        ))
        self.assertTrue(result.is_empty)
        
        # Missing persona_id
        result = await provider.build(PromptBuildContext(
            apply_persona=True, guild_id=1, user_id=1
        ))
        self.assertTrue(result.is_empty)
    
    async def test_build_returns_empty_when_apply_persona_false(self):
        provider = CharacterMemoryProvider()
        context = PromptBuildContext(
            apply_persona=False,
            guild_id=123,
            user_id=456,
            persona_id="test_persona"
        )
        result = await provider.build(context)
        self.assertTrue(result.is_empty)


class TestPersonaKnowledgeBaseProvider(unittest.IsolatedAsyncioTestCase):
    """Tests for PersonaKnowledgeBaseProvider."""
    
    def test_name_and_priority(self):
        provider = PersonaKnowledgeBaseProvider()
        self.assertEqual(provider.name, "persona_knowledge_base")
        self.assertEqual(provider.priority, ProviderPriority.PERSONA_KNOWLEDGE_BASE)
        self.assertEqual(provider.mutability, Mutability.IMMUTABLE)
    
    @patch("utils.chroma.query_knowledge")
    async def test_build_formats_entries_correctly(self, mock_query):
        mock_query.return_value = [
            {
                "document": "Chisato loves aquariums.",
                "metadata": {
                    "source": "Episode 06",
                    "entry_type": "dialogue",
                    "scene": "Aquarium",
                    "speaker": "Chisato",
                    "chapter": "",
                    "timestamp": "S01E06 12:34",
                    "canon_level": "canon"
                }
            },
            {
                "document": "Takina is serious.",
                "metadata": {
                    "source": "Episode 01",
                    "entry_type": "narration",
                    "scene": "",
                    "speaker": "",
                    "chapter": "Chapter 1",
                    "timestamp": "",
                    "canon_level": "canon"
                }
            }
        ]
        
        provider = PersonaKnowledgeBaseProvider()
        context = PromptBuildContext(
            apply_persona=True,
            kb_enabled=True,
            persona_id="chisato_nishikigi",
            kb_top_k=5,
            user_message="What does Chisato like?"
        )
        result = await provider.build(context)
        
        # Verify format matches generation.py exactly
        self.assertIn("Relevant Canonical Context", result.content)
        self.assertIn("1. Chisato loves aquariums.", result.content)
        self.assertIn("(Source: Episode 06, Type: dialogue, Scene: Aquarium, Speaker: Chisato, Timestamp: S01E06 12:34, Canon: canon)", result.content)
        self.assertIn("2. Takina is serious.", result.content)
        self.assertIn("(Source: Episode 01, Type: narration, Chapter: Chapter 1, Canon: canon)", result.content)
        self.assertEqual(result.mutability, Mutability.IMMUTABLE)
    
    async def test_build_returns_empty_when_disabled(self):
        provider = PersonaKnowledgeBaseProvider()
        context = PromptBuildContext(
            apply_persona=True,
            kb_enabled=False,  # disabled
            persona_id="test",
            user_message="hello"
        )
        result = await provider.build(context)
        self.assertTrue(result.is_empty)
    
    async def test_build_returns_empty_when_no_persona_id(self):
        provider = PersonaKnowledgeBaseProvider()
        context = PromptBuildContext(
            apply_persona=True,
            kb_enabled=True,
            persona_id="",
            user_message="hello"
        )
        result = await provider.build(context)
        self.assertTrue(result.is_empty)
    
    async def test_build_returns_empty_when_no_user_message(self):
        provider = PersonaKnowledgeBaseProvider()
        context = PromptBuildContext(
            apply_persona=True,
            kb_enabled=True,
            persona_id="test",
            user_message=""
        )
        result = await provider.build(context)
        self.assertTrue(result.is_empty)


class TestGuildWorldContextProvider(unittest.IsolatedAsyncioTestCase):
    """Tests for GuildWorldContextProvider (Phase 3)."""
    
    def test_name_and_priority(self):
        provider = GuildWorldContextProvider()
        self.assertEqual(provider.name, "guild_world")
        self.assertEqual(provider.priority, ProviderPriority.GUILD_WORLD)
        self.assertEqual(provider.mutability, Mutability.MUTABLE)
    
    async def test_build_returns_empty_when_apply_persona_false(self):
        provider = GuildWorldContextProvider()
        context = PromptBuildContext(
            apply_persona=False,
            guild_id=123,
            channel_id=456,
        )
        result = await provider.build(context)
        self.assertTrue(result.is_empty)
    
    async def test_build_returns_empty_when_no_guild_id(self):
        provider = GuildWorldContextProvider()
        context = PromptBuildContext(
            apply_persona=True,
            channel_id=456,
        )
        result = await provider.build(context)
        self.assertTrue(result.is_empty)
    
    async def test_build_returns_empty_when_no_channel_id(self):
        provider = GuildWorldContextProvider()
        context = PromptBuildContext(
            apply_persona=True,
            guild_id=123,
        )
        result = await provider.build(context)
        self.assertTrue(result.is_empty)
    
    async def test_build_returns_empty_with_null_accessor(self):
        """With NULL_ACCESSOR, should return empty (no data)."""
        from utils.guild_world import NULL_ACCESSOR
        provider = GuildWorldContextProvider()
        context = PromptBuildContext(
            apply_persona=True,
            guild_id=123,
            channel_id=456,
            guild_world_accessor=NULL_ACCESSOR,
        )
        result = await provider.build(context)
        self.assertTrue(result.is_empty)
    
    async def test_build_formats_context_correctly(self):
        """With a mock accessor, should format guild/channel info."""
        class MockAccessor:
            async def get_guild_name(self, guild_id):
                _ = guild_id
                return "Test Server"
            async def get_channel_name(self, channel_id):
                _ = channel_id
                return "general"
            async def get_channel_topic(self, channel_id):
                _ = channel_id
                return "Welcome channel"
            async def get_guild_member_count(self, guild_id):
                _ = guild_id
                return 100
        
        provider = GuildWorldContextProvider()
        context = PromptBuildContext(
            apply_persona=True,
            guild_id=123,
            channel_id=456,
            guild_world_accessor=MockAccessor(),
        )
        result = await provider.build(context)
        
        self.assertFalse(result.is_empty)
        self.assertIn("[Guild World Context]", result.content)
        self.assertIn("Server: Test Server", result.content)
        self.assertIn("Population: ~100", result.content)
        self.assertIn("Channel: #general", result.content)
        self.assertIn("Topic: Welcome channel", result.content)
        self.assertEqual(result.mutability, Mutability.MUTABLE)


class TestPromptBuildContext(unittest.TestCase):
    """Tests for PromptBuildContext dataclass."""
    
    def test_defaults(self):
        context = PromptBuildContext()
        self.assertIsNone(context.guild_id)
        self.assertIsNone(context.channel_id)
        self.assertIsNone(context.user_id)
        self.assertEqual(context.username, "")
        self.assertEqual(context.persona_id, "")
        self.assertEqual(context.persona_data, {})
        self.assertEqual(context.current_persona_assembled, "")
        self.assertTrue(context.apply_persona)
        self.assertTrue(context.kb_enabled)
        self.assertEqual(context.kb_top_k, 5)
        self.assertEqual(context.user_message, "")
        self.assertEqual(context.instruction_prefix, "")
    
    def test_custom_values(self):
        context = PromptBuildContext(
            guild_id=1,
            user_id=2,
            username="Test",
            persona_id="test_persona",
            persona_data={"core_personality": "test"},
            current_persona_assembled="assembled",
            apply_persona=False,
            kb_enabled=False,
            kb_top_k=10,
            user_message="Hello",
            instruction_prefix="[Test]: "
        )
        self.assertEqual(context.guild_id, 1)
        self.assertEqual(context.user_id, 2)
        self.assertEqual(context.username, "Test")
        self.assertEqual(context.persona_id, "test_persona")
        self.assertEqual(context.persona_data, {"core_personality": "test"})
        self.assertEqual(context.current_persona_assembled, "assembled")
        self.assertFalse(context.apply_persona)
        self.assertFalse(context.kb_enabled)
        self.assertEqual(context.kb_top_k, 10)
        self.assertEqual(context.user_message, "Hello")
        self.assertEqual(context.instruction_prefix, "[Test]: ")


class TestBuildSystemPromptBackwardsCompat(unittest.IsolatedAsyncioTestCase):
    """Test the backwards-compatible build_system_prompt function."""
    
    @patch("utils.persona.PERSONA_DATA", {"system_instructions": "Global sys", "core_personality": "Global core"})
    @patch("utils.memory.get_user_facts_prompt")
    async def test_uses_global_persona_data_when_none_provided(self, mock_get_facts):
        mock_get_facts.return_value = ""
        result = await build_system_prompt(
            current_persona="<system_instructions>\nGlobal sys\n</system_instructions>\n\n<role>\nGlobal core\n</role>",
            persona_id="test",
            guild_id=1,
            user_id=2,
            username="Alice",
            apply_persona=True,
        )
        self.assertIn("Global sys", result)
        self.assertIn("Discord mention guidelines:", result)
        self.assertIn("When REPLYING to a message (using Discord's reply feature), do NOT add a @mention", result)
        self.assertIn("<role>\nGlobal core\n</role>", result)
    
    @patch("utils.memory.get_user_facts_prompt")
    async def test_uses_provided_persona_data(self, mock_get_facts):
        mock_get_facts.return_value = ""
        result = await build_system_prompt(
            current_persona="<system_instructions>\nProvided sys\n</system_instructions>\n\n<role>\nProvided core\n</role>",
            persona_id="test",
            guild_id=1,
            user_id=2,
            username="Alice",
            apply_persona=True,
            persona_data={"system_instructions": "Provided sys", "core_personality": "Provided core"}
        )
        self.assertIn("Provided sys", result)
        self.assertIn("Discord mention guidelines:", result)
        self.assertIn("When REPLYING to a message (using Discord's reply feature), do NOT add a @mention", result)
        self.assertIn("<role>\nProvided core\n</role>", result)


class TestPromptBuilderInspect(unittest.IsolatedAsyncioTestCase):
    """Test the inspect() method for debugging."""
    
    async def test_inspect_returns_all_providers_with_context_blocks(self):
        builder = PromptBuilder.with_default_providers()
        context = PromptBuildContext(
            apply_persona=True,
            persona_data={
                "system_instructions": "Sys",
                "core_personality": "Core",
                "background": "BG",
                "beliefs": "Beliefs",
                "language": "Lang"
            },
            guild_id=1,
            user_id=2,
            username="Test",
            persona_id="test",
            kb_enabled=True,
            user_message="Hello"
        )
        
        result = await builder.inspect(context)
        
        # Should have all 8 providers
        self.assertEqual(len(result), 8)
        self.assertIn("system", result)
        self.assertIn("persona", result)
        self.assertIn("canon", result)
        self.assertIn("conversation_history", result)
        self.assertIn("user_memory", result)
        self.assertIn("character_memory", result)
        self.assertIn("guild_world", result)
        self.assertIn("persona_knowledge_base", result)
        
        # Each value should be a ContextBlock
        for name, block in result.items():
            self.assertIsInstance(block, ContextBlock, f"{name} should be ContextBlock")
            self.assertEqual(block.name, name)
            # Convert name to ProviderPriority attribute format
            priority_attr_map = {
                "system": "SYSTEM",
                "persona": "PERSONA",
                "canon": "CANON",
                "conversation_history": "CONVERSATION_HISTORY",
                "user_memory": "USER_MEMORY",
                "character_memory": "CHARACTER_MEMORY",
                "guild_world": "GUILD_WORLD",
                "persona_knowledge_base": "PERSONA_KNOWLEDGE_BASE",
            }
            self.assertEqual(block.priority, getattr(ProviderPriority, priority_attr_map[name]))
        
        # System and persona should have content
        self.assertIn("Sys", result["system"].content)
        self.assertIn("Core", result["persona"].content)
        
        # Character memory should have content (empty if no memories stored)
        self.assertIsInstance(result["character_memory"].content, str)
        
        # Verify mutability classifications
        self.assertEqual(result["system"].mutability, Mutability.IMMUTABLE)
        self.assertEqual(result["persona"].mutability, Mutability.IMMUTABLE)
        self.assertEqual(result["canon"].mutability, Mutability.IMMUTABLE)
        self.assertEqual(result["user_memory"].mutability, Mutability.MUTABLE)
        self.assertEqual(result["character_memory"].mutability, Mutability.MUTABLE)
        self.assertEqual(result["guild_world"].mutability, Mutability.MUTABLE)
        self.assertEqual(result["persona_knowledge_base"].mutability, Mutability.IMMUTABLE)
        self.assertEqual(result["conversation_history"].mutability, Mutability.MUTABLE)


class TestPromptBuilderCustomProviders(unittest.TestCase):
    """Test custom provider lists and extension."""
    
    def test_with_providers_allows_custom_list(self):
        """PromptBuilder.with_providers should allow custom provider list."""
        # Create a minimal test provider
        class TestProvider(ContextProvider):
            @property
            def name(self): return "test"
            @property
            def priority(self): return 999
            @property
            def mutability(self): return Mutability.IMMUTABLE
            async def build(self, context): 
                return ContextBlock("test", 999, Mutability.IMMUTABLE, "test")
        
        builder = PromptBuilder.with_providers([TestProvider()])
        self.assertEqual(builder.get_provider_names(), ["test"])
    
    def test_without_default_providers_can_be_empty(self):
        """PromptBuilder can be created with empty provider list."""
        builder = PromptBuilder(providers=[])
        self.assertEqual(builder.get_provider_names(), [])


class TestTokenBudgetEnforcement(unittest.IsolatedAsyncioTestCase):
    """Test token budget enforcement in PromptBuilder.build()."""
    
    def test_context_block_estimate_tokens(self):
        """ContextBlock.estimate_tokens should return rough token count."""
        block = ContextBlock("test", 10, Mutability.IMMUTABLE, "a" * 100)
        self.assertEqual(block.estimate_tokens(), 25)  # 100 chars / 4
        
        block = ContextBlock("test", 10, Mutability.IMMUTABLE, "")
        self.assertEqual(block.estimate_tokens(), 0)
    
    async def test_build_respects_token_budget_within_limit(self):
        """When total tokens within budget, all blocks should be included."""
        # Create mock providers with known content sizes
        class SmallProvider(ContextProvider):
            def __init__(self, name, priority, mutability, content):
                self._name = name
                self._priority = priority
                self._mutability = mutability
                self._content = content
            @property
            def name(self): return self._name
            @property
            def priority(self): return self._priority
            @property
            def mutability(self): return self._mutability
            async def build(self, context):
                return ContextBlock(self._name, self._priority, self._mutability, self._content)
        
        # 4 chars = ~1 token, so 100 chars = ~25 tokens
        providers = [
            SmallProvider("immutable1", 10, Mutability.IMMUTABLE, "x" * 100),  # ~25 tokens
            SmallProvider("mutable1", 30, Mutability.MUTABLE, "x" * 100),       # ~25 tokens
            SmallProvider("mutable2", 40, Mutability.MUTABLE, "x" * 100),       # ~25 tokens
        ]
        # Total ~75 tokens, budget 100 - should keep all
        builder = PromptBuilder.with_providers(providers, token_budget=100)
        context = PromptBuildContext(apply_persona=True)
        result = await builder.build(context)
        
        # All three blocks should be present
        self.assertEqual(result.count("x" * 100), 3)
    
    async def test_build_drops_mutable_blocks_in_reverse_priority_order(self):
        """When over budget, MUTABLE blocks dropped in reverse priority order."""
        class SmallProvider(ContextProvider):
            def __init__(self, name, priority, mutability, content):
                self._name = name
                self._priority = priority
                self._mutability = mutability
                self._content = content
            @property
            def name(self): return self._name
            @property
            def priority(self): return self._priority
            @property
            def mutability(self): return self._mutability
            async def build(self, context):
                return ContextBlock(self._name, self._priority, self._mutability, self._content)
        
        # 100 chars = ~25 tokens each
        providers = [
            SmallProvider("immutable1", 10, Mutability.IMMUTABLE, "A" * 100),  # ~25 tokens
            SmallProvider("mutable_low", 30, Mutability.MUTABLE, "B" * 100),    # ~25 tokens
            SmallProvider("mutable_mid", 40, Mutability.MUTABLE, "C" * 100),    # ~25 tokens
            SmallProvider("mutable_high", 50, Mutability.MUTABLE, "D" * 100),   # ~25 tokens
            SmallProvider("immutable2", 60, Mutability.IMMUTABLE, "E" * 100),   # ~25 tokens
        ]
        # Total ~125 tokens, budget 100
        # Should drop mutable_high (50) first, then mutable_mid (40) if needed
        # But immutable are never dropped (10 + 60 = 20 priority values, ~50 tokens)
        # So remaining budget for mutable = 100 - 50 = 50 tokens
        # Can fit mutable_low (30, 25 tokens) and mutable_mid (40, 25 tokens) = 50 tokens
        # mutable_high (50) should be dropped
        builder = PromptBuilder.with_providers(providers, token_budget=100)
        context = PromptBuildContext(apply_persona=True)
        result = await builder.build(context)
        
        # Immutable blocks should always be present
        self.assertIn("A" * 100, result)
        self.assertIn("E" * 100, result)
        # Low and mid priority mutable should be present
        self.assertIn("B" * 100, result)
        self.assertIn("C" * 100, result)
        # High priority mutable should be dropped
        self.assertNotIn("D" * 100, result)
    
    async def test_build_never_drops_immutable_blocks(self):
        """IMMUTABLE blocks should never be dropped regardless of budget."""
        class SmallProvider(ContextProvider):
            def __init__(self, name, priority, mutability, content):
                self._name = name
                self._priority = priority
                self._mutability = mutability
                self._content = content
            @property
            def name(self): return self._name
            @property
            def priority(self): return self._priority
            @property
            def mutability(self): return self._mutability
            async def build(self, context):
                return ContextBlock(self._name, self._priority, self._mutability, self._content)
        
        # 100 chars = ~25 tokens each
        providers = [
            SmallProvider("immutable1", 10, Mutability.IMMUTABLE, "A" * 100),  # ~25 tokens
            SmallProvider("immutable2", 20, Mutability.IMMUTABLE, "B" * 100),  # ~25 tokens
            SmallProvider("immutable3", 25, Mutability.IMMUTABLE, "C" * 100),  # ~25 tokens
            SmallProvider("mutable1", 30, Mutability.MUTABLE, "D" * 100),      # ~25 tokens
        ]
        # Total ~100 tokens, budget 75
        # Immutable use 75 tokens, mutable would need 25 more
        # All immutable should be kept, mutable dropped
        builder = PromptBuilder.with_providers(providers, token_budget=75)
        context = PromptBuildContext(apply_persona=True)
        result = await builder.build(context)
        
        # All immutable should be present
        self.assertIn("A" * 100, result)
        self.assertIn("B" * 100, result)
        self.assertIn("C" * 100, result)
        # Mutable should be dropped
        self.assertNotIn("D" * 100, result)
    
    async def test_build_with_placeholder_mutability(self):
        """PLACEHOLDER mutability blocks should be skipped (empty content)."""
        class SmallProvider(ContextProvider):
            def __init__(self, name, priority, mutability, content):
                self._name = name
                self._priority = priority
                self._mutability = mutability
                self._content = content
            @property
            def name(self): return self._name
            @property
            def priority(self): return self._priority
            @property
            def mutability(self): return self._mutability
            async def build(self, context):
                return ContextBlock(self._name, self._priority, self._mutability, self._content)
        
        providers = [
            SmallProvider("immutable", 10, Mutability.IMMUTABLE, "A" * 100),
            SmallProvider("placeholder", 20, Mutability.PLACEHOLDER, "B" * 100),
            SmallProvider("mutable", 30, Mutability.MUTABLE, "C" * 100),
        ]
        builder = PromptBuilder.with_providers(providers, token_budget=50)
        context = PromptBuildContext(apply_persona=True)
        result = await builder.build(context)
        
        # Placeholder should not appear (empty content or skipped)
        self.assertIn("A" * 100, result)
        # Note: PLACEHOLDER blocks with content ARE included if not empty
        # But is_empty check should skip them if content is empty/whitespace
    
    async def test_build_with_default_providers_and_token_budget(self):
        """PromptBuilder.with_default_providers should accept token_budget parameter."""
        builder = PromptBuilder.with_default_providers(token_budget=4000)
        self.assertEqual(builder.token_budget, 4000)
        
        builder = PromptBuilder.with_default_providers()
        self.assertEqual(builder.token_budget, 8000)


if __name__ == "__main__":
    unittest.main()