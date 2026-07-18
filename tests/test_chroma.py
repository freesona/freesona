import io
import unittest
import zipfile
from unittest.mock import patch

from utils import chroma


class FakeCollection:
    def __init__(self):
        self.added = []
        self.deleted_ids = []
        self.docs = {}

    def add(self, *, documents, metadatas=None, ids=None):
        self.added.append({
            "documents": documents,
            "metadatas": metadatas or [],
            "ids": ids or [],
        })

        # Provide fallback defaults per item so zip doesn't evaluate to empty list
        meta_list = metadatas if metadatas is not None else [{}] * len(documents)
        id_list = ids if ids is not None else [f"doc-{i}" for i in range(len(documents))]

        for doc, meta, doc_id in zip(documents, meta_list, id_list):
            self.docs[doc_id] = {"document": doc, "metadata": meta}

    def get(self, *, limit=None, include=None, where=None):
        docs = []
        metadatas = []
        ids = []
        for doc_id, item in self.docs.items():
            if where and "persona" in where:
                if item["metadata"].get("persona") != where["persona"]:
                    continue
            ids.append(doc_id)
            docs.append(item["document"])
            metadatas.append(item["metadata"])
        return {"ids": ids, "documents": docs, "metadatas": metadatas}

    def query(self, *, query_texts, n_results, where=None, include=None):
        # Simple mock query that filters by persona if provided
        filtered_docs = []
        filtered_metadatas = []
        filtered_ids = []
        
        for doc_id, item in self.docs.items():
            if where and "persona" in where:
                if item["metadata"].get("persona") != where["persona"]:
                    continue
            filtered_ids.append(doc_id)
            filtered_docs.append(item["document"])
            filtered_metadatas.append(item["metadata"])
            if len(filtered_ids) >= n_results:
                break
        
        # Return in ChromaDB format: list of lists
        return {
            "ids": [filtered_ids],
            "documents": [filtered_docs],
            "metadatas": [filtered_metadatas],
            "distances": [[0.1] * len(filtered_docs)],
        }

    def delete(self, ids):
        self.deleted_ids.extend(ids)
        for doc_id in ids:
            self.docs.pop(doc_id, None)


class ChromaKnowledgeBaseTests(unittest.TestCase):
    def test_add_list_delete_knowledge_round_trip(self):
        fake_collection = FakeCollection()

        valid_metadata = {
            "persona": "test_persona",
            "source": "Test Source",
            "source_type": "anime",
            "entry_type": "dialogue",
            "topics": ["testing", "validation"],
        }

        with patch.object(chroma, "get_collection", return_value=fake_collection):
            doc_id = chroma.add_knowledge("Alpha doc", source="manual", title="Alpha", metadata=valid_metadata)
            entries = chroma.list_knowledge()

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["document"], "Alpha doc")
        # Metadata source takes precedence over function parameter
        self.assertEqual(entries[0]["metadata"]["source"], "Test Source")
        self.assertEqual(entries[0]["metadata"]["title"], "Alpha")
        self.assertEqual(entries[0]["metadata"]["persona"], "test_persona")
        self.assertEqual(entries[0]["metadata"]["entry_type"], "dialogue")
        # topics are normalized to comma-separated string
        self.assertEqual(entries[0]["metadata"]["topics"], "testing, validation")

        with patch.object(chroma, "get_collection", return_value=fake_collection):
            chroma.delete_knowledge(entries[0]["id"])
            entries_after = chroma.list_knowledge()

        self.assertEqual(entries_after, [])

    def test_add_knowledge_rejects_missing_metadata(self):
        """Test that add_knowledge rejects entries with missing required metadata fields."""
        fake_collection = FakeCollection()
        
        # Missing required fields
        invalid_metadata = {
            "persona": "test_persona",
            # missing source, source_type, entry_type, topics
        }
        
        with patch.object(chroma, "get_collection", return_value=fake_collection):
            doc_id = chroma.add_knowledge("Test doc", metadata=invalid_metadata)
        
        self.assertEqual(doc_id, "")  # Should return empty string on validation failure

    def test_add_knowledge_rejects_invalid_entry_type(self):
        """Test that add_knowledge rejects invalid entry_type values."""
        fake_collection = FakeCollection()
        
        invalid_metadata = {
            "persona": "test_persona",
            "source": "Test Source",
            "source_type": "anime",
            "entry_type": "invalid_type",
            "topics": ["testing"],
        }
        
        with patch.object(chroma, "get_collection", return_value=fake_collection):
            doc_id = chroma.add_knowledge("Test doc", metadata=invalid_metadata)
        
        self.assertEqual(doc_id, "")

    def test_add_knowledge_rejects_invalid_source_type(self):
        """Test that add_knowledge rejects invalid source_type values."""
        fake_collection = FakeCollection()
        
        invalid_metadata = {
            "persona": "test_persona",
            "source": "Test Source",
            "source_type": "invalid_source",
            "entry_type": "dialogue",
            "topics": ["testing"],
        }
        
        with patch.object(chroma, "get_collection", return_value=fake_collection):
            doc_id = chroma.add_knowledge("Test doc", metadata=invalid_metadata)
        
        self.assertEqual(doc_id, "")

    def test_add_knowledge_rejects_empty_topics(self):
        """Test that add_knowledge rejects empty topics list."""
        fake_collection = FakeCollection()
        
        invalid_metadata = {
            "persona": "test_persona",
            "source": "Test Source",
            "source_type": "anime",
            "entry_type": "dialogue",
            "topics": [],  # Empty list
        }
        
        with patch.object(chroma, "get_collection", return_value=fake_collection):
            doc_id = chroma.add_knowledge("Test doc", metadata=invalid_metadata)
        
        self.assertEqual(doc_id, "")

    def test_query_knowledge_filters_by_persona(self):
        """Test that query_knowledge correctly filters by persona."""
        fake_collection = FakeCollection()
        
        # Add entries for two different personas
        metadata_a = {
            "persona": "persona_a",
            "source": "Source A",
            "source_type": "anime",
            "entry_type": "dialogue",
            "topics": ["topic_a"],
        }
        metadata_b = {
            "persona": "persona_b",
            "source": "Source B",
            "source_type": "novel",
            "entry_type": "narration",
            "topics": ["topic_b"],
        }
        
        with patch.object(chroma, "get_collection", return_value=fake_collection):
            chroma.add_knowledge("Persona A content", metadata=metadata_a)
            chroma.add_knowledge("Persona B content", metadata=metadata_b)
            
            # Query for persona_a only
            results_a = chroma.query_knowledge("content", limit=5, persona="persona_a")
            results_b = chroma.query_knowledge("content", limit=5, persona="persona_b")
            results_all = chroma.query_knowledge("content", limit=5)
        
        # Should only return persona_a entries
        self.assertEqual(len(results_a), 1)
        self.assertEqual(results_a[0]["metadata"]["persona"], "persona_a")
        
        # Should only return persona_b entries
        self.assertEqual(len(results_b), 1)
        self.assertEqual(results_b[0]["metadata"]["persona"], "persona_b")
        
        # Should return all entries when no persona filter
        self.assertEqual(len(results_all), 2)

    def test_get_knowledge_by_persona(self):
        """Test retrieving all knowledge for a specific persona."""
        fake_collection = FakeCollection()
        
        metadata_a = {
            "persona": "persona_a",
            "source": "Source A",
            "source_type": "anime",
            "entry_type": "dialogue",
            "topics": ["topic_a"],
        }
        metadata_b = {
            "persona": "persona_b",
            "source": "Source B",
            "source_type": "novel",
            "entry_type": "narration",
            "topics": ["topic_b"],
        }
        
        with patch.object(chroma, "get_collection", return_value=fake_collection):
            chroma.add_knowledge("Persona A content 1", metadata=metadata_a)
            chroma.add_knowledge("Persona A content 2", metadata=metadata_a)
            chroma.add_knowledge("Persona B content", metadata=metadata_b)
            
            results = chroma.get_knowledge_by_persona("persona_a", limit=10)
        
        self.assertEqual(len(results), 2)
        for entry in results:
            self.assertEqual(entry["metadata"]["persona"], "persona_a")

    def test_extract_text_from_epub_bytes(self):
        epub_buffer = io.BytesIO()
        with zipfile.ZipFile(epub_buffer, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
            zf.writestr(
                "META-INF/container.xml",
                """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""",
            )
            zf.writestr(
                "OEBPS/content.opf",
                """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="https://www.idpf.org/2007/opf" xmlns:dc="https://purl.org/dc/elements/1.1/" version="3.0">
  <metadata><dc:title>Example</dc:title></metadata>
  <manifest>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="chapter1"/></spine>
</package>""",
            )
            zf.writestr(
                "OEBPS/chapter1.xhtml",
                """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Chapter One</h1><p>Alpha content for test.</p></body></html>""",
            )

        text = chroma.extract_text_from_bytes("sample.epub", epub_buffer.getvalue())
        self.assertIn("Chapter One", text)
        self.assertIn("Alpha content for test.", text)

    def test_add_knowledge_accepts_optional_fields(self):
        """Test that add_knowledge accepts optional metadata fields (chapter, timestamp, canon_level, tags)."""
        fake_collection = FakeCollection()
        
        metadata_with_optionals = {
            "persona": "test_persona",
            "source": "Test Source",
            "source_type": "novel",
            "entry_type": "narration",
            "topics": ["testing"],
            "episode": "05",
            "chapter": "Chapter 12",
            "scene": "Library",
            "speaker": "Narrator",
            "timestamp": "2023-01-15",
            "canon_level": "canon",
            "tags": ["canon", "key_moment"],
        }
        
        with patch.object(chroma, "get_collection", return_value=fake_collection):
            doc_id = chroma.add_knowledge("Test doc with optionals", metadata=metadata_with_optionals)
        
        self.assertNotEqual(doc_id, "")
        
        with patch.object(chroma, "get_collection", return_value=fake_collection):
            entries = chroma.list_knowledge()
        
        self.assertEqual(len(entries), 1)
        meta = entries[0]["metadata"]
        self.assertEqual(meta["chapter"], "Chapter 12")
        self.assertEqual(meta["timestamp"], "2023-01-15")
        self.assertEqual(meta["canon_level"], "canon")
        self.assertEqual(meta["tags"], "canon, key_moment")
        self.assertEqual(meta["episode"], "05")
        self.assertEqual(meta["scene"], "Library")

    def test_add_knowledge_rejects_invalid_canon_level(self):
        """Test that add_knowledge rejects invalid canon_level values."""
        fake_collection = FakeCollection()
        
        invalid_metadata = {
            "persona": "test_persona",
            "source": "Test Source",
            "source_type": "anime",
            "entry_type": "dialogue",
            "topics": ["testing"],
            "canon_level": "invalid_canon",
        }
        
        with patch.object(chroma, "get_collection", return_value=fake_collection):
            doc_id = chroma.add_knowledge("Test doc", metadata=invalid_metadata)
        
        self.assertEqual(doc_id, "")

    def test_clean_source_text(self):
        """Test the clean_source_text utility function."""
        # Test line ending normalization
        text = "Line 1\r\nLine 2\rLine 3\nLine 4"
        cleaned = chroma.clean_source_text(text)
        self.assertNotIn("\r", cleaned)
        self.assertEqual(cleaned, "Line 1\nLine 2\nLine 3\nLine 4")
        
        # Test excessive blank line removal
        text = "Line 1\n\n\n\nLine 2\n\n\nLine 3"
        cleaned = chroma.clean_source_text(text)
        self.assertEqual(cleaned, "Line 1\n\nLine 2\n\nLine 3")
        
        # Test empty input
        self.assertEqual(chroma.clean_source_text(""), "")
        self.assertEqual(chroma.clean_source_text(None), "")

    def test_identify_speakers(self):
        """Test the identify_speakers utility function."""
        text = "Chisato: Hello there!\nTakina: Hi.\nNarrator: The sun shone."
        speakers = chroma.identify_speakers(text)
        
        self.assertEqual(len(speakers), 3)
        self.assertEqual(speakers[0]["speaker"], "Chisato")
        self.assertEqual(speakers[0]["dialogue"], "Hello there!")
        self.assertEqual(speakers[1]["speaker"], "Takina")
        self.assertEqual(speakers[1]["dialogue"], "Hi.")
        self.assertEqual(speakers[2]["speaker"], "Narrator")
        self.assertEqual(speakers[2]["dialogue"], "The sun shone.")

    def test_chunk_semantic_units_dialogue(self):
        """Test chunking with speaker data."""
        speaker_data = [
            {"speaker": "Chisato", "dialogue": "Hello!"},
            {"speaker": "Chisato", "dialogue": "How are you?"},
            {"speaker": "Takina", "dialogue": "I'm fine."},
            {"speaker": "Takina", "dialogue": "And you?"},
        ]
        
        chunks = chroma.chunk_semantic_units("", speaker_data=speaker_data, max_chunk_size=100)
        
        # Should create chunks grouped by speaker
        self.assertGreaterEqual(len(chunks), 2)
        # First chunk should have Chisato
        self.assertEqual(chunks[0]["speaker"], "Chisato")
        # Last chunk should have Takina
        self.assertEqual(chunks[-1]["speaker"], "Takina")

    def test_chunk_semantic_units_narration(self):
        """Test chunking narration without speaker data."""
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        
        chunks = chroma.chunk_semantic_units(text, max_chunk_size=50, min_chunk_size=10)
        
        self.assertGreater(len(chunks), 0)
        for chunk in chunks:
            self.assertIsNone(chunk["speaker"])
            self.assertGreater(len(chunk["document"]), 0)

    def test_assign_metadata(self):
        """Test the assign_metadata utility function."""
        chunks = [
            {"document": "Chisato: Hello!", "speaker": "Chisato", "estimated_tokens": 5},
            {"document": "The sun rose.", "speaker": "Narrator", "estimated_tokens": 4},
        ]
        
        base_metadata = {
            "persona": "test_persona",
            "source": "Test Source",
            "source_type": "anime",
            "entry_type": "narration",
            "topics": ["greeting"],
        }
        
        results = chroma.assign_metadata(chunks, base_metadata)
        
        self.assertEqual(len(results), 2)
        # First chunk has speaker -> entry_type should be dialogue
        self.assertEqual(results[0]["metadata"]["entry_type"], "dialogue")
        self.assertEqual(results[0]["metadata"]["speaker"], "Chisato")
        # Second chunk has no speaker (Narrator) -> entry_type should be narration
        self.assertEqual(results[1]["metadata"]["entry_type"], "narration")
        self.assertNotIn("speaker", results[1]["metadata"])

    def test_ingest_source_full_pipeline(self):
        """Test the full ingest_source pipeline."""
        raw_text = "Chisato: I'll protect everyone!\nTakina: I'll help too.\n\nThe aquarium shimmered with light."
        
        base_metadata = {
            "persona": "chisato_nishikigi",
            "source": "Episode 06",
            "source_type": "anime",
            "entry_type": "dialogue",
            "topics": ["friendship", "optimism"],
            "episode": "06",
            "scene": "Aquarium",
        }
        
        results = chroma.ingest_source(raw_text, base_metadata)
        
        self.assertGreater(len(results), 0)
        for result in results:
            self.assertIn("document", result)
            self.assertIn("metadata", result)
            self.assertEqual(result["metadata"]["persona"], "chisato_nishikigi")
            self.assertEqual(result["metadata"]["source"], "Episode 06")
            self.assertIn("topics", result["metadata"])


if __name__ == "__main__":
    unittest.main()