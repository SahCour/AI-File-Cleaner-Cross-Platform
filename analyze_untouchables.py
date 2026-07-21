#!/usr/bin/env python3
"""
Deep analysis of files_to_process.json to find ALL potentially untouchable files.
Goes beyond simple pattern matching — analyzes directory structures,
app bundles, service folders, and cross-references with known macOS services.
"""

import json
import re
import os
from collections import defaultdict, Counter

with open('files_to_process.json', 'r') as f:
    data = json.load(f)

print(f"Total files in dataset: {len(data)}")
print("=" * 80)

# ============================================================================
# 1. SYSTEM / SERVICE PATH PATTERNS (Comprehensive macOS blacklist)
# ============================================================================
SYSTEM_PATTERNS = {
    'Microsoft Office Data': r'Microsoft User Data',
    'macOS Library': r'/Library/',
    'System Folder': r'/System/',
    'Applications Bundle': r'\.app/',
    'Bundle/Plugin': r'\.(bundle|plugin|kext|framework|dylib)(/|$)',
    'Xcode Project': r'\.(xcodeproj|xcworkspace)/',
    'Git Repository Internals': r'/\.git/',
    'Node Modules': r'/node_modules/',
    'Python venv': r'/(venv|\.venv|__pycache__)/',
    'macOS Containers': r'/(Containers|Group Containers)/',
    'Adobe Service Data': r'/Adobe/',
    'Trash': r'/\.Trash/',
    'Hidden System Files': r'/\.[A-Z]',  # .DS_Store, .Spotlight, etc
    'iCloud Internal': r'com~apple~CloudDocs',
    'Automator Workflows': r'\.(workflow|action)/',
    'Spotlight Index': r'\.Spotlight',
    'Time Machine': r'\.MobileBackups',
    'Caches': r'/Caches/',
    'Preferences': r'/Preferences/',
    'Saved Application State': r'/Saved Application State/',
    'Package Contents': r'/Contents/(Resources|MacOS|Frameworks|PlugIns)/',
}

# ============================================================================
# 2. FILE EXTENSION PATTERNS (potentially dangerous to move)
# ============================================================================
DANGEROUS_EXTENSIONS = {
    'Database files': ['.db', '.sqlite', '.sqlite3', '.realm'],
    'Config files': ['.plist', '.conf', '.cfg', '.ini', '.yaml', '.yml'],
    'Workflow files': ['.wflow', '.action', '.workflow'],
    'Certificate/Key files': ['.pem', '.key', '.cer', '.p12', '.keychain'],
    'Lock files': ['.lock', '.pid'],
    'Log files': ['.log'],
    'Binary/Compiled': ['.dylib', '.so', '.o', '.a'],
}

# ============================================================================
# 3. DIRECTORY DEPTH ANALYSIS (files deep inside app/service hierarchies)
# ============================================================================

print("\n" + "=" * 80)
print("SECTION 1: Files matching SYSTEM/SERVICE path patterns")
print("=" * 80)

system_files = defaultdict(list)
safe_files = []

for file in data:
    path = file.get('path', '')
    matched = False
    for name, pattern in SYSTEM_PATTERNS.items():
        if re.search(pattern, path, re.IGNORECASE):
            system_files[name].append(path)
            matched = True
            break
    if not matched:
        safe_files.append(file)

for name, files in sorted(system_files.items(), key=lambda x: -len(x[1])):
    print(f"\n🔒 {name}: {len(files)} files")
    for f in files[:3]:
        print(f"   Example: {f}")
    if len(files) > 3:
        print(f"   ... and {len(files) - 3} more")

print(f"\n✅ Safe files (no system pattern match): {len(safe_files)}")

# ============================================================================
# 4. DANGEROUS EXTENSIONS in remaining "safe" files
# ============================================================================

print("\n" + "=" * 80)
print("SECTION 2: Potentially dangerous FILE EXTENSIONS in 'safe' files")
print("=" * 80)

dangerous_ext_files = defaultdict(list)
for file in safe_files:
    ext = file.get('extension', '').lower()
    for category, exts in DANGEROUS_EXTENSIONS.items():
        if ext in exts:
            dangerous_ext_files[category].append(file)
            break

for cat, files in sorted(dangerous_ext_files.items(), key=lambda x: -len(x[1])):
    print(f"\n⚠️  {cat}: {len(files)} files")
    for f in files[:3]:
        print(f"   {f['path']}")
    if len(files) > 3:
        print(f"   ... and {len(files) - 3} more")

# ============================================================================
# 5. UNIQUE ROOT DIRECTORIES (where do all files come from?)
# ============================================================================

print("\n" + "=" * 80)
print("SECTION 3: Source directories breakdown")
print("=" * 80)

root_dirs = Counter()
for file in data:
    path = file.get('path', '')
    # Extract top 3 levels: /Users/mac/Downloads or /Users/mac/Documents/Subfolder
    parts = path.split('/')
    if len(parts) >= 4:
        root = '/'.join(parts[:4])
    else:
        root = path
    root_dirs[root] += 1

for root, count in root_dirs.most_common(20):
    print(f"  {count:5d} files <- {root}")

# ============================================================================
# 6. POTENTIAL "ATOMIC" PROJECT FOLDERS (should not be split)
# ============================================================================

print("\n" + "=" * 80)
print("SECTION 4: Potential 'atomic' project folders (should move as a unit)")
print("=" * 80)

# Group files by their parent directory
parent_dirs = defaultdict(list)
for file in data:
    path = file.get('path', '')
    parent = os.path.dirname(path)
    parent_dirs[parent].append(file)

# Find dirs with multiple files of different suggested_folders (conflict!)
conflicts = []
for parent, files in parent_dirs.items():
    if len(files) < 2:
        continue
    suggested = set(f.get('suggested_folder', '') for f in files)
    if len(suggested) > 1:
        conflicts.append((parent, len(files), suggested))

conflicts.sort(key=lambda x: -x[1])
for parent, count, suggested in conflicts[:15]:
    print(f"\n⚡ CONFLICT: {parent}")
    print(f"   {count} files, AI suggested {len(suggested)} different folders:")
    for s in list(suggested)[:4]:
        print(f"     -> {s}")

# ============================================================================
# 7. SUMMARY
# ============================================================================

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

total_system = sum(len(v) for v in system_files.values())
total_dangerous_ext = sum(len(v) for v in dangerous_ext_files.values())

print(f"  Total files:                   {len(data)}")
print(f"  🔒 System/Service files:        {total_system}")
print(f"  ⚠️  Dangerous extension files:   {total_dangerous_ext}")
print(f"  ⚡ Conflicting parent dirs:      {len(conflicts)}")
print(f"  ✅ Clearly safe files:           {len(safe_files) - total_dangerous_ext}")
