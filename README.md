# AI File Cleaner (Cross-Platform)

A ridiculously powerful, AI-driven tool for organizing thousands of messy files on macOS, Windows, and Linux.

Unlike typical rule-based cleaners that rely on extensions or basic rules, **AI File Cleaner** uses Large Language Models (LLMs) to semantically analyze the actual content, context, and purpose of every single file, and suggests the perfect destination folder for it.

It comes with a beautiful, lightning-fast two-stage web dashboard for manual review, ensuring you remain in absolute control of your data.

## 🎯 Why AI File Cleaner? (Core USPs)

- **Two-Stage Web Dashboard (Unique):** Unlike any other tool on the market, we offer a two-stage review process. 
  - **Stage 1 (By Source):** Review the AI's initial sorting predictions grouped by their original locations.
  - **Stage 2 (By Destination):** Review the final target folders before a single byte is moved. Absolute control.
- **Quarantine System:** Files marked as "Delete" are **never** wiped. They are safely moved to a dedicated `_Quarantine` folder for your manual inspection. Safety is our philosophy.
- **Lightning Fast Web UI:** Effortlessly handles 5000+ files instantly in the browser without lag. No heavy desktop clients needed for the review process.
- **Semantic AI Sorting:** Groups invoices with invoices, designs with designs, and projects with projects based on semantic meaning of the file's content, not just simple file extensions.
- **Local Execution:** Your files are processed securely. The dashboard runs locally on your machine.

## 🛠 Prerequisites

- macOS, Windows, or Linux
- Python 3.9+
- A modern browser (Safari, Chrome, Arc)

## 📦 Installation & Usage

### 1. Initial Scan
Run the scanner to index your cluttered folders (e.g., `~/Downloads`, `~/Desktop`, `~/Documents`).
```bash
python3 scripts/scan_files.py
```
*Note: This will generate `files_to_process.json`.*

### 2. Launch the Dashboard
Start the local server to review the AI's sorting plan.
```bash
python3 webapp/server.py
```
Open your browser and navigate to `http://localhost:8000`.

### 3. Review & Sort
- Use the web interface to quickly review the AI's predictions.
- Tag files, create custom destination paths on the fly, or move entire folders.
- Use the **Search Bar** to instantly find any file across your entire system.
- Click **Export** when you are satisfied with the sorting. This will download an `export_tasks.json` file to your Downloads folder.

### 4. Execute the Cleanup
Finally, let the script safely move the files to their new homes.
```bash
python3 scripts/executor.py
```

## 🔒 Privacy & Safety
- **No unapproved moves:** The script only moves files you explicitly approve via the Export button.
- **Collision handling:** If a file with the same name exists in the destination, the tool automatically adds a suffix (`_1`, `_2`) to prevent overwriting.

## 🗺 Roadmap
- [ ] Packaging into a native `.dmg` app (Tauri / Electron).
- [ ] Built-in file tree browser for easier custom folder selection.
- [ ] Integration with local LLMs (Ollama) for 100% offline, private scanning.

---
*Built to bring order to the chaos.*
