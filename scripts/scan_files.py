import os
import json

# Common clutter directories
TARGET_DIRS = [
    os.path.expanduser("~/Downloads"),
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Documents")
]

# Dirs to skip during recursion
SKIP_DIRS = {
    "node_modules", "venv", ".venv", "env",
    ".git", ".idea", ".vscode", "build", "dist"
}

def is_skipped_dir(dir_name):
    return dir_name in SKIP_DIRS or dir_name.startswith('.')

def scan_directory(start_path):
    if not os.path.exists(start_path):
        return []
        
    files_list = []
    
    for root, dirs, files in os.walk(start_path):
        # Modify dirs in-place to skip unwanted directories
        dirs[:] = [d for d in dirs if not is_skipped_dir(d)]
            
        for file in files:
            # Skip hidden files
            if file.startswith('.'):
                continue
                
            file_path = os.path.join(root, file)
            
            # Skip symlinks for safety
            if os.path.islink(file_path):
                continue
                
            try:
                stat = os.stat(file_path)
                files_list.append({
                    "id": str(len(files_list) + 1),
                    "filename": file,
                    "path": file_path.replace('\\', '/'),
                    "size_bytes": stat.st_size,
                    "modified_at": stat.st_mtime,
                    "extension": os.path.splitext(file)[1].lower(),
                    "description": "", # Will be filled by AI
                    "suggested_folder": "" # Will be filled by AI
                })
            except (PermissionError, OSError):
                pass
                
    return files_list

def main():
    all_files = []
    print("Starting file scan...")
    
    for d in TARGET_DIRS:
        print(f"Scanning {d}...")
        files = scan_directory(d)
        all_files.extend(files)
        
    # Reassign IDs just in case
    for idx, f in enumerate(all_files):
        f["id"] = str(idx + 1)
        
    print(f"Total files found to process: {len(all_files)}")
    
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "files_to_process.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_files, f, ensure_ascii=False, indent=2)
        
    print(f"File list saved to {os.path.abspath(out_path)}")

if __name__ == "__main__":
    main()
