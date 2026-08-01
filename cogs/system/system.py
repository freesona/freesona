# cogs/system/system.py: Aggregate system extension loader
# for split command-type cogs.
# Mirrors the pattern used in cogs/ai/genai.py

from .config import ConfigCog
from .core import CoreCog
from .logging import LoggingCog
from .model import ModelCog
from .module import ModuleCog
from .provider import ProviderCog
from .timezone import TimezoneCog


async def setup(bot):
    await bot.add_cog(ModuleCog(bot))
    await bot.add_cog(ModelCog(bot))
    await bot.add_cog(ProviderCog(bot))
    await bot.add_cog(ConfigCog(bot))
    await bot.add_cog(LoggingCog(bot))
    await bot.add_cog(CoreCog(bot))
    await bot.add_cog(TimezoneCog(bot))
