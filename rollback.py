#!/usr/bin/env python3
"""
rollback.py — Скрипт отмены перемещения файлов.
Читает move_log.json с конца и восстанавливает файлы на их оригинальные места.
Использует /bin/mv для сохранения метаданных.
"""

import json
import os
import subprocess
import sys

LOG_FILE = 'move_log.json'

def main():
    print("=" * 60)
    print("⏪ ОТМЕНА ЭКСПОРТА (ROLLBACK)")
    print("=" * 60)

    if not os.path.exists(LOG_FILE):
        print(f"❌ Файл логов {LOG_FILE} не найден. Отменять нечего.")
        sys.exit(1)

    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            logs = json.load(f)
    except json.JSONDecodeError:
        print(f"❌ Файл логов {LOG_FILE} повреждён.")
        sys.exit(1)

    if not logs:
        print("ℹ️ Лог пуст. Отменять нечего.")
        sys.exit(0)

    # Обрабатываем с конца в начало, чтобы корректно отменить цепочку перемещений
    logs.reverse()

    success_count = 0
    error_count = 0

    print(f"Обнаружено {len(logs)} записей в логе. Начинаю восстановление...\n")

    for entry in logs:
        if entry.get('status') != 'success':
            continue

        original_source = entry['source']
        current_target = entry['target']
        op_type = entry.get('type', 'file')

        if not os.path.exists(current_target):
            print(f"⚠️ Пропущен: {current_target} (файл/папка больше не существует)")
            error_count += 1
            continue

        # Создаём структуру оригинальных папок, если она была удалена
        original_dir = os.path.dirname(original_source)
        if original_dir:
            os.makedirs(original_dir, exist_ok=True)

        try:
            # Возвращаем файл назад с помощью mv -n (не перезаписываем, если там уже что-то появилось)
            result = subprocess.run(['/bin/mv', '-n', current_target, original_source], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ Восстановлено: {os.path.basename(original_source)}")
                success_count += 1
            else:
                print(f"❌ Ошибка восстановления {current_target}: {result.stderr.strip()}")
                error_count += 1
        except Exception as e:
            print(f"❌ Исключение при восстановлении {current_target}: {str(e)}")
            error_count += 1

    print("\n" + "=" * 60)
    print("🎯 ОТКАТ ЗАВЕРШЁН")
    print("=" * 60)
    print(f"   Успешно восстановлено: {success_count}")
    if error_count > 0:
        print(f"   Ошибок:                {error_count}")
    print("=" * 60)
    
    # После успешного отката лог можно переименовать, чтобы не откатывать дважды
    if success_count > 0:
        backup_log = f"{LOG_FILE}.bak"
        os.rename(LOG_FILE, backup_log)
        print(f"ℹ️ Файл логов переименован в {backup_log} для предотвращения повторного отката.")

if __name__ == '__main__':
    main()
