# .count

<p>
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-555?style=flat" alt="Platform" />
  <img src="https://img.shields.io/badge/Category-CLI%20%26%20Library-orange?style=flat" alt="Category" />
  <!-- loc:start --><img src="https://img.shields.io/badge/lines_of_code-796-lightgrey?style=flat" alt="796 lines of code" /><!-- loc:end -->
</p>

<img src="docs/cover.svg" width="720" alt="code-counter cover">

Python-библиотека и CLI для подсчёта физических строк кода в каталоге. Учитывает `.gitignore`, группирует по расширениям, опционально считает вклад авторов через `git blame --incremental`. Runtime - только stdlib; внешние pip-зависимости не нужны.

## Запуск

PyPI:

```bash
pip install code-counter-ntwusr
code-counter .
```

Из исходников:

```bash
pip install -e ".[dev]"
code-counter .
```

### API

```python
from code_counter import analyze_project, CodeCounter, Analysis

analysis = analyze_project(".", as_json=False)  # печатает отчёт и возвращает Analysis
counter = CodeCounter(".")
result = counter.analyze(with_author=True, jobs=4)
total = result.total_lines
```

Публичный API: `CodeCounter`, `GitIgnoreParser`, `Analysis`, `analyze_project()` (`__all__` в `code_counter.py`).

## Команды

| Команда | Назначение |
|---------|------------|
| `code-counter [path]` | Анализ каталога (default: `.`) |
| `code-counter -f` / `--files` | Показать крупнейшие файлы |
| `code-counter -n N` / `--top N` | Сколько файлов в топе (default: 10) |
| `code-counter --no-blame` | Без статистики по авторам |
| `code-counter --all-text` | Любые текстовые файлы, не только code extensions |
| `code-counter --ext .foo .bar` | Добавить расширения к дефолтному списку |
| `code-counter -j N` / `--jobs N` | Worker-потоки для git blame |
| `code-counter --json` | Вывод `Analysis.to_dict()` в stdout |
| `code-counter -v` / `--version` | Версия (`code_counter.__version__`, сейчас 0.2.0) |
| `pytest` | Тесты (`tests/`, `testpaths` в `pyproject.toml`) |
| `ruff check .` | Lint (`line-length = 100`, `py312`) |
| `mypy code_counter.py` | Typecheck (dev dependency) |

Entry point: `[project.scripts]` → `code-counter = code_counter:main`.

## Стек

<p>
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white" alt="pytest" />
  <img src="https://img.shields.io/badge/ruff-D7FF64?style=for-the-badge&logo=ruff&logoColor=black" alt="ruff" />
  <img src="https://img.shields.io/badge/Git-F05032?style=for-the-badge&logo=git&logoColor=white" alt="Git" />
  <img src="https://img.shields.io/badge/setuptools-555555?style=for-the-badge" alt="setuptools" />
  <img src="https://img.shields.io/badge/mypy-2C5282?style=for-the-badge" alt="mypy" />
</p>

## Тесты

```bash
pytest
```

## Архитектура

Один модуль `code_counter.py`: парсер `.gitignore`, обход каталога, подсчёт строк в бинарном режиме, git blame через `ThreadPoolExecutor`. CLI - `argparse` в `main()`.

```
code-counter/
├── code_counter.py              # GitIgnoreParser, CodeCounter, CLI (v0.2.0)
├── pyproject.toml               # setuptools, entry point, ruff/pytest/mypy
├── conftest.py                  # делает плоский модуль импортируемым из тестов
├── AGENTS.md                    # инструкции для coding-агентов
├── CLAUDE.md                    # обёртка → AGENTS.md
├── .cursor/rules/
│   └── dotcore-project.mdc
├── docs/
│   └── cover.svg
└── tests/
    ├── test_counter.py
    └── test_gitignore.py
```

- **Физические строки**: подсчёт по `\n` в бинарном чтении, не AST и не logical LOC
- **gitignore**: wildcards, `**`, якоря, directory-only (`/`), negation (`!`)
- **Расширения**: 129 suffix + 9 имён файлов (Makefile, Dockerfile…); override через `--all-text` / `--ext`
- **Author stats**: `git blame --incremental`, параллельно по файлам; без `.git` или git в PATH - пропуск без ошибки
- **Публикация**: PyPI `code-counter-ntwusr`, runtime deps = stdlib

## Лицензия

MIT. Свободное использование, копирование, изменение и распространение с сохранением копирайта и текста лицензии. См. [LICENSE](LICENSE).
