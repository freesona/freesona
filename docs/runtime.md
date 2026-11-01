# Runtime Controls

This document follows ASD-STE100 Simplified Technical English.

This document describes the runtime commands available in Freesona.

## Module management

The `genai` module is an aggregate loader that registers AI commands by type-specific cogs (listener, generation, persona, memory, channel, autonomy).

```text
/module list
/module enable <name>
/module disable <name>
/module reload <name>
```

## Model management

The bot owner can switch providers and models without restarting:

```text
/model show
/model set <model>
/model reset
/model temperature <value>
/model temperature_reset
/provider show
/provider set <name>
/provider reset
/sync
/reboot
/docs
```

## Configuration management

Runtime configuration is managed with `/config` commands:

```text
/config list
/config show [key]
/config set <key> <value>
/config reset <key>
/config edit
/config view
/config reset-interactive
/config dump
```

## Logging

Logging is controlled with `/logging` commands:

```text
/logging status
/logging enable <section>
/logging disable <section>
/logging toggle <section>
/logging setchannel <#ch>
/logging clearchannel
/logging setlevel <level>
/logging test [message]
```

## Timezone and autonomy

Timezone and autonomy are configurable at runtime:

```text
/settimezone <timezone>
/timezone
/autonomy on
/autonomy off
/autonomy frequency <low/default/high>
/chatmode all
/chatmode mentions
/chatmode smart
```

## RSS/Atom feeds

RSS/Atom feeds can be read and managed with:

```text
/rss list
/rss latest <feed>
/rss add <name> <url>
/rss remove <name>
/rss setchannel <#channel>
/rss clearchannel
```
