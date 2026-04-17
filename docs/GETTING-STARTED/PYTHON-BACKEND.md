# Python Backend Installation

## Option A — Install from PyPI

```bash
# 1. Create and activate a virtual environment
uv venv venv-3.13 --python 3.13
venv-3.13\Scripts\Activate   # Windows
source venv-3.13/bin/activate  # Linux/macOS

# 2. Install flexible-graphrag
uv pip install flexible-graphrag

# 3. Optional: ArcadeDB embedded mode
uv pip install arcadedb>=26.3.2

# 3a. Optional: LangChain support
uv pip install "flexible-graphrag[langchain]"

# 4. Create .env from sample
copy env-sample.txt .env   # Windows
cp env-sample.txt .env     # Linux/macOS
# Edit .env with your LLM API keys and database settings

# 5. Start databases
docker compose -f docker/docker-compose.yml up -d

# 6. Start the backend
flexible-graphrag
```

## Option B — Install from source (editable)

```bash
cd flexible-graphrag
uv venv venv-3.13 --python 3.13
venv-3.13\Scripts\Activate   # Windows
source venv-3.13/bin/activate  # Linux/macOS
uv pip install -e .

# Optional extras
uv pip install -e ".[langchain]"
uv pip install -e ".[langchain,langchain-extras]"
uv pip install arcadedb>=26.3.2

cp env-sample.txt .env   # Linux/macOS
copy env-sample.txt .env  # Windows

# Start the backend
flexible-graphrag
# or: uv run start.py
```

The backend will be available at `http://localhost:8000`.

!!! note "Windows Build Tools"
    If installation fails with "Microsoft Visual C++ 14.0 or greater is required", install [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) — select "Desktop development with C++".
