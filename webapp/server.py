#!/usr/bin/env python3
import http.server
import socketserver
import urllib.parse
import subprocess
import os

PORT = 8002
DIRECTORY = ".."

# Cache of allowed paths for /api/open (rebuilt when files_to_process.json changes)
_ALLOWED_CACHE = {}

def _allowed_paths():
    list_path = os.path.join(DIRECTORY, 'files_to_process.json')
    mtime = os.path.getmtime(list_path) if os.path.exists(list_path) else None
    cached = _ALLOWED_CACHE.get('data')
    if cached is not None and _ALLOWED_CACHE.get('mtime') == mtime:
        return cached
    allowed = set()
    if mtime is not None:
        try:
            with open(list_path, 'r', encoding='utf-8') as f:
                import json
                for item in json.load(f):
                    if item.get('path'):
                        allowed.add(item['path'])
        except (OSError, ValueError):
            allowed = set()
    _ALLOWED_CACHE['data'] = allowed
    _ALLOWED_CACHE['mtime'] = mtime
    return allowed

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == '/':
            self.send_response(301)
            self.send_header('Location', '/webapp/')
            self.end_headers()
            return
            
        if parsed.path == '/api/choose_folder':
            import subprocess
            import platform
            try:
                sys_name = platform.system()
                folder_path = None
                
                if sys_name == 'Darwin':
                    # Use AppleScript to show native folder picker attached to frontmost app (browser)
                    script = 'tell application (path to frontmost application as text)\nactivate\nreturn POSIX path of (choose folder with prompt "Select base folder for sorting:")\nend tell'
                    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
                    if result.returncode == 0:
                        folder_path = result.stdout.strip()
                elif sys_name == 'Windows':
                    import tkinter as tk
                    from tkinter import filedialog
                    root = tk.Tk()
                    root.withdraw()
                    root.attributes('-topmost', True)
                    res = filedialog.askdirectory(title="Select base folder for sorting")
                    if res:
                        folder_path = res
                    root.destroy()
                else:
                    # Linux (try zenity)
                    try:
                        result = subprocess.run(['zenity', '--file-selection', '--directory', '--title=Select base folder for sorting'], capture_output=True, text=True)
                        if result.returncode == 0:
                            folder_path = result.stdout.strip()
                    except:
                        pass # Could add tkinter fallback here for linux
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                
                import json
                if folder_path:
                    self.wfile.write(json.dumps({"path": folder_path}).encode('utf-8'))
                else:
                    self.wfile.write(json.dumps({"error": "canceled"}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f'{{"error": "{str(e)}" }}'.encode())
            return

        if parsed.path == '/api/get_destinations':
            dest_path = os.path.join(DIRECTORY, 'destinations.json')
            try:
                with open(dest_path, 'r', encoding='utf-8') as f:
                    data = f.read()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.end_headers()
                self.wfile.write(data.encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f'{{"error": "{str(e)}" }}'.encode())
            return
            
        if parsed.path == '/api/open':
            query = urllib.parse.parse_qs(parsed.query)
            if 'path' in query:
                file_path = query['path'][0]
                import platform
                import subprocess
                import os
                try:
                    # Whitelist: only allow paths listed in files_to_process.json
                    if file_path not in _allowed_paths():
                        self.send_response(403)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(b'{"error": "forbidden"}')
                        return

                    sys_name = platform.system()
                    if sys_name == 'Darwin':
                        subprocess.run(['open', file_path])
                    elif sys_name == 'Windows':
                        os.startfile(file_path)
                    else:
                        subprocess.run(['xdg-open', file_path])
                        
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(b'{"status": "ok"}')
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(f'{{"error": "{str(e)}" }}'.encode())
            else:
                self.send_response(400)
                self.end_headers()
            return
        
        # Default behavior for static files
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/api/save_destinations':
            # CSRF guard: only allow requests from the local browser page
            host = self.headers.get('Host', '')
            if not (host.startswith('localhost:') or host.startswith('127.0.0.1:')):
                self.send_response(403)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"error": "forbidden"}')
                return

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            dest_path = os.path.join(DIRECTORY, 'destinations.json')
            try:
                import json
                data = json.loads(post_data.decode('utf-8'))
                with open(dest_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status": "ok"}')
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f'{{"error": "{str(e)}" }}'.encode())
            return
            
        self.send_response(404)
        self.end_headers()

if __name__ == '__main__':
    while True:
        try:
            with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
                print(f"==================================================")
                print(f"🚀 AI File Cleaner Native Server running!")
                print(f"👉 Open in your browser: http://localhost:{PORT}")
                print(f"==================================================")
                print("Press Ctrl+C to stop.")
                try:
                    httpd.serve_forever()
                except KeyboardInterrupt:
                    print("\nShutting down server...")
                    httpd.server_close()
                break
        except OSError as e:
            if e.errno == 48: # Address already in use
                PORT += 1
            else:
                raise
