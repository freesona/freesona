# tests/test_canon.py: Tests for the Canon Framework

import os
import tempfile
import unittest
import sys
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.canon import (
    CanonComponentType,
    CanonComponent,
    CanonSnapshot,
    CanonValidationError,
    init_db,
    store_component,
    update_component,
    delete_component,
    get_components,
    get_component,
    get_components_by_type,
    create_snapshot,
    get_snapshots,
    restore_snapshot,
    build_canon_context,
    ensure_default_canon,
    validate_canon_component,
    export_canon,
    import_canon,
    COMPONENT_ASSEMBLY_ORDER,
    COMPONENT_LABELS,
    COMPONENT_XML_TAGS,
    DEFAULT_CANON_TEMPLATES,
)


TEST_PERSONA_ID = "test_persona_canon"


class TestCanonDatabase(unittest.TestCase):
    """Test the Canon database operations."""
    
    def setUp(self):
        """Set up a temporary canon database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        os.environ["CANON_FILE_PATH"] = self.temp_db.name
        
        # Re-import to pick up new path
        import utils.canon as canon_module
        canon_module.CANON_FILE_PATH = self.temp_db.name
        
        # Run init_db synchronously
        import asyncio
        asyncio.run(init_db())
    
    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
        if "CANON_FILE_PATH" in os.environ:
            del os.environ["CANON_FILE_PATH"]
    
    def test_init_db_creates_tables(self):
        """Test that init_db creates the required tables."""
        import asyncio
        import aiosqlite
        
        async def check_tables():
            async with aiosqlite.connect(os.getenv("CANON_FILE_PATH") or "") as db:
                async with db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ) as cursor:
                    tables = [row[0] async for row in cursor]
                    return tables
        
        tables = asyncio.run(check_tables())
        self.assertIn("canon_components", tables)
        self.assertIn("canon_snapshots", tables)


class TestCanonComponentCRUD(unittest.TestCase):
    """Test CRUD operations for canon components."""
    
    def setUp(self):
        """Set up a temporary canon database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        os.environ["CANON_FILE_PATH"] = self.temp_db.name
        
        import utils.canon as canon_module
        canon_module.CANON_FILE_PATH = self.temp_db.name
        
        import asyncio
        asyncio.run(init_db())
    
    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
        if "CANON_FILE_PATH" in os.environ:
            del os.environ["CANON_FILE_PATH"]
    
    def test_store_and_get_component(self):
        """Test storing and retrieving a canon component."""
        import asyncio
        
        async def test():
            component = CanonComponent(
                component_id="test-comp-1",
                persona_id=TEST_PERSONA_ID,
                component_type=CanonComponentType.CORE_IDENTITY,
                content="Test identity content",
                explanation="Test explanation",
                version="1.0.0",
                author="test",
            )
            
            await store_component(component)
            retrieved = await get_component("test-comp-1")
            
            assert retrieved is not None
            self.assertEqual(retrieved.component_id, "test-comp-1")
            self.assertEqual(retrieved.persona_id, TEST_PERSONA_ID)
            self.assertEqual(retrieved.component_type, CanonComponentType.CORE_IDENTITY)
            self.assertEqual(retrieved.content, "Test identity content")
            self.assertEqual(retrieved.explanation, "Test explanation")
        
        asyncio.run(test())
    
    def test_get_components_ordered(self):
        """Test that components are returned in assembly order."""
        import asyncio
        
        async def test():
            # Store components out of order
            for comp_type in [
                CanonComponentType.WORLD_ASSUMPTIONS,
                CanonComponentType.CORE_IDENTITY,
                CanonComponentType.BEHAVIORAL_RULES,
                CanonComponentType.MOTIVATIONS,
            ]:
                component = CanonComponent(
                    component_id=f"test-{comp_type.value}",
                    persona_id=TEST_PERSONA_ID,
                    component_type=comp_type,
                    content=f"Content for {comp_type.value}",
                    explanation="Explanation",
                    version="1.0.0",
                    author="test",
                )
                await store_component(component)
            
            components = await get_components(TEST_PERSONA_ID)
            
            # Should be ordered by COMPONENT_ASSEMBLY_ORDER
            expected_order = [
                CanonComponentType.CORE_IDENTITY,
                CanonComponentType.CORE_BELIEFS,
                CanonComponentType.MOTIVATIONS,
                CanonComponentType.BEHAVIORAL_RULES,
                CanonComponentType.WORLD_ASSUMPTIONS,
                CanonComponentType.CANON_EXPLANATIONS,
            ]
            
            # Filter to only the ones we inserted
            inserted_types = [c.component_type for c in components]
            
            # Verify order matches assembly order for inserted types
            for i, expected_type in enumerate(expected_order):
                if expected_type in inserted_types:
                    actual_idx = inserted_types.index(expected_type)
                    for prev_type in expected_order[:i]:
                        if prev_type in inserted_types:
                            prev_idx = inserted_types.index(prev_type)
                            self.assertLess(prev_idx, actual_idx,
                                f"{prev_type.value} should come before {expected_type.value}")
        
        asyncio.run(test())
    
    def test_update_component(self):
        """Test updating a canon component."""
        import asyncio
        
        async def test():
            component = CanonComponent(
                component_id="test-update",
                persona_id=TEST_PERSONA_ID,
                component_type=CanonComponentType.CORE_BELIEFS,
                content="Original content",
                explanation="Original explanation",
                version="1.0.0",
                author="test",
            )
            
            await store_component(component)
            
            # Update
            component.content = "Updated content"
            component.explanation = "Updated explanation"
            component.version = "1.1.0"
            await update_component(component)
            
            retrieved = await get_component("test-update")
            assert retrieved is not None
            self.assertEqual(retrieved.content, "Updated content")
            self.assertEqual(retrieved.explanation, "Updated explanation")
            self.assertEqual(retrieved.version, "1.1.0")
        
        asyncio.run(test())
    
    def test_delete_component(self):
        """Test deleting a canon component."""
        import asyncio
        
        async def test():
            component = CanonComponent(
                component_id="test-delete",
                persona_id=TEST_PERSONA_ID,
                component_type=CanonComponentType.MOTIVATIONS,
                content="To be deleted",
                explanation="Explanation",
                version="1.0.0",
                author="test",
            )
            
            await store_component(component)
            self.assertIsNotNone(await get_component("test-delete"))
            
            await delete_component("test-delete")
            self.assertIsNone(await get_component("test-delete"))
        
        asyncio.run(test())
    
    def test_get_components_by_type(self):
        """Test filtering components by type."""
        import asyncio
        
        async def test():
            for comp_type in CanonComponentType:
                component = CanonComponent(
                    component_id=f"test-by-type-{comp_type.value}",
                    persona_id=TEST_PERSONA_ID,
                    component_type=comp_type,
                    content=f"Content for {comp_type.value}",
                    explanation="Explanation",
                    version="1.0.0",
                    author="test",
                )
                await store_component(component)
            
            # Get only BEHAVIORAL_RULES
            rules = await get_components_by_type(TEST_PERSONA_ID, CanonComponentType.BEHAVIORAL_RULES)
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0].component_type, CanonComponentType.BEHAVIORAL_RULES)
            
            # Get only CORE_IDENTITY
            identity = await get_components_by_type(TEST_PERSONA_ID, CanonComponentType.CORE_IDENTITY)
            self.assertEqual(len(identity), 1)
            self.assertEqual(identity[0].component_type, CanonComponentType.CORE_IDENTITY)
        
        asyncio.run(test())


class TestCanonSnapshots(unittest.TestCase):
    """Test canon snapshot (versioning) operations."""
    
    def setUp(self):
        """Set up a temporary canon database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        os.environ["CANON_FILE_PATH"] = self.temp_db.name
        
        import utils.canon as canon_module
        canon_module.CANON_FILE_PATH = self.temp_db.name
        
        import asyncio
        asyncio.run(init_db())
    
    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
        if "CANON_FILE_PATH" in os.environ:
            del os.environ["CANON_FILE_PATH"]
    
    def test_snapshot_creation_and_retrieval(self):
        """Test creating and retrieving canon snapshots."""
        import asyncio
        
        async def test():
            # Create some components
            for comp_type in [
                CanonComponentType.CORE_IDENTITY,
                CanonComponentType.CORE_BELIEFS,
            ]:
                component = CanonComponent(
                    component_id=f"snap-test-{comp_type.value}",
                    persona_id=TEST_PERSONA_ID,
                    component_type=comp_type,
                    content=f"Snapshot content for {comp_type.value}",
                    explanation="Explanation",
                    version="1.0.0",
                    author="test",
                )
                await store_component(component)
            
            # Create snapshot
            snapshot = await create_snapshot(
                persona_id=TEST_PERSONA_ID,
                version="1.0.0",
                author="test",
                description="Test snapshot"
            )
            
            self.assertIsNotNone(snapshot.snapshot_id)
            self.assertEqual(snapshot.persona_id, TEST_PERSONA_ID)
            self.assertEqual(snapshot.version, "1.0.0")
            self.assertEqual(len(snapshot.components), 2)
            
            # Retrieve snapshots
            snapshots = await get_snapshots(TEST_PERSONA_ID, limit=5)
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(snapshots[0].snapshot_id, snapshot.snapshot_id)
        
        asyncio.run(test())
    
    def test_restore_snapshot(self):
        """Test restoring canon from a snapshot."""
        import asyncio
        
        async def test():
            # Create initial components
            for comp_type in [CanonComponentType.CORE_IDENTITY]:
                component = CanonComponent(
                    component_id=f"restore-test-{comp_type.value}",
                    persona_id=TEST_PERSONA_ID,
                    component_type=comp_type,
                    content=f"Original {comp_type.value}",
                    explanation="Explanation",
                    version="1.0.0",
                    author="test",
                )
                await store_component(component)
            
            # Create snapshot
            snapshot = await create_snapshot(
                persona_id=TEST_PERSONA_ID,
                version="1.0.0",
                author="test",
                description="Before changes"
            )
            
            # Modify component
            component = await get_component(f"restore-test-{CanonComponentType.CORE_IDENTITY.value}")
            assert component is not None
            component.content = "Modified content"
            component.version = "2.0.0"
            await update_component(component)
            
            # Verify modification
            modified = await get_component(f"restore-test-{CanonComponentType.CORE_IDENTITY.value}")
            assert modified is not None
            self.assertEqual(modified.content, "Modified content")
            
            # Restore snapshot
            result = await restore_snapshot(snapshot.snapshot_id)
            self.assertTrue(result)
            
            # Verify restored
            restored = await get_component(f"restore-test-{CanonComponentType.CORE_IDENTITY.value}")
            assert restored is not None
            self.assertEqual(restored.content, f"Original {CanonComponentType.CORE_IDENTITY.value}")
        
        asyncio.run(test())


class TestCanonContextAssembly(unittest.TestCase):
    """Test building canon context for PromptBuilder."""
    
    def setUp(self):
        """Set up a temporary canon database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        os.environ["CANON_FILE_PATH"] = self.temp_db.name
        
        import utils.canon as canon_module
        canon_module.CANON_FILE_PATH = self.temp_db.name
        
        import asyncio
        asyncio.run(init_db())
    
    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
        if "CANON_FILE_PATH" in os.environ:
            del os.environ["CANON_FILE_PATH"]
    
    def test_build_canon_context(self):
        """Test building the canon context block for PromptBuilder."""
        import asyncio
        
        async def test():
            # Create components
            for comp_type in [
                CanonComponentType.CORE_IDENTITY,
                CanonComponentType.BEHAVIORAL_RULES,
            ]:
                component = CanonComponent(
                    component_id=f"context-test-{comp_type.value}",
                    persona_id=TEST_PERSONA_ID,
                    component_type=comp_type,
                    content=f"Content for {comp_type.value}",
                    explanation="The reason why" if comp_type == CanonComponentType.BEHAVIORAL_RULES else "",
                    version="1.0.0",
                    author="test",
                )
                await store_component(component)
            
            context = await build_canon_context(TEST_PERSONA_ID)
            
            self.assertIn("[Canon Definition]", context)
            self.assertIn("<core_identity>", context)
            self.assertIn("Content for core_identity", context)
            self.assertIn("<behavioral_rules>", context)
            self.assertIn("Content for behavioral_rules", context)
            self.assertIn("<!-- Why: The reason why -->", context)
        
        asyncio.run(test())
    
    def test_build_canon_context_empty(self):
        """Test building context when no canon exists."""
        import asyncio
        
        async def test():
            context = await build_canon_context("nonexistent_persona")
            self.assertEqual(context, "")
            
            context = await build_canon_context("")
            self.assertEqual(context, "")
        
        asyncio.run(test())


class TestCanonDefaultCreation(unittest.TestCase):
    """Test default canon creation for new personas."""
    
    def setUp(self):
        """Set up a temporary canon database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        os.environ["CANON_FILE_PATH"] = self.temp_db.name
        
        import utils.canon as canon_module
        canon_module.CANON_FILE_PATH = self.temp_db.name
        
        import asyncio
        asyncio.run(init_db())
    
    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
        if "CANON_FILE_PATH" in os.environ:
            del os.environ["CANON_FILE_PATH"]
    
    def test_ensure_default_canon(self):
        """Test creating default canon for new persona."""
        import asyncio
        
        async def test():
            new_persona = "new_test_persona"
            
            # Ensure default canon (should create empty components)
            await ensure_default_canon(new_persona, author="test")
            
            components = await get_components(new_persona)
            self.assertEqual(len(components), 6)  # One for each component type
            
            # All should be empty content but have explanations
            for comp in components:
                self.assertEqual(comp.content, "")
                self.assertNotEqual(comp.explanation, "")
                self.assertEqual(comp.persona_id, new_persona)
            
            # Verify snapshot was created
            snapshots = await get_snapshots(new_persona, limit=1)
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(snapshots[0].description, "Initial canon creation")
        
        asyncio.run(test())


class TestCanonValidation(unittest.TestCase):
    """Test canon component validation (Canonical Truth Invariant enforcement)."""
    
    def test_validate_canon_component_behavioral_rules_require_explanation(self):
        """Test that BEHAVIORAL_RULES must have an explanation."""
        valid_rule = CanonComponent(
            component_id="valid-rule",
            persona_id=TEST_PERSONA_ID,
            component_type=CanonComponentType.BEHAVIORAL_RULES,
            content="Never kill",
            explanation="Character values all life",
            version="1.0.0",
            author="test",
        )
        warnings = validate_canon_component(valid_rule)
        self.assertIsInstance(warnings, list)
        # Should not raise
        
        # Invalid behavioral rule without explanation
        invalid_rule = CanonComponent(
            component_id="invalid-rule",
            persona_id=TEST_PERSONA_ID,
            component_type=CanonComponentType.BEHAVIORAL_RULES,
            content="Never kill",
            explanation="",  # Missing required explanation
            version="1.0.0",
            author="test",
        )
        with self.assertRaises(CanonValidationError):
            validate_canon_component(invalid_rule)
    
    def test_validate_warns_for_suspicious_content(self):
        """Test validation warns for content that may violate Canonical Truth Invariant."""
        suspicious = CanonComponent(
            component_id="suspicious",
            persona_id=TEST_PERSONA_ID,
            component_type=CanonComponentType.CORE_BELIEFS,
            content="We promised to meet tomorrow",
            explanation="Test",
            version="1.0.0",
            author="test",
        )
        warnings = validate_canon_component(suspicious)
        self.assertTrue(any("Canonical Truth Invariant" in w for w in warnings))
        
        # Also test other prohibited patterns
        patterns = [
            ("the user likes pizza", "User Memory violation"),
            ("conversation history shows", "Conversation History violation"),
            ("in this server", "Guild Context violation"),
        ]
        for content, _ in patterns:
            comp = CanonComponent(
                component_id=f"suspicious-{content[:10]}",
                persona_id=TEST_PERSONA_ID,
                component_type=CanonComponentType.CORE_BELIEFS,
                content=content,
                explanation="Test",
                version="1.0.0",
                author="test",
            )
            warnings = validate_canon_component(comp)
            self.assertTrue(any("Canonical Truth Invariant" in w for w in warnings))


class TestCanonExportImport(unittest.TestCase):
    """Test canon export/import functionality."""
    
    def setUp(self):
        """Set up a temporary canon database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        os.environ["CANON_FILE_PATH"] = self.temp_db.name
        
        import utils.canon as canon_module
        canon_module.CANON_FILE_PATH = self.temp_db.name
        
        import asyncio
        asyncio.run(init_db())
    
    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
        if "CANON_FILE_PATH" in os.environ:
            del os.environ["CANON_FILE_PATH"]
    
    def test_export_import_canon(self):
        """Test exporting and importing canon data."""
        import asyncio
        
        async def test():
            # Create components
            for comp_type in [
                CanonComponentType.CORE_IDENTITY,
                CanonComponentType.CORE_BELIEFS,
            ]:
                component = CanonComponent(
                    component_id=f"export-test-{comp_type.value}",
                    persona_id=TEST_PERSONA_ID,
                    component_type=comp_type,
                    content=f"Export content {comp_type.value}",
                    explanation="Explanation",
                    version="1.0.0",
                    author="test",
                )
                await store_component(component)
            
            # Export
            exported = await export_canon(TEST_PERSONA_ID)
            self.assertEqual(exported["persona_id"], TEST_PERSONA_ID)
            self.assertEqual(len(exported["components"]), 2)
            
            # Import to new persona
            new_persona = "imported_persona"
            count = await import_canon(exported, target_persona_id=new_persona, author="importer")
            self.assertEqual(count, 2)
            
            # Verify imported
            imported_components = await get_components(new_persona)
            self.assertEqual(len(imported_components), 2)
            
            # Verify snapshot created
            snapshots = await get_snapshots(new_persona, limit=1)
            self.assertEqual(len(snapshots), 1)
            self.assertIn("Imported", snapshots[0].description)
        
        asyncio.run(test())


class TestCanonComponentFormatting(unittest.TestCase):
    """Test canon component formatting for prompt assembly."""
    
    def test_format_for_prompt(self):
        """Test the format_for_prompt method."""
        component = CanonComponent(
            component_id="format-test",
            persona_id=TEST_PERSONA_ID,
            component_type=CanonComponentType.CORE_IDENTITY,
            content="I am a test character",
            explanation="This defines my core nature",
            version="1.0.0",
            author="test",
        )
        
        formatted = component.format_for_prompt()
        
        self.assertIn("<core_identity>", formatted)
        self.assertIn("I am a test character", formatted)
        self.assertIn("<!-- Why: This defines my core nature -->", formatted)
        self.assertIn("</core_identity>", formatted)
    
    def test_component_to_dict(self):
        """Test component serialization to dict."""
        component = CanonComponent(
            component_id="dict-test",
            persona_id=TEST_PERSONA_ID,
            component_type=CanonComponentType.MOTIVATIONS,
            content="To protect others",
            explanation="Driven by past trauma",
            version="1.0.0",
            author="test",
            metadata={"source": "author_notes"},
        )
        
        d = component.to_dict()
        
        self.assertEqual(d["component_id"], "dict-test")
        self.assertEqual(d["persona_id"], TEST_PERSONA_ID)
        self.assertEqual(d["component_type"], "motivations")
        self.assertEqual(d["content"], "To protect others")
        self.assertEqual(d["explanation"], "Driven by past trauma")
        self.assertEqual(d["version"], "1.0.0")
        self.assertEqual(d["author"], "test")
        self.assertEqual(d["metadata"], {"source": "author_notes"})


class TestCanonConstants(unittest.TestCase):
    """Test that all expected constants are defined."""
    
    def test_constants_defined(self):
        """Test that all expected constants are defined."""
        self.assertEqual(len(COMPONENT_ASSEMBLY_ORDER), 6)
        self.assertEqual(COMPONENT_ASSEMBLY_ORDER[0], CanonComponentType.CORE_IDENTITY)
        self.assertEqual(COMPONENT_ASSEMBLY_ORDER[-1], CanonComponentType.CANON_EXPLANATIONS)
        
        self.assertEqual(len(COMPONENT_LABELS), 6)
        self.assertEqual(len(COMPONENT_XML_TAGS), 6)
        self.assertEqual(len(DEFAULT_CANON_TEMPLATES), 6)
        
        # Verify all types have labels, tags, and templates
        for comp_type in CanonComponentType:
            self.assertIn(comp_type, COMPONENT_LABELS)
            self.assertIn(comp_type, COMPONENT_XML_TAGS)
            self.assertIn(comp_type, DEFAULT_CANON_TEMPLATES)


class TestCanonSnapshotSerialization(unittest.TestCase):
    """Test canon snapshot serialization."""
    
    def setUp(self):
        """Set up a temporary canon database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        os.environ["CANON_FILE_PATH"] = self.temp_db.name
        
        import utils.canon as canon_module
        canon_module.CANON_FILE_PATH = self.temp_db.name
        
        import asyncio
        asyncio.run(init_db())
    
    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
        if "CANON_FILE_PATH" in os.environ:
            del os.environ["CANON_FILE_PATH"]
    
    def test_snapshot_to_dict(self):
        """Test snapshot serialization."""
        import asyncio
        
        async def test():
            component = CanonComponent(
                component_id="snap-comp",
                persona_id=TEST_PERSONA_ID,
                component_type=CanonComponentType.CORE_IDENTITY,
                content="Test",
                explanation="Test",
                version="1.0.0",
                author="test",
            )
            await store_component(component)
            
            snapshot = await create_snapshot(TEST_PERSONA_ID, "1.0.0", "test", "Test snap")
            d = snapshot.to_dict()
            
            self.assertEqual(d["snapshot_id"], snapshot.snapshot_id)
            self.assertEqual(d["persona_id"], TEST_PERSONA_ID)
            self.assertEqual(d["version"], "1.0.0")
            self.assertEqual(len(d["components"]), 1)
            self.assertEqual(d["author"], "test")
            self.assertEqual(d["description"], "Test snap")
        
        asyncio.run(test())


if __name__ == "__main__":
    unittest.main()