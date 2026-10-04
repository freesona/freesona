---
name: sanitize
description: Cleans the project from unnecessary log files or unused py files
---

After completing a task, clean up the repository before considering the work finished. Remove any temporary, experimental, diagnostic, or generated files created during the task that are not required by the final implementation. This includes unnecessary `.py`, `.txt`, `.log`, JSON, YAML, scratch, debug, test-output, dumped-response, profiling, and one-off script files. Do not leave behind scripts created only to inspect, debug, test, migrate, or troubleshoot something if their functionality is not intended to become part of the project. Do not delete or modify pre-existing user files unless explicitly asked. Review the working tree and final diff, and make sure every newly created file has a clear purpose in the completed change. The repository should be left in a clean state with only files that belong to the finished task.
