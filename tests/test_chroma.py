import unittest
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
        for doc, meta, doc_id in zip(documents, metadatas or [{}] * len(documents), ids or [f"doc-{len(self.docs)}"] * len(documents)):
            self.docs[doc_id] = {"document": doc, "metadata": meta}

    def get(self, *, include=None):
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
            chroma.add_knowledge("Alpha doc", source="manual", title="Alpha")
            entries = chroma.list_knowledge()

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["document"], "Alpha doc")
        self.assertEqual(entries[0]["metadata"]["source"], "manual")
        self.assertEqual(entries[0]["metadata"]["title"], "Alpha")

        with patch.object(chroma, "get_collection", return_value=fake_collection):
            chroma.delete_knowledge(entries[0]["id"])
            entries_after = chroma.list_knowledge()

        self.assertEqual(entries_after, [])


if __name__ == "__main__":
    unittest.main()
