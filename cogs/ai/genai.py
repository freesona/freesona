# cogs/ai/genai.py: Aggregate AI extension loader for split command-type cogs.

from utils.persona import LEGACY_DETECTED  # noqa: F401

from .genai_autonomy import GenAIAutonomyCog
from .genai_channel import GenAIChannelCog
from .genai_common import BOT_NAME  # noqa: F401
from .genai_generation import GenAIGenerationCog
from .genai_listener import GenAIListenerCog
from .genai_memory import GenAIMemoryCog
from .genai_persona import GenAIPersonaCog

# Backward-compatible alias retained for code that imports GenAICog directly.
GenAICog = GenAIListenerCog


async def setup(bot):
    await bot.add_cog(GenAIListenerCog(bot))
    await bot.add_cog(GenAIGenerationCog(bot))
    await bot.add_cog(GenAIPersonaCog(bot))
    await bot.add_cog(GenAIMemoryCog(bot))
    await bot.add_cog(GenAIChannelCog(bot))
    await bot.add_cog(GenAIAutonomyCog(bot))
