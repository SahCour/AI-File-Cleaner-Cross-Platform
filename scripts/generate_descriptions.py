import os
import json
import urllib.request
import urllib.error
import time

def load_env():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k] = v

load_env()
BASE_URL = os.environ.get("OMNI_BASE_URL", "http://127.0.0.1:20128/v1")
API_KEY = os.environ.get("OMNI_API_KEY", "")
MODEL = os.environ.get("OMNI_MODEL", "flash-everyday")

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
    
    # Optional: we can force JSON via open router if supported, but prompt engineering is usually enough for simple tasks
    if "openrouter" in BASE_URL or "omni" in BASE_URL:
        # Some compatible gateways accept response_format
        try:
            data["response_format"] = {"type": "json_object"}
        except:
            pass

    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(data).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            raw_data = response.read().decode("utf-8")
            if raw_data.strip().startswith("data:"):
                # Parse SSE stream
                full_content = ""
                for line in raw_data.split("\n"):
                    line = line.strip()
                    if line.startswith("data:") and line != "data: [DONE]":
                        try:
                            chunk = json.loads(line[5:].strip())
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta:
                                full_content += delta["content"]
                        except json.JSONDecodeError:
                            pass
                content = full_content
            else:
                try:
                    result = json.loads(raw_data)
                    content = result["choices"][0]["message"]["content"]
                except json.JSONDecodeError:
                    print(f"API Error: Server returned 200 OK but invalid JSON. Raw body: '{raw_data[:200]}'")
                    return {"description": "Неизвестный файл", "suggested_folder": "~/_Quarantine"}
            # Clean up markdown code blocks if the model wrapped the JSON
            if content.startswith("```json"):
                content = content.replace("```json\\n", "").replace("```json\n", "").replace("```", "")
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                print(f"Model returned invalid JSON (or empty string): '{content}'")
                return {"description": "Неизвестный файл", "suggested_folder": "~/_Quarantine"}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='ignore')
        print(f"API HTTP Error on {filename}: {e.code} {e.reason} - {error_body}")
        return {"description": "Неизвестный файл", "suggested_folder": "~/_Quarantine"}
    except Exception as e:
        print(f"API Error on {filename}: {e}")
        return {"description": "Неизвестный файл", "suggested_folder": "~/_Quarantine"}

def main():
    base_dir = os.path.join(os.path.dirname(__file__), "..")
    files_json = os.path.join(base_dir, "files_to_process.json")
    dests_json = os.path.join(base_dir, "destinations.json")
    
    if not os.path.exists(files_json):
        print("files_to_process.json not found. Run scan_files.py first.")
        return
        
    with open(files_json, "r") as f:
        files = json.load(f)
        
    with open(dests_json, "r") as f:
        dests = json.load(f)
        
    # Flatten destinations for the prompt
    flat_dests = []
    for category, paths in dests.items():
        flat_dests.extend(paths)
    dest_str = "\n".join(f"- {p}" for p in flat_dests)
    
    print(f"Processing {len(files)} files via OmniRoute with model '{MODEL}'...")
    
    processed = 0
    for i, file_obj in enumerate(files):
        if file_obj.get("description") and file_obj.get("suggested_folder"):
            continue # already processed
            
        print(f"[{i+1}/{len(files)}] AI analyzing: {file_obj['filename']}")
        res = call_llm(file_obj['filename'], file_obj['extension'], file_obj['size_bytes'], dest_str)
        
        file_obj["description"] = res.get("description", "")
        file_obj["suggested_folder"] = res.get("suggested_folder", "")
        processed += 1
        
        # Save periodically
        if processed % 5 == 0:
            with open(files_json, "w", encoding="utf-8") as f:
                json.dump(files, f, ensure_ascii=False, indent=2)
                
        time.sleep(0.5)
        
    # Final save
    with open(files_json, "w", encoding="utf-8") as f:
        json.dump(files, f, ensure_ascii=False, indent=2)
        
    print("Done generating descriptions!")

if __name__ == "__main__":
    main()
