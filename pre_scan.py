#!/usr/bin/env python3
"""
pre_scan.py — Предварительное сканирование файлов для определения уровня защиты.

Добавляет к каждому файлу в files_to_process.json поля:
  - protection: "system" | "app_storage" | "dev_project" | null
  - protection_reason: str | null
  - is_icloud_stub: bool
  - is_locked_by_process: bool  
  - locked_by: str | null
  - atomic_project: str | null
  - has_alias: bool
  - alias_path: str | null
"""

import json
import os
import re
import subprocess
import unicodedata

INPUT_FILE = 'files_to_process.json'
OUTPUT_FILE = 'files_to_process.json'

# ============================================================================
# BLACKLISTS
# ============================================================================

SYSTEM_PATH_PATTERNS = [
    (r'Microsoft User Data', 'Microsoft Office service files'),
    (r'/Library/', 'macOS Library folder'),
    (r'/System/', 'macOS System folder'),
    (r'\.app/Contents/', 'Application bundle contents'),
    (r'\.(bundle|plugin|kext|framework)(/|$)', 'System plugin/framework'),
    (r'/(Containers|Group Containers)/', 'App sandbox container'),
    (r'/\.Trash/', 'Trash folder'),
    (r'/Caches/', 'System cache'),
    (r'/Preferences/', 'System preferences'),
    (r'/Saved Application State/', 'Saved app state'),
]

APP_STORAGE_PATTERNS = [
    (r'WhisperNotes/', 'WhisperNotes app storage'),
    (r'GarageBand/', 'GarageBand project storage'),
    (r'iMovie .+\.rcproject', 'iMovie project'),
    (r'Final Cut .+\.fcpbundle', 'Final Cut Pro project'),
    (r'Logic Pro/', 'Logic Pro project storage'),
]

DEV_PROJECT_MARKERS = {
    '.git': 'Git repository',
    'docker-compose.yml': 'Docker project',
    'docker-compose.yaml': 'Docker project',
    'package.json': 'Node.js project',
    'requirements.txt': 'Python project',
    'Pipfile': 'Python (Pipenv) project',
    'pyproject.toml': 'Python project',
    'Cargo.toml': 'Rust project',
    'go.mod': 'Go project',
    'Gemfile': 'Ruby project',
    'pom.xml': 'Maven/Java project',
    'build.gradle': 'Gradle/Java project',
    'Makefile': 'Make project',
    'CMakeLists.txt': 'CMake project',
}

XCODE_MARKERS = ['.xcodeproj', '.xcworkspace']

# ============================================================================
# DETECTION FUNCTIONS
# ============================================================================

def detect_system(path):
    """Check if file is in a system/service path."""
    for pattern, reason in SYSTEM_PATH_PATTERNS:
        if re.search(pattern, path, re.IGNORECASE):
            return reason
    return None


def detect_app_storage(path):
    """Check if file belongs to an app's internal storage."""
    for pattern, reason in APP_STORAGE_PATTERNS:
        if re.search(pattern, path, re.IGNORECASE):
            return reason
    return None


def detect_dev_projects(all_files):
    """
    Scan parent directories of all files to find dev project markers.
    Returns a dict: { dir_path: (project_name, marker_reason) }
    """
    # Collect all unique parent directories
    parent_dirs = set()
    for f in all_files:
        path = f.get('path', '')
        parent = os.path.dirname(path)
        # Walk up the tree to check all ancestors
        while parent and parent != '/':
            parent_dirs.add(parent)
            parent = os.path.dirname(parent)

    # Top-level user dirs should never be treated as projects
    EXCLUDE_DIRS = {
        os.path.expanduser('~/Documents'),
        os.path.expanduser('~/Downloads'),
        os.path.expanduser('~/Desktop'),
        os.path.expanduser('~'),
    }

    project_roots = {}

    for d in parent_dirs:
        if d in EXCLUDE_DIRS:
            continue
        # Check for marker files
        for marker, reason in DEV_PROJECT_MARKERS.items():
            marker_path = os.path.join(d, marker)
            if os.path.exists(marker_path):
                project_name = os.path.basename(d)
                project_roots[d] = (project_name, reason)
                break

        # Check for Xcode projects
        if d not in project_roots:
            for xc_marker in XCODE_MARKERS:
                if d.endswith(xc_marker):
                    project_name = os.path.basename(os.path.dirname(d))
                    project_roots[os.path.dirname(d)] = (project_name, 'Xcode project')
                    break

    return project_roots


def check_icloud_stub(path):
    """
    Check if a file is an iCloud stub (evicted/not downloaded).
    iCloud stubs have a special extended attribute or are dataless.
    """
    try:
        # Method 1: Check for .icloud placeholder file
        dirname = os.path.dirname(path)
        basename = os.path.basename(path)
        icloud_name = os.path.join(dirname, '.' + basename + '.icloud')
        if os.path.exists(icloud_name):
            return True

        # Method 2: Check file flags via xattr
        try:
            result = subprocess.run(
                ['xattr', '-l', path],
                capture_output=True, timeout=5
            )
            stdout_text = result.stdout.decode('utf-8', errors='replace')
            if 'com.apple.icloud' in stdout_text:
                return True
        except (subprocess.TimeoutExpired, OSError):
            pass

        # Method 3: Check if file size is 0 but expected to be non-zero
        stat = os.stat(path)
        if stat.st_size == 0:
            # Could be a stub, but also could be genuinely empty
            # We'll flag it but not block
            pass

        return False
    except (OSError, subprocess.TimeoutExpired):
        return False


def check_locked_files(paths_batch):
    """
    Use lsof to check which files are currently open by other processes.
    Processes a batch at once for efficiency.
    Returns dict: { path: process_name }
    """
    locked = {}
    try:
        # Run lsof once for efficiency - check all open files
        result = subprocess.run(
            ['lsof', '-Fn', '+D', os.path.expanduser('~/Documents'),
             '+D', os.path.expanduser('~/Downloads'),
             '+D', os.path.expanduser('~/Desktop')],
            capture_output=True, text=True, timeout=30
        )

        # Parse lsof output: lines starting with 'p' = PID, 'c' = command, 'n' = name
        current_cmd = ''
        for line in result.stdout.split('\n'):
            if line.startswith('c'):
                current_cmd = line[1:]
            elif line.startswith('n'):
                filepath = line[1:]
                if filepath in paths_batch:
                    locked[filepath] = current_cmd
    except (subprocess.TimeoutExpired, OSError):
        pass

    return locked


def find_aliases(target_paths):
    """
    Find Finder Aliases that point to files in our list.
    Returns dict: { target_path: alias_path }
    """
    aliases = {}
    try:
        # Use mdfind to find all aliases
        result = subprocess.run(
            ['mdfind', 'kMDItemKind == "Alias"', '-onlyin', os.path.expanduser('~')],
            capture_output=True, text=True, timeout=30
        )
        alias_paths = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]

        # For each alias, resolve its target using mdls
        for alias_path in alias_paths[:200]:  # limit to first 200 for performance
            try:
                resolve_result = subprocess.run(
                    ['mdls', '-name', 'kMDItemPath', alias_path],
                    capture_output=True, text=True, timeout=5
                )
                # Parse target path from mdls output
                for line in resolve_result.stdout.split('\n'):
                    if 'kMDItemPath' in line and '=' in line:
                        target = line.split('=', 1)[1].strip().strip('"')
                        if target in target_paths:
                            aliases[target] = alias_path
            except (subprocess.TimeoutExpired, OSError):
                continue
    except (subprocess.TimeoutExpired, OSError):
        pass

    return aliases


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("🔍 Loading files...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        files = json.load(f)

    total = len(files)
    print(f"   Found {total} files")

    # --- Phase 1: Detect dev projects (scan directories) ---
    print("\n🔧 Detecting dev projects...")
    project_roots = detect_dev_projects(files)
    for d, (name, reason) in project_roots.items():
        print(f"   Found: {name} ({reason}) at {d}")

    # --- Phase 2: Classify each file ---
    print("\n🏷️  Classifying files...")

    all_paths = set(f.get('path', '') for f in files)

    stats = {
        'system': 0,
        'app_storage': 0,
        'dev_project': 0,
        'icloud_stub': 0,
        'safe': 0,
    }

    for i, file in enumerate(files):
        path = file.get('path', '')

        # Normalize unicode
        path_normalized = unicodedata.normalize('NFC', path)

        # Default values
        file['protection'] = None
        file['protection_reason'] = None
        file['is_icloud_stub'] = False
        file['is_locked_by_process'] = False
        file['locked_by'] = None
        file['atomic_project'] = None
        file['has_alias'] = False
        file['alias_path'] = None

        # Check 1: System/Service
        sys_reason = detect_system(path)
        if sys_reason:
            file['protection'] = 'system'
            file['protection_reason'] = sys_reason
            stats['system'] += 1
            continue

        # Check 2: App Storage
        app_reason = detect_app_storage(path)
        if app_reason:
            file['protection'] = 'app_storage'
            file['protection_reason'] = app_reason
            stats['app_storage'] += 1
            continue

        # Check 3: Dev Project
        for project_dir, (project_name, reason) in project_roots.items():
            if path.startswith(project_dir + '/') or path == project_dir:
                file['protection'] = 'dev_project'
                file['protection_reason'] = reason
                file['atomic_project'] = project_name
                stats['dev_project'] += 1
                break

        if file['protection']:
            continue

        # Check 4: iCloud stub
        if check_icloud_stub(path):
            file['is_icloud_stub'] = True
            stats['icloud_stub'] += 1
            continue

        stats['safe'] += 1

        if (i + 1) % 500 == 0:
            print(f"   Processed {i + 1}/{total}...")

    # --- Phase 3: Check locked files (batch) ---
    print("\n🔴 Checking for locked files (lsof)...")
    safe_paths = set(f['path'] for f in files if not f['protection'] and not f['is_icloud_stub'])
    locked = check_locked_files(safe_paths)
    for path, process in locked.items():
        for f in files:
            if f['path'] == path:
                f['is_locked_by_process'] = True
                f['locked_by'] = process
                break
    print(f"   Found {len(locked)} locked files")

    # --- Phase 4: Find aliases ---
    print("\n🔗 Scanning for Finder Aliases...")
    aliases = find_aliases(all_paths)
    for target, alias_path in aliases.items():
        for f in files:
            if f['path'] == target:
                f['has_alias'] = True
                f['alias_path'] = alias_path
                break
    print(f"   Found {len(aliases)} files with aliases")

    # --- Save ---
    print(f"\n💾 Saving to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(files, f, ensure_ascii=False, indent=2)

    # --- Summary ---
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    print(f"  Total files:              {total}")
    print(f"  🔒 System/Service:         {stats['system']}")
    print(f"  📦 App Storage:            {stats['app_storage']}")
    print(f"  🔧 Dev Projects:           {stats['dev_project']}")
    print(f"  ☁️  iCloud Stubs:           {stats['icloud_stub']}")
    print(f"  🔴 Locked by process:      {len(locked)}")
    print(f"  🔗 Has Finder Alias:       {len(aliases)}")
    print(f"  ✅ Safe to sort:           {stats['safe']}")
    print(f"\n  Protected (excluded from progress): {stats['system'] + stats['app_storage'] + stats['icloud_stub']}")
    print(f"  Dev Projects (move as unit only):    {stats['dev_project']}")
    print("=" * 60)


if __name__ == '__main__':
    main()
