import unittest

import discord

from cogs.ai.genai_generation import GenAIGenerationCog


class TestGenerationSlashAttachments(unittest.TestCase):
    def test_ask_and_write_expose_optional_attachment_options(self):
        for command in (
            GenAIGenerationCog.ask_cmd,
            GenAIGenerationCog.write_cmd,
        ):
            assert command.app_command is not None
            attachment_option = next(
                parameter
                for parameter in command.app_command.parameters
                if parameter.name == "attachment"
            )
            self.assertEqual(
                attachment_option.type,
                discord.AppCommandOptionType.attachment,
            )
            self.assertFalse(attachment_option.required)


if __name__ == "__main__":
    unittest.main()