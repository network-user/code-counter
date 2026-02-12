"""
Code Counter - библиотека для подсчета строк кода в проекте.
Учитывает .gitignore и позволяет анализировать вклад разработчиков.

"""
from pathlib import Path
from typing import Iterator
from collections import defaultdict
import subprocess
import re
import argparse


__version__ = "0.1.0"
__all__ = ["CodeCounter", "GitIgnoreParser", "analyze_project"]


class GitIgnoreParser:
    def __init__(self, gitignore_path: Path | None = None):
        self.patterns: list[str] = []
        if gitignore_path and gitignore_path.exists():
            self._parse_gitignore(gitignore_path)

    def _parse_gitignore(self, path: Path) -> None:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    self.patterns.append(line)

    def should_ignore(self, path: Path, project_root: Path) -> bool:
        relative_path = path.relative_to(project_root)
        path_str = str(relative_path)

        if '.git' in path.parts:
            return True

        for pattern in self.patterns:
            if pattern.endswith('/'):
                if path_str.startswith(pattern.rstrip('/')):
                    return True
            elif '*' in pattern:
                regex_pattern = pattern.replace('.', r'\.').replace('*', '.*')
                if re.search(regex_pattern, path_str):
                    return True
            else:
                if pattern in path_str or path_str.endswith(pattern):
                    return True

        return False


class CodeCounter:

    def __init__(self, project_path: str | Path):
        self.project_path = Path(project_path).resolve()
        self.gitignore_parser = GitIgnoreParser(
            self.project_path / '.gitignore'
        )

        self.code_extensions = {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp',
            '.h', '.hpp', '.cs', '.go', '.rs', '.rb', '.php', '.swift',
            '.kt', '.scala', '.sql', '.html', '.css', '.scss', '.vue',
            '.yaml', '.yml', '.json', '.xml', '.sh', '.bash', '.r',
            '.m', '.mm', '.dart', '.lua', '.pl', '.R'
        }

    def _is_code_file(self, path: Path) -> bool:
        return path.suffix.lower() in self.code_extensions

    def _count_lines_in_file(self, path: Path) -> int:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return sum(1 for _ in f)
        except (UnicodeDecodeError, PermissionError):
            return 0

    def get_code_files(self) -> Iterator[Path]:
        for path in self.project_path.rglob('*'):
            if not path.is_file():
                continue

            if self.gitignore_parser.should_ignore(path, self.project_path):
                continue

            if self._is_code_file(path):
                yield path

    def count_total_lines(self) -> dict[str, int]:
        stats: dict[str, int] = defaultdict(int)
        total = 0

        for file_path in self.get_code_files():
            lines = self._count_lines_in_file(file_path)
            extension = file_path.suffix or 'no_ext'
            stats[extension] += lines
            total += lines

        stats['TOTAL'] = total
        return dict(stats)

    def count_by_author(self) -> dict[str, int]:
        if not (self.project_path / '.git').exists():
            raise ValueError("Проект не является git-репозиторием")

        author_stats: dict[str, int] = defaultdict(int)

        for file_path in self.get_code_files():
            try:
                relative_path = file_path.relative_to(self.project_path)

                result = subprocess.run(
                    ['git', 'blame', '--line-porcelain', str(relative_path)],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode != 0:
                    continue

                for line in result.stdout.split('\n'):
                    if line.startswith('author '):
                        author = line[7:]
                        author_stats[author] += 1

            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                continue

        return dict(sorted(author_stats.items(), key=lambda x: x[1], reverse=True))

    def get_stats_by_file(self) -> dict[str, int]:
        file_stats = {}
        for file_path in self.get_code_files():
            lines = self._count_lines_in_file(file_path)
            relative_path = str(file_path.relative_to(self.project_path))
            file_stats[relative_path] = lines

        return dict(sorted(file_stats.items(), key=lambda x: x[1], reverse=True))


def analyze_project(project_path: str | Path, show_files: bool = False) -> None:
    counter = CodeCounter(project_path)

    print(f"\n Анализ проекта: {counter.project_path}\n")

    print("=" * 50)
    print("Общая статистика по типам файлов:")
    print("=" * 50)

    total_stats = counter.count_total_lines()
    total_lines = total_stats.pop('TOTAL', 0)

    for ext, lines in sorted(total_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {ext:15s}: {lines:>8,} строк")

    print("-" * 50)
    print(f"  {'ИТОГО':15s}: {total_lines:>8,} строк")
    print("=" * 50)

    try:
        print("\n" + "=" * 50)
        print("Вклад разработчиков:")
        print("=" * 50)

        author_stats = counter.count_by_author()

        if author_stats:
            max_name_len = max(len(name) for name in author_stats.keys())

            for author, lines in author_stats.items():
                percentage = (lines / total_lines * 100) if total_lines > 0 else 0
                print(f"  {author:{max_name_len}s}: {lines:>8,} строк ({percentage:>5.1f}%)")
        else:
            print("  Не удалось получить статистику по авторам")

        print("=" * 50)

    except ValueError as e:
        print(f"\n⚠️  {e}")
    except Exception as e:
        print(f"\n⚠️  Ошибка при анализе авторства: {e}")

    # Статистика по файлам
    if show_files:
        print("\n" + "=" * 50)
        print("Топ-10 самых больших файлов:")
        print("=" * 50)

        file_stats = counter.get_stats_by_file()
        for i, (file_path, lines) in enumerate(list(file_stats.items())[:10], 1):
            print(f"  {i:2d}. {file_path:40s} {lines:>6,} строк")

        print("=" * 50)


def main() -> None:
    """CLI интерфейс."""
    parser = argparse.ArgumentParser(
        description='Подсчет строк кода в проекте с учетом .gitignore'
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Путь до проекта (по умолчанию: текущая директория)'
    )
    parser.add_argument(
        '-f', '--files',
        action='store_true',
        help='Показать топ-10 самых больших файлов'
    )
    parser.add_argument(
        '-v', '--version',
        action='version',
        version=f'code-counter {__version__}'
    )

    args = parser.parse_args()

    try:
        analyze_project(args.path, show_files=args.files)
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        exit(1)


if __name__ == '__main__':
    main()
