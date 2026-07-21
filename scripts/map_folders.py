import os
import json

SYSTEM_DIRS = {
    '/System', '/Library', '/Applications', '/usr', '/bin', 
    '/sbin', '/var', '/private', '/Volumes', '/dev', '/net', '/cores', '/opt',
    os.path.expanduser('~/Library')
}

def is_system_or_hidden(path):
    basename = os.path.basename(path)
    if basename.startswith('.') and basename != '.':
        return True
    
    clean_path = path.rstrip('/')
    if not clean_path:
        clean_path = '/'
        
    if clean_path in SYSTEM_DIRS:
        return True
        
    return False

def get_dir_tree(root_path):
    try:
        if not os.path.isdir(root_path) or os.path.islink(root_path):
            return None
    except PermissionError:
        return None
        
    tree = {
        'name': os.path.basename(root_path) or root_path,
        'path': root_path,
        'type': 'directory',
        'children': [],
        'flags': []
    }
    
    # If it's a known system or hidden dir, mark it and DO NOT recurse
    if is_system_or_hidden(root_path):
        tree['flags'].append('SYSTEM/HIDDEN')
        return tree
        
    try:
        entries = os.listdir(root_path)
    except (PermissionError, OSError):
        tree['flags'].append('NO_ACCESS')
        return tree
        
    for entry in entries:
        full_path = os.path.join(root_path, entry)
        if os.path.isdir(full_path) and not os.path.islink(full_path):
            child_tree = get_dir_tree(full_path)
            if child_tree:
                tree['children'].append(child_tree)
                
    return tree

def print_tree_markdown(tree, indent=0):
    lines = []
    prefix = "  " * indent + "- "
    
    display_name = tree['name']
    if tree.get('flags'):
        display_name += f" `[{', '.join(tree['flags'])}]`"
        
    lines.append(f"{prefix}**{display_name}**")
    
    # Sort children alphabetically, but put those with flags at the bottom
    def sort_key(x):
        has_flags = 1 if x.get('flags') else 0
        return (has_flags, x['name'].lower())
        
    sorted_children = sorted(tree['children'], key=sort_key)
    for child in sorted_children:
        lines.extend(print_tree_markdown(child, indent + 1))
    return lines

def main():
    home = os.path.expanduser('~')
    
    # We scan the root (which will cover ~) and explicitly iCloud (since ~/Library is skipped)
    icloud_path = os.path.join(home, 'Library', 'Mobile Documents', 'com~apple~CloudDocs')
    
    targets = ['/']
    
    full_tree = []
    
    for target in targets:
        if os.path.exists(target):
            tree = get_dir_tree(target)
            if tree:
                if target == '/':
                    tree['name'] = '/'
                full_tree.append(tree)
                
    # Also grab iCloud if it exists
    if os.path.exists(icloud_path):
        icloud_tree = get_dir_tree(icloud_path)
        if icloud_tree:
            icloud_tree['name'] = 'iCloud Drive'
            # Remove SYSTEM/HIDDEN flag from iCloud root if it got one
            if 'SYSTEM/HIDDEN' in icloud_tree['flags']:
                icloud_tree['flags'].remove('SYSTEM/HIDDEN')
            full_tree.append(icloud_tree)
                
    # Save to JSON
    output_dir = os.path.join(os.path.dirname(__file__), '..')
    output_path = os.path.abspath(os.path.join(output_dir, 'folder_tree.json'))
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(full_tree, f, indent=2, ensure_ascii=False)
        
    # Generate Markdown Artifact in brain
    md_lines = [
        "# Дерево папок", 
        "", 
        "Пожалуйста, посмотрите на директории и назовите в чате те, которые вы хотите сделать 'Целевыми' (Destination Folders).",
        "Системные и скрытые папки помечены `[SYSTEM/HIDDEN]` и их содержимое проигнорировано.",
        ""
    ]
    for tree in full_tree:
        md_lines.extend(print_tree_markdown(tree))
        md_lines.append("")
        
    md_output_path = os.path.abspath(os.path.join(output_dir, 'folder_tree.md'))
    with open(md_output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(md_lines))
        
    print(f"Folder tree saved to {output_path}")
    print(f"Markdown tree saved to {md_output_path}")

if __name__ == '__main__':
    main()
