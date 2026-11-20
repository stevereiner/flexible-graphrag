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
uv pip install --override extras-overrides.txt -e ".[langchain,langchain-extras]"
# see flexible-graphrag/pyproject.toml for all options

# arcadedb embedded
uv pip install arcadedb-embedded>=26.3.2

cp env-sample.txt .env   # Linux/macOS
copy env-sample.txt .env  # Windows

# Start the backend
flexible-graphrag
# or: uv run start.py
```

The backend will be available at `http://localhost:8000`.

## Platform notes

### Windows: C++ Build Tools

!!! note "Windows Build Tools"
    Several dependencies (`spacy`, `lancedb`, `psycopg2`, and some database drivers) include C extensions that must be compiled on Windows. When running on Windows, `uv pip install` may need to build a platform-specific wheel if a pre-built one is not available for your Python version. If installation fails with "Microsoft Visual C++ 14.0 or greater is required", install [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) and select "Desktop development with C++".

### Linux: compiler and Python headers

!!! note "Linux Build Tools"
    Most dependencies install from pre-built wheels. When a wheel is not available for your Python version or CPU, `uv pip install` builds the package from source. This often happens with a newly released Python, or with a transitive dependency such as `pystemmer`. Building from source needs a C compiler and the Python development headers. Without them the build fails with `Python.h: No such file or directory` or `command 'gcc' failed`.

    Install the packages that match the Python version of your venv:

    ```bash
    # Debian / Ubuntu
    sudo apt install build-essential python3.13-dev   # Python 3.13
    sudo apt install build-essential python3.14-dev   # Python 3.14

    # Fedora / RHEL
    sudo dnf install gcc gcc-c++ python3.13-devel     # Python 3.13
    sudo dnf install gcc gcc-c++ python3.14-devel     # Python 3.14
    ```

    If your distribution doesn't package the Python version you want, use a uv-managed Python (`uv python install 3.14`). It includes its own headers, so you only need the compiler (`build-essential` or `gcc`). On Ubuntu, the [deadsnakes PPA](https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa) is another source for newer Python versions.

    No certificate step is needed. Distribution Pythons and uv-managed Pythons use the system CA store from the `ca-certificates` package.

### macOS: Xcode Command Line Tools

!!! note "macOS Build Tools"
    When a dependency has no pre-built wheel for your Python version, `uv pip install` compiles it from source. This often happens with a newly released Python, or with a transitive dependency such as `pystemmer`. Compiling needs the Xcode Command Line Tools (`clang`, `make`, the macOS SDK). Install them once:

    ```bash
    xcode-select --install
    ```

    You don't need the full Xcode app. A python.org, Homebrew or uv-managed Python already includes its own headers, so there is no separate `-dev` package as on Linux. The same Command Line Tools are also required to build the [Desktop App](DESKTOP-APP.md#prerequisites).

    To check whether they are already installed, run `xcode-select -p`. It prints a path such as `/Library/Developer/CommandLineTools` when they are.

### macOS: Install Certificates (python.org Python)

!!! note "macOS: Install Certificates (python.org Python)"
    The python.org installer for macOS ships its own OpenSSL with an empty CA certificate store. It does not use the macOS Keychain. Until you install certificates, Python's built-in HTTPS (`urllib`, `ssl.create_default_context()`) fails with:

    ```
    ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate
    ```

    - **Installing from source:** the install fails. `pystemmer`, a dependency of `llama-index-retrievers-bm25`, downloads its C sources over HTTPS during the build.
    - **Running from PyPI:** LLM and cloud API calls still work because `httpx` and `requests` bring their own `certifi` bundle. Stdlib downloads, such as NLTK data on first run, can still fail.

    Fix it once per Python version (not per venv) by running the installer's certificate script, matching your Python version:

    ```bash
    # Python 3.13
    "/Applications/Python 3.13/Install Certificates.command"

    # Python 3.14
    "/Applications/Python 3.14/Install Certificates.command"
    ```

    You can also open `/Applications/Python 3.13/` or `/Applications/Python 3.14/` in Finder and double-click **Install Certificates.command**.

    Python from Homebrew, or a uv-managed Python (installed with `uv python install 3.13` or `uv python install 3.14`), already includes CA certificates and does not need this step. Note that `uv venv --python 3.13` (or `3.14`) uses a python.org install if one is present.
