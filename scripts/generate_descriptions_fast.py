import os
import json
import urllib.request
import urllib.error
import time
import concurrent.futures
import threading

def load_env():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k] = v

load_env()
BASE_URL = os.environ.get("OMNI_BASE_URL", "http://127.0.0.1:20128/v1")
API_KEY = os.environ.get("OMNI_API_KEY", "")
MODEL = os.environ.get("OMNI_MODEL", "flash-everyday")

# Lock for safe JSON saving
file_lock = threading.Lock()
processed_count = 0
total_to_process = 0

def call_llm(filename, ext, size, destinations_summary):
    prompt = f"""You are an AI file organizer.
File: {filename}
Extension: {ext}
Size: {size} bytes

Available folders:
{destinations_summary}

Task:
1. Provide a short description (max 5 words, in Russian) of what this file likely is based on the filename.
2. Pick the BEST matching folder path from the available folders. If unsure, pick '~/_Quarantine'.

Output strictly in valid JSON format:
{{
  "description": "...",
  "suggested_folder": "..."
}}
"""
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    
    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "stream": False
    }
    
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(data).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw_data = response.read().decode("utf-8")
            if raw_data.strip().startswith("data:"):
                full_content = ""
                for line in raw_data.split("\n"):
                    line = line.strip()
                    if line.startswith("data:") and line != "data: [DONE]":
                        try:
                            chunk = json.loads(line[5:].strip())
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta:
                                full_content += delta["content"]
                        except:
                            pass
                content = full_content
            else:
                try:
                    result = json.loads(raw_data)
                    content = result["choices"][0]["message"]["content"]
                except json.JSONDecodeError:
                    return {"description": "Ошибка парсинга", "suggested_folder": "~/_Quarantine"}
                    
            if content.startswith("```json"):
                content = content.replace("```json\\n", "").replace("```json\n", "").replace("```", "")
            try:
                return json.loads(content)
            except:
                return {"description": "Сложный формат", "suggested_folder": "~/_Quarantine"}
    except Exception as e:
        return {"description": "Ошибка сети", "suggested_folder": "~/_Quarantine"}

def process_file(file_obj, dest_str, files_json, files_list):
    global processed_count
    
    # Skip already processed (or currently processing)
    if file_obj.get("description") and file_obj.get("suggested_folder") and file_obj["description"] not in ["Ошибка сети", "Ошибка парсинга"]:
        return
        
    res = call_llm(file_obj['filename'], file_obj['extension'], file_obj['size_bytes'], dest_str)
    
    file_obj["description"] = res.get("description", "Неизвестно")
    file_obj["suggested_folder"] = res.get("suggested_folder", "~/_Quarantine")
    
    with file_lock:
        processed_count += 1
        print(f"[{processed_count}/{total_to_process}] AI: {file_obj['filename']}")
        # Save every 10 files
        if processed_count % 10 == 0:
            with open(files_json, "w", encoding="utf-8") as f:
                json.dump(files_list, f, ensure_ascii=False, indent=2)

def main():
    global total_to_process
    base_dir = os.path.join(os.path.dirname(__file__), "..")
    files_json = os.path.join(base_dir, "files_to_process.json")
    dests_json = os.path.join(base_dir, "destinations.json")
    
    if not os.path.exists(files_json):
        print("files_to_process.json not found.")
        return
        
    with open(files_json, "r") as f:
        files = json.load(f)
        
    with open(dests_json, "r") as f:
        dests = json.load(f)
        
    flat_dests = []
    for category, paths in dests.items():
        flat_dests.extend(paths)
    dest_str = "\n".join(f"- {p}" for p in flat_dests)
    
    needs_processing = [f for f in files if not f.get("description") or f["description"] in ["Ошибка сети", "Ошибка парсинга", ""]]
    total_to_process = len(needs_processing)
    
    if total_to_process == 0:
        print("All files already processed!")
        return
        
    print(f"Starting FAST multi-threaded processing for {total_to_process} files (10 parallel requests)...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_file, f, dest_str, files_json, files) for f in needs_processing]
        concurrent.futures.wait(futures)
        
    with open(files_json, "w", encoding="utf-8") as f:
        json.dump(files, f, ensure_ascii=False, indent=2)
        
    print("Done generating descriptions!")

if __name__ == "__main__":
    main()
