#!/usr/bin/env python3
"""
export.py — Трёхфазный скрипт безопасного перемещения файлов.
Реализует логику экспорта с учётом всех правил защиты.
Поддерживает режим --dry-run для безопасной проверки.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import unicodedata

INPUT_FILE = 'files_to_process.json'
LOG_FILE = 'move_log.json'

def normalize_path(p):
    if not p: return p
    p = os.path.expanduser(p)
    return unicodedata.normalize('NFC', p)

def get_safe_target_path(source_path, target_dir):
    """
    Генерирует безопасное имя файла, если в папке назначения уже есть файл с таким именем.
    Добавляет суффиксы _1, _2 и т.д.
    """
    basename = os.path.basename(source_path)
    name, ext = os.path.splitext(basename)
    
    safe_path = os.path.join(target_dir, basename)
    counter = 1
    
    while os.path.exists(safe_path):
        safe_path = os.path.join(target_dir, f"{name}_{counter}{ext}")
        counter += 1
        
    return safe_path

def main():
    parser = argparse.ArgumentParser(description="Safely export and organize files.")
    parser.add_argument('--dry-run', action='store_true', help='Simulate the export without physically moving files')
    args = parser.parse_args()

    mode_text = "[DRY RUN] Режим симуляции" if args.dry_run else "🚀 РЕАЛЬНОЕ ПЕРЕМЕЩЕНИЕ"
    print("=" * 60)
    print(f"{mode_text}")
    print("=" * 60)

    if not os.path.exists(INPUT_FILE):
        print(f"❌ Файл {INPUT_FILE} не найден!")
        sys.exit(1)

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        files = json.load(f)

    operations = []
    dir_moves_seen = set()

    for f in files:
        # 1. Пропускаем защищённые файлы
        protected = f.get('protection') in ['system', 'app_storage'] or f.get('is_icloud_stub') or f.get('is_locked_by_process')
        if protected:
            continue
            
        current_dest = f.get('current_dest')
        original_dest = f.get('original_dest')
        is_dir_move = f.get('is_dir_move', False)
        reviewed = f.get('reviewed', False)
        
        # 2. Перемещаем, только если файл был обработан (переназначен, помечен как reviewed, или папка)
        if current_dest == 'DELETE' or is_dir_move or current_dest != original_dest or reviewed:
            
            target_dir = current_dest
            if target_dir == 'DELETE':
                target_dir = '~/.Trash'
            elif target_dir == 'To_Review' or target_dir == '~/_Quarantine/To_Review':
                target_dir = '~/_Quarantine/To_Review'
            elif not target_dir or target_dir == 'Custom':
                continue # Пропускаем неполные данные
                
            target_dir = normalize_path(target_dir)
            source_path = normalize_path(f.get('path'))
            
            if not os.path.exists(source_path):
                # Файл уже перемещён или удалён
                continue

            if is_dir_move:
                parent_dir = normalize_path(f.get('parent_dir_to_move'))
                if parent_dir and parent_dir not in dir_moves_seen:
                    if os.path.exists(parent_dir):
                        operations.append({
                            'source': parent_dir,
                            'target_dir': target_dir,
                            'type': 'dir'
                        })
                        dir_moves_seen.add(parent_dir)
            else:
                operations.append({
                    'source': source_path,
                    'target_dir': target_dir,
                    'type': 'file'
                })

    # Очистка коллизий и обработка исключений
    final_operations = []
    for op in operations:
        if op['type'] == 'file':
            is_covered_by_dir = False
            for d_op in operations:
                if d_op['type'] == 'dir' and op['source'].startswith(d_op['source'] + '/'):
                    # Если файл находится внутри перемещаемой папки, мы смотрим на его цель.
                    # Если цель ТА ЖЕ, что у папки — файл перенесётся вместе с папкой, пропускаем.
                    # Если цель ДРУГАЯ — это ИСКЛЮЧЕНИЕ, мы оставляем его в списке на индивидуальный перенос.
                    if op['target_dir'] == d_op['target_dir']:
                        is_covered_by_dir = True
                        break
            if not is_covered_by_dir:
                final_operations.append(op)
        else:
            final_operations.append(op)

    # КРИТИЧЕСКИ ВАЖНО: Сортируем операции по глубине пути (от самых глубоких к верхним).
    # Это гарантирует, что исключения (файлы внутри папок) и вложенные подпапки 
    # будут перемещены ДО того, как переместится их родительская папка.
    final_operations.sort(key=lambda x: len(x['source'].split('/')), reverse=True)

    print(f"📊 Запланировано операций: {len(final_operations)}")

    log_entries = []
    success_count = 0
    error_count = 0

    for op in final_operations:
        source = op['source']
        target_dir = op['target_dir']
        op_type = op['type']

        if not args.dry_run:
            os.makedirs(target_dir, exist_ok=True)
            
        target_path = get_safe_target_path(source, target_dir)
        
        log_entry = {
            'source': source,
            'target': target_path,
            'type': op_type,
            'timestamp': time.time()
        }

        if args.dry_run:
            print(f"   [DRY-RUN] Будет перемещено: {source} -> {target_path}")
            success_count += 1
            continue

        try:
            # Используем /bin/mv для сохранения всех метаданных macOS, resource forks и xattr
            # Флаг -n предотвращает случайную перезапись (хотя мы уже сделали безопасное имя)
            result = subprocess.run(['/bin/mv', '-n', source, target_path], capture_output=True, text=True)
            if result.returncode == 0:
                log_entry['status'] = 'success'
                success_count += 1
                print(f"✅ Перемещено: {os.path.basename(source)} -> {target_path}")
            else:
                log_entry['status'] = 'error'
                log_entry['error'] = result.stderr.strip()
                error_count += 1
                print(f"❌ Ошибка перемещения {source}: {result.stderr.strip()}")
        except Exception as e:
            log_entry['status'] = 'error'
            log_entry['error'] = str(e)
            error_count += 1
            print(f"❌ Критическая ошибка {source}: {str(e)}")
            
        log_entries.append(log_entry)

    if not args.dry_run and len(log_entries) > 0:
        existing_logs = []
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, 'r', encoding='utf-8') as lf:
                    existing_logs = json.load(lf)
            except json.JSONDecodeError:
                pass
                
        existing_logs.extend(log_entries)
        
        with open(LOG_FILE, 'w', encoding='utf-8') as lf:
            json.dump(existing_logs, lf, ensure_ascii=False, indent=2)
            
        print(f"\n💾 Лог перемещений сохранён в {LOG_FILE}")

    print("\n" + "=" * 60)
    print(f"🎯 ЭКСПОРТ ЗАВЕРШЁН {'[РЕЖИМ DRY RUN]' if args.dry_run else ''}")
    print("=" * 60)
    print(f"   Успешно: {success_count}")
    if error_count > 0:
        print(f"   Ошибок:  {error_count}")
    print("=" * 60)

if __name__ == '__main__':
    main()
