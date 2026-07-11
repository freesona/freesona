import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.memory import get_interaction_id, set_interaction_id, clear_interaction_id


class InteractionMemoryTests(unittest.TestCase):
    def tearDown(self):
        clear_interaction_id(100)

    def test_user_scoped_interaction_id_storage(self):
        set_interaction_id(10, 100, 200, "user-a")
        set_interaction_id(10, 100, 201, "user-b")

        self.assertEqual(get_interaction_id(10, 100, 200), "user-a")
        self.assertEqual(get_interaction_id(10, 100, 201), "user-b")
        self.assertIsNone(get_interaction_id(10, 100, 202))

    def test_clear_channel_clears_all_user_scopes(self):
        set_interaction_id(10, 100, 200, "id-a")
        set_interaction_id(10, 100, 201, "id-b")

        clear_interaction_id(100)

        self.assertIsNone(get_interaction_id(10, 100, 200))
        self.assertIsNone(get_interaction_id(10, 100, 201))


if __name__ == "__main__":
    unittest.main()
