import os
import json
import shutil
from datetime import datetime

def main():
    base_dir = os.path.join(os.path.dirname(__file__), "..")
    export_json = os.path.join(base_dir, "export_tasks.json")
    
    if not os.path.exists(export_json):
        # We can also check Downloads since the browser might have saved it there
        downloads_export = os.path.expanduser("~/Downloads/export_tasks.json")
        if os.path.exists(downloads_export):
            export_json = downloads_export
        else:
            print("export_tasks.json not found! Please export it from the Web App first.")
            return

    with open(export_json, "r") as f:
        tasks = json.load(f)
        
    print(f"Loaded {len(tasks)} tasks from {export_json}")
    
    quarantine_base = os.path.expanduser("~/_Quarantine")
    quarantine_deleted = os.path.join(quarantine_base, "Deleted_Files")
    
    success_count = 0
    error_count = 0
    
    for task in tasks:
        src = os.path.abspath(task["path"])
        dest_folder = task["destination"]
        
        if not os.path.exists(src):
            print(f"[SKIP] File not found: {src}")
            error_count += 1
            continue
            
        filename = os.path.basename(src)
        
        if dest_folder == "DELETE":
            # Move to Quarantine instead of rm
            target_dir = quarantine_deleted
        else:
            target_dir = os.path.expanduser(dest_folder)
            
        # Ensure target dir exists
        try:
            os.makedirs(target_dir, exist_ok=True)
        except OSError as e:
            print(f"[ERROR] Failed to create folder {target_dir}: {e}")
            error_count += 1
            continue
            
        is_dir_move = task.get("type") == "DIR_MOVE"
        
        if is_dir_move:
            dest_path = os.path.join(target_dir, os.path.basename(src))
            
            if os.path.exists(dest_path):
                print(f"[ERROR] Directory already exists at {dest_path}. Skipping to prevent nesting/overwrite.")
                error_count += 1
                continue
                
            try:
                shutil.move(src, dest_path)
                print(f"[MOVED ENTIRE FOLDER] {os.path.basename(src)} TO {dest_folder}")
                success_count += 1
            except Exception as e:
                print(f"[ERROR] Failed to move folder {os.path.basename(src)}: {e}")
                error_count += 1
        else:
            dest_path = os.path.join(target_dir, filename)
            
            # Handle naming collisions
            if os.path.exists(dest_path):
                name, ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime("%Y%md%H%M%S")
                dest_path = os.path.join(target_dir, f"{name}_{timestamp}{ext}")
                
            try:
                shutil.move(src, dest_path)
                action_text = "MOVED TO QUARANTINE" if dest_folder == "DELETE" else f"MOVED TO {dest_folder}"
                print(f"[{action_text}] {filename}")
                success_count += 1
            except Exception as e:
                print(f"[ERROR] Failed to move {filename}: {e}")
                error_count += 1
            
    print("\n--- Execution Complete ---")
    print(f"Successfully processed: {success_count}")
    print(f"Errors: {error_count}")
    
    # Optionally rename the export file so we don't run it twice
    if success_count > 0:
        done_path = export_json + ".done"
        shutil.move(export_json, done_path)
        print(f"Export file renamed to {os.path.basename(done_path)}")

if __name__ == "__main__":
    main()
