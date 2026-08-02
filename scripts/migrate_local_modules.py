import ast
import json
import os
import sys

# Hardcoded built-in modules as they existed before this refactor.
KNOWN_BUILTIN_MODULES = {
    "hello": "cogs.fun.hello",
    "random": "cogs.fun.random",
    "moderation": "cogs.moderation.core",
    "genai": "cogs.ai.genai",
    "math": "cogs.tools.math",
    "news": "cogs.system.news",
    "ytdlp": "cogs.media.ytdlp",
    "mvsep": "cogs.media.mvsep",
    "warns": "cogs.moderation.warns",
    "chroma": "cogs.ai.chroma",
    "module": "cogs.system.system",
    "model": "cogs.system.system",
    "provider": "cogs.system.system",
    "config": "cogs.system.system",
    "logging": "cogs.system.system",
    "core": "cogs.system.system",
}

def migrate(file_path):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        sys.exit(1)

    print(f"Reading {file_path}...")
    with open(file_path, "r") as f:
        tree = ast.parse(f.read())

    optional_modules = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'OPTIONAL_MODULES':
                    optional_modules = ast.literal_eval(node.value)
                    break
    
    if optional_modules is None:
        print("Could not find OPTIONAL_MODULES dictionary in the file.")
        sys.exit(1)

    print("Found OPTIONAL_MODULES.")
    
    local_modules = {
        k: v for k, v in optional_modules.items()
        if k not in KNOWN_BUILTIN_MODULES or KNOWN_BUILTIN_MODULES[k] != v
    }

    if not local_modules:
        print("No deployment-specific modules found.")
        sys.exit(0)

    print(f"Found deployment-specific modules: {local_modules}")
    
    if os.path.exists("modules.local.json"):
        print("modules.local.json already exists. Please manually merge the findings.")
        sys.exit(1)

    with open("modules.local.json", "w") as f:
        json.dump(local_modules, f, indent=4)
    
    print("Successfully created modules.local.json.")
    print("Please verify the file content.")

if __name__ == "__main__":
    file_path = "utils/modules.py"
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    migrate(file_path)
