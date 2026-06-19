# AGENTS.md

> Инструкции для AI coding agents. Человеческий обзор - в [README.md](README.md).
> Перегенерировано скиллом `generate-readme`. Источник правды - код репозитория.

## Профиль проекта

- **Тип:** library + cli
- **Аудитория:** oss
- **Runtime:** Python 3.12+
- **Монорепо:** no
- **Дистрибуция:** GitHub + PyPI (`code-counter-ntwusr`)

## Быстрый старт

```bash
pip install -e ".[dev]"
code-counter .
```

## Сборка и проверки

| Действие | Команда |
|----------|---------|
| Установка (dev) | `pip install -e ".[dev]"` |
| Установка (PyPI) | `pip install code-counter-ntwusr` |
| CLI | `code-counter [path]` |
| Тесты | `pytest` |
| Lint | `ruff check .` |
| Typecheck | `mypy code_counter.py` |
| Build | `python -m build` (setuptools, при необходимости) |

Команды - из `pyproject.toml` и CLI в `code_counter.py`.

## Структура репозитория

```
code-counter/
├── code_counter.py
├── pyproject.toml
├── conftest.py
├── AGENTS.md
├── CLAUDE.md
├── .cursor/rules/dotcore-project.mdc
├── docs/cover.svg
└── tests/
```

## Соглашения

- **Язык документации:** русский.
- **Стиль кода:** ruff (`line-length = 100`, `target-version = py312`).
- **Именование:** следуй существующим модулям и тестам.
- **Runtime deps:** только stdlib; dev - pytest, ruff, mypy.

## Переменные окружения

Нет обязательных env для CLI. Для author stats нужен `git` в PATH и каталог `.git`.

## Что делать агенту

- Перед правками прочитай `code_counter.py` и затронутые тесты.
- После изменений запусти `pytest` и `ruff check .`.
- Обновляй `README.md` и `AGENTS.md` через скилл `generate-readme`, не латай разметку вручную.
- Минимальный diff - не рефактори несвязанный код.
- Числа (LoC, расширения) - из `code-counter .` или кода, не выдумывай.

## Чего не делать

- Не выдумывать команды, зависимости, env, API.
- Не добавлять `<details>`, centered hero, emoji в README DotCore.
- Не менять `docs/cover.svg` без регенерации обложки.
- Не коммитить секреты.
- Не удалять маркеры `<!-- loc:start -->` / `<!-- loc:end -->` в README.

## Документация

- [README.md](README.md) - запуск, команды, стек, архитектура

## DotCore

Плоский технический README, SVG-обложка DotBioSite (`docs/cover.svg`), LoC-бейдж под cover. При запросе «обнови README» используй скилл `generate-readme`.
