# MiStories

Back up your Instagram Stories — built with Python Reflex
> Important: Before working on this project, read [AGENTS.md](AGENTS.md) for required workflows and tooling expectations.

## Getting Started

> Before making changes, read the project guidelines in [AGENTS.md](AGENTS.md).

This project is managed with [Poetry](https://python-poetry.org/).

### Prerequisites

Based on this project's dependencies, install the following system-level packages first via Homebrew (macOS):

```bash
brew install python@3.11  poetry
```

| Package | Reason |
|---------|--------|
| `python@3.11` | The project requires Python ~3.11 as specified in `pyproject.toml` |
| `poetry` | Python dependency manager used to manage this project |

After installing Playwright (via `poetry install`), you also need to download browser binaries:

```bash
poetry run playwright install
```


### Installation

1. (Recommended) Configure Poetry to store the virtual environment inside the project directory. This makes it easier for IDEs and AI agents to discover and analyze dependency source code:

```bash
poetry config virtualenvs.in-project true
```

> This is a global one-time setting. After this, every project will create its `.venv/` under the project root instead of a shared cache folder (`~/Library/Caches/pypoetry/virtualenvs/`). The `.venv/` directory is already in `.gitignore`.

2. Ensure Poetry uses Python 3.11:

```bash
poetry env use python3.11
poetry env info
```

3. Install dependencies:

```bash
poetry install
```

### Running the App

Start the development server:

```bash
poetry run ./reflex_rerun.sh
```

The application will be available at `http://localhost:3000`.

### Clean Rebuild & Run

To fully clean the environment, reinstall all dependencies, and start the app in one step:

```bash
./proj_reinstall.sh --with-rerun
```

This will remove existing Poetry virtual environments and Reflex artifacts, recreate the environment from scratch, and automatically launch the app afterwards.

---
