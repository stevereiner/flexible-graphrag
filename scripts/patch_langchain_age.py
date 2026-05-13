"""
Patch antlr4-python3-runtime for Python 3.14 compatibility with langchain-age.

Background
----------
langchain-age bundles the Apache AGE Python driver under langchain_age/_vendor/age/.
That driver includes ANTLR4-generated grammar files whose serializedATN() returns an
int list starting with 4 (the ATN serialization version used by the ANTLR tool).

Some builds of antlr4-python3-runtime==4.13.2 have SERIALIZED_VERSION=3 and no
version-4 deserializer path, causing an import failure on all Python versions.  Other
builds of the same version have SERIALIZED_VERSION=4 natively and work without patching.
This script makes no changes when the installed build already works.  Two additional issues
exist in the SERIALIZED_VERSION=3 builds specific to Python 3.14:

  - reset(): Python 3.14 is stricter about ord() argument types.  The old code called
    ord(c) on values that are already ints when the input is an int list, raising
    TypeError.  (antlr4-python3-runtime 4.13.2 already fixed this; 4.11.1 did not.)

  - __slots__: ATNDeserializer declares __slots__ with no __dict__ fallback.  Our
    checkVersion() patch stores self._ver, which requires '_ver' in __slots__.
    Python 3.14 enforces this strictly — older versions were sometimes more lenient.

This script applies four targeted patches to ATNDeserializer.py in the installed
antlr4-python3-runtime (tested with 4.11.1 and 4.13.2):

  1. __slots__: add '_ver' slot
  2. reset(): accept int-list input directly (4.11.1 only — 4.13.2 already fixed)
  3. checkVersion(): accept version 3 or 4; save detected version in self._ver
  4. checkUUID(): skip UUID header read for version-4 int-list data
  5. deserialize(): skip SMP readInt32 block for version-4 data

Usage
-----
Run once after installing the age-extras group:

    uv pip install --override extras-overrides.txt -e ".[langchain,langchain-extras,age-extras]"
    python scripts/patch_langchain_age.py

The patch is idempotent — safe to run multiple times.

The files that langchain-age==0.1.2 ships work correctly once this patch is applied.
"""
import sys
import pathlib
import importlib.metadata
import subprocess


SUPPORTED_ANTLR_VERSIONS = {"4.11.1", "4.13.2"}
_PATCH_MARKER = "# [flexible-graphrag py314 patch applied]"


def check_environment() -> str:
    ver = importlib.metadata.version("antlr4-python3-runtime")
    if ver not in SUPPORTED_ANTLR_VERSIONS:
        print(
            f"WARNING: antlr4-python3-runtime=={ver} is not in tested set "
            f"{SUPPORTED_ANTLR_VERSIONS}.\n"
            f"  Patch may still work — proceeding anyway.",
        )
    return ver


def find_atn_deserializer() -> pathlib.Path:
    import antlr4
    p = pathlib.Path(antlr4.__file__).parent / "atn" / "ATNDeserializer.py"
    if not p.exists():
        raise FileNotFoundError(f"ATNDeserializer.py not found at {p}")
    return p


# ---------------------------------------------------------------------------
# Patches
# ---------------------------------------------------------------------------

_SLOTS_OLD = "    __slots__ = ('deserializationOptions', 'data', 'pos', 'uuid')"
_SLOTS_NEW = "    __slots__ = ('deserializationOptions', 'data', 'pos', 'uuid', '_ver')"

# Patch 2 only needed for antlr4-python3-runtime 4.11.1 — 4.13.2 already handles int lists.
_RESET_OLD = '''\
    def reset(self, data:str):
        def adjust(c):
            v = ord(c) if isinstance(c,str) else c
            return v-2 if v>1 else v + 65533
        temp = [ adjust(c) for c in data ]
        # don't adjust the first value since that's the version number
        temp[0] = ord(data[0]) if isinstance(data[0], str) else data[0]
        self.data = temp
        self.pos = 0'''

_RESET_NEW = '''\
    def reset(self, data:str):
        # antlr4 tool >= 4.10 generates int lists — store directly without adjustment.
        if data and isinstance(data[0], int):
            self.data = list(data)
        else:
            def adjust(c):
                v = ord(c) if isinstance(c, str) else c
                return v-2 if v>1 else v + 65533
            temp = [ adjust(c) for c in data ]
            # don't adjust the first value since that's the version number
            temp[0] = ord(data[0]) if isinstance(data[0], str) else data[0]
            self.data = temp
        self.pos = 0'''

_CHECK_VERSION_OLD = '''\
    def checkVersion(self):
        version = self.readInt()
        if version != SERIALIZED_VERSION:
            raise Exception("Could not deserialize ATN with version " + str(version) + " (expected " + str(SERIALIZED_VERSION) + ").")'''

_CHECK_VERSION_NEW = '''\
    def checkVersion(self):
        version = self.readInt()
        if version not in (SERIALIZED_VERSION, 4):
            raise Exception("Could not deserialize ATN with version " + str(version) + " (expected " + str(SERIALIZED_VERSION) + ").")
        self._ver = version'''

_CHECK_UUID_OLD = '''\
    def checkUUID(self):
        uuid = self.readUUID()
        if not uuid in SUPPORTED_UUIDS:
            raise Exception("Could not deserialize ATN with UUID: " + str(uuid) + \\
                            " (expected " + str(SERIALIZED_UUID) + " or a legacy UUID).", uuid, SERIALIZED_UUID)
        self.uuid = uuid'''

_CHECK_UUID_NEW = '''\
    def checkUUID(self):
        if getattr(self, '_ver', SERIALIZED_VERSION) == 4:
            self.uuid = SERIALIZED_UUID
            return
        uuid = self.readUUID()
        if not uuid in SUPPORTED_UUIDS:
            raise Exception("Could not deserialize ATN with UUID: " + str(uuid) + \\
                            " (expected " + str(SERIALIZED_UUID) + " or a legacy UUID).", uuid, SERIALIZED_UUID)
        self.uuid = uuid'''

_READ_SETS_OLD = '''\
        if self.isFeatureSupported(ADDED_UNICODE_SMP, self.uuid):
            self.readSets(atn, sets, self.readInt32)'''

_READ_SETS_NEW = '''\
        if getattr(self, '_ver', SERIALIZED_VERSION) != 4 and self.isFeatureSupported(ADDED_UNICODE_SMP, self.uuid):
            self.readSets(atn, sets, self.readInt32)'''

PATCHES = [
    (_SLOTS_OLD,         _SLOTS_NEW,          "__slots__: add _ver slot"),
    (_RESET_OLD,         _RESET_NEW,          "reset(): accept int-list format (4.11.1 only)"),
    (_CHECK_VERSION_OLD, _CHECK_VERSION_NEW,  "checkVersion(): accept version 3 or 4"),
    (_CHECK_UUID_OLD,    _CHECK_UUID_NEW,     "checkUUID(): skip UUID header for version 4"),
    (_READ_SETS_OLD,     _READ_SETS_NEW,      "deserialize(): skip SMP block for version 4"),
]


def patch_atn_deserializer(path: pathlib.Path) -> bool:
    """Apply patches to ATNDeserializer.py.  Returns True if any patch was applied."""
    src = path.read_text(encoding="utf-8")

    if _PATCH_MARKER in src:
        print(f"  [already patched] {path.name}")
        return False

    patched = src
    applied = []
    for old, new, label in PATCHES:
        if old in patched:
            patched = patched.replace(old, new, 1)
            applied.append(label)
            print(f"  [applied] {label}")
        elif new in patched:
            print(f"  [already present] {label}")
        else:
            print(f"  [skip] {label} — target not found (not needed for this build)")

    if applied:
        patched = _PATCH_MARKER + "\n" + patched
        path.write_text(patched, encoding="utf-8")
        for pyc in path.parent.glob(f"__pycache__/{path.stem}*.pyc"):
            pyc.unlink(missing_ok=True)
        return True
    else:
        print(f"  [no changes] this build does not need patching")
        return False


def smoke_test() -> bool:
    result = subprocess.run(
        [sys.executable, "-c",
         "from langchain_age.graphs.age_graph import AGEGraph; print('AGEGraph import OK')"],
        capture_output=True, text=True,
    )
    out = result.stdout.strip() or result.stderr.strip()
    print(f"\nSmoke test: {out}")
    return result.returncode == 0


if __name__ == "__main__":
    try:
        ver = check_environment()
        path = find_atn_deserializer()
        print(f"antlr4-python3-runtime=={ver}  ({path})\n")
        changed = patch_atn_deserializer(path)
        if not smoke_test():
            print("ERROR: smoke test failed — check the error above.", file=sys.stderr)
            sys.exit(1)
        if changed:
            print("Patch applied successfully.")
        else:
            print("No changes made — build already compatible.")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
