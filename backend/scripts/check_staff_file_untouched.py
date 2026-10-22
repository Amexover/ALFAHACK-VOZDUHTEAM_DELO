"""Проверка контракта «в файле ручек сотрудника правим только сигнатуры».

Сравнивает app/api/staff.py с версией из ветки main на уровне разобранного кода:
тело каждой функции должно совпадать дословно, отличаться могут только объявления
аргументов. Однострочные правки сигнатур git мержит без конфликта, правки тела — нет,
поэтому эта проверка и записывается в приёмку.

Запуск:  python scripts/check_staff_file_untouched.py [base_ref]
"""

import ast
import pathlib
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
TARGET = "backend/app/api/staff.py"


def functions(source: str) -> dict[str, ast.FunctionDef]:
    return {node.name: node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef)}


def body_fingerprint(node: ast.FunctionDef) -> str:
    return "\n".join(ast.dump(stmt, indent=1) for stmt in node.body)


def signature(node: ast.FunctionDef) -> str:
    return ast.unparse(node.args)


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "main"
    old = subprocess.run(["git", "show", f"{base}:{TARGET}"], cwd=REPO, capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    new = (REPO / TARGET).read_text(encoding="utf-8")

    old_fn, new_fn = functions(old), functions(new)
    print(f"файл: {TARGET}")
    print(f"ветка сравнения: {base}")
    print(f"функций было: {len(old_fn)}, стало: {len(new_fn)}")

    problems: list[str] = []
    if set(old_fn) != set(new_fn):
        problems.append(f"изменился состав функций: {sorted(set(new_fn) ^ set(old_fn))}")

    changed_signatures = []
    for name in sorted(set(old_fn) & set(new_fn)):
        if body_fingerprint(old_fn[name]) != body_fingerprint(new_fn[name]):
            problems.append(f"изменено тело функции {name}")
        if signature(old_fn[name]) != signature(new_fn[name]):
            changed_signatures.append(name)

    print(f"тела функций изменены: {'да' if any(p.startswith('изменено тело') for p in problems) else 'нет'}")
    print(f"сигнатуры изменены ({len(changed_signatures)}): {', '.join(changed_signatures) or '—'}")
    for name in changed_signatures:
        print(f"  {name}:")
        print(f"    было:  {signature(old_fn[name])}")
        print(f"    стало: {signature(new_fn[name])}")

    diff = subprocess.run(["git", "diff", "--numstat", base, "--", TARGET], cwd=REPO,
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()
    print(f"git diff --numstat: {diff or 'без изменений'}")

    if problems:
        print("\nПРОВЕРКА НЕ ПРОЙДЕНА:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nПРОВЕРКА ПРОЙДЕНА: тела функций не изменены, правки только в сигнатурах.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
