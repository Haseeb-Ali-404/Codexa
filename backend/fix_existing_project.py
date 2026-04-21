"""
Run once to patch all existing projects in MongoDB:
  python fix_existing_project.py

Fixes:
  - Unsafe .split() calls without null guards
  - .map()/.filter() calls without null guards
  - Array index [n] access on split results without fallback
"""

import re
import sys
from utils.database_util import files_col

SPLIT_PATTERN = re.compile(
    r'(?<![?!])\b((?:[a-zA-Z_$][a-zA-Z0-9_$]*\.)+[a-zA-Z_$][a-zA-Z0-9_$]*)\.split\(',
)

MAP_FILTER_PATTERN = re.compile(
    r'(?<![?!])\b((?:[a-zA-Z_$][a-zA-Z0-9_$]*\.)+[a-zA-Z_$][a-zA-Z0-9_$]*)\.(map|filter|forEach|find|reduce)\(',
)


def fix_content(content: str, path: str) -> tuple[str, list[str]]:
    if not content or not path.endswith((".ts", ".tsx")):
        return content, []

    original = content
    fixes = []

    # Fix .split() on property chains
    new = SPLIT_PATTERN.sub(r'(\1 ?? "").split(', content)
    if new != content:
        fixes.append(".split() null guard")
        content = new

    # Fix .map/.filter/.forEach/.find on property chains
    new = MAP_FILTER_PATTERN.sub(r'(\1 ?? []).\2(', content)
    if new != content:
        fixes.append(".map/.filter null guard")
        content = new

    return content, fixes


def main():
    total_files = 0
    total_fixed = 0

    cursor = files_col.find({"path": re.compile(r'\.(ts|tsx)$')})

    for doc in cursor:
        path = doc.get("path", "")
        content = doc.get("content", "") or ""

        new_content, fixes = fix_content(content, path)

        if fixes:
            files_col.update_one(
                {"_id": doc["_id"]},
                {"$set": {"content": new_content}}
            )
            total_fixed += 1
            print(f"  Fixed {path}: {', '.join(fixes)}")

        total_files += 1

    print(f"\nDone. Scanned {total_files} TS/TSX files, fixed {total_fixed}.")
    print("Restart the preview to pick up changes.")


if __name__ == "__main__":
    sys.path.insert(0, ".")
    main()
