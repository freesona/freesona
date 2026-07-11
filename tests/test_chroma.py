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

    def get(self, *, limit=None, include=None):
        docs = []
        metadatas = []
        ids = []
        for doc_id, item in self.docs.items():
            ids.append(doc_id)
            docs.append(item["document"])
            metadatas.append(item["metadata"])
        return {"ids": ids, "documents": docs, "metadatas": metadatas}

    def delete(self, ids):
        self.deleted_ids.extend(ids)
        for doc_id in ids:
            self.docs.pop(doc_id, None)


class ChromaKnowledgeBaseTests(unittest.TestCase):
    def test_add_list_delete_knowledge_round_trip(self):
        fake_collection = FakeCollection()

        with patch.object(chroma, "get_collection", return_value=fake_collection):
            doc_id = chroma.add_knowledge("Alpha doc", source="manual", title="Alpha")
            entries = chroma.list_knowledge()

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["document"], "Alpha doc")
        self.assertEqual(entries[0]["metadata"]["source"], "manual")
        self.assertEqual(entries[0]["metadata"]["title"], "Alpha")

        with patch.object(chroma, "get_collection", return_value=fake_collection):
            chroma.delete_knowledge(entries[0]["id"])
            entries_after = chroma.list_knowledge()

        self.assertEqual(entries_after, [])

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
<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/" version="3.0">
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


if __name__ == "__main__":
    unittest.main()