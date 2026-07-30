# cogs/system/system.py: Aggregate system extension loader for split command-type cogs.
# Mirrors the pattern used in cogs/ai/genai.py

from .module import ModuleCog
from .model import ModelCog
from .provider import ProviderCog
from .config import ConfigCog
from .logging import LoggingCog
from .core import CoreCog
from .timezone import TimezoneCog


async def setup(bot):
    await bot.add_cog(ModuleCog(bot))
    await bot.add_cog(ModelCog(bot))
    await bot.add_cog(ProviderCog(bot))
    await bot.add_cog(ConfigCog(bot))
    await bot.add_cog(LoggingCog(bot))
    await bot.add_cog(CoreCog(bot))
    await bot.add_cog(TimezoneCog(bot))