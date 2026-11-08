"""Where Hedera stands in the code of a repository (design 7.3, 21 October 2026).

The archive of the repository's default branch is read as a stream, on this computer, and
nothing of it is kept. Every file of the project's own code is read, with no order and no
limit on how many. What is kept is what the plain text matching found, with no AI:

* **packages:** the Hedera packages that the package files name: package.json, requirements
  files, pyproject.toml, Pipfile, go.mod, Cargo.toml, pom.xml, build.gradle, Package.swift and
  .csproj. The names of all their dependencies are kept too, so that a later rule can read them
  again; no other part of a package file is kept (it can name its authors);
* **features:** the Hedera services that the source code calls, by the names of the classes of
  Hedera's SDKs, which are the same in every language (TopicCreateTransaction and the like), in
  the files that the project uses;
* **unused:** the same, in files that nothing in the project uses: no other file imports them,
  and none of them is where a program starts (a file that package.json names, a Python file with
  a __main__ block, a file at the root, a usual name such as index or main, or a usual folder such
  as pages, api, scripts or tests). Such a file is written and never reached, like a wrapper kept
  for later (8 November 2026: a submission named the Token and File Services only in two such
  files, and the check counted them as called). When it is not sure, a file counts as used. Only
  JavaScript, TypeScript and Python are read this way; in other languages every file is used;
* **imports:** the source files that import a Hedera library;
* **signs:** Hedera's JSON-RPC relay (Hashio) or its chain IDs in the code or the settings of an
  EVM project, a Hedera network taken from an EVM tool (viem, wagmi, thirdweb, or a network of
  Hardhat or Foundry named after Hedera), Hedera's system contracts in Solidity, and the mirror
  node read by the code;
* **mentions:** the files that name Hedera, Hashgraph or Hiero at all, in code, settings or
  comments. The weakest sign, kept so that a person sees where to look when nothing else was
  found;
* **IDs:** the Hedera IDs that the files name, by the rules of the page (parse/hedera_ids.py),
  each with the files where it stands (24 October 2026). Only the ID, its network when the text
  names one, and the paths are kept, never the words around it: in a file of example settings
  the next line can hold a key. Whether an ID proves anything is for the check to say
  (pipeline/code_ids.py): code also names things that many teams use, such as a public token.

It says what the code names. It does not run the code, and it cannot tell whether a line is ever
executed: only whether a file is ever imported, or starts a program. Folders of other people's
code (node_modules, vendor) and generated files are left out: they are not the project's own
code. Files named .env are never opened: they may hold secrets.
"""

from __future__ import annotations

import hashlib
import io
import json
import posixpath
import re
import tarfile
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from hackathon_memory.parse.hedera_ids import find_ids

# 2 (21 October 2026): the Hedera networks of EVM tools, and the mentions. 3 (24 October 2026):
# the Hedera IDs that the code names. 4 (8 November 2026): the services in files that nothing uses.
FORMAT = 4
EXAMPLES = 10  # the files kept as examples for each thing found; the count is always complete
# The most IDs kept for one repository. In 40 repositories of the collection the code named 161
# IDs in all, 23 at most in one (evals/results/20261023T224559Z-ids-in-code.json); more than this
# is a list of somebody else's things, such as the tokens of an exchange.
MOST_IDS = 200
MAX_FILE_BYTES = 1_000_000  # a larger file is a bundle or data, not code that a team wrote

# Folders that hold other people's code, or files made by a tool from the project's code.
SKIPPED_FOLDERS = frozenset({
    "node_modules", "vendor", "bower_components", ".git", "dist", "build", "out", ".next",
    ".nuxt", ".svelte-kit", ".turbo", "coverage", "artifacts", "cache", "typechain",
    "typechain-types", "target", "__pycache__", ".venv", "venv", "site-packages", ".yarn",
    ".pnpm-store", ".expo",
})  # fmt: skip
SKIPPED_FILES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "cargo.lock", "go.sum",
    "poetry.lock", "pipfile.lock", "uv.lock",
})  # fmt: skip
SOURCE_SUFFIXES = frozenset({
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts", ".vue", ".svelte", ".py",
    ".go", ".rs", ".java", ".kt", ".kts", ".scala", ".sol", ".swift", ".cs", ".toml", ".yaml",
    ".yml", ".json", ".ipynb",
})  # fmt: skip
# Settings files that only show placeholders; a real .env file is never opened.
EXAMPLE_ENV = frozenset({".env.example", ".env.sample", ".env.template", "env.example"})
# The files whose use is read from what imports them (8 November 2026).
JS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".vue", ".svelte")
PY_SUFFIXES = (".py",)
# Where a program starts, by the usual folders and names of the frameworks: a file there is used
# even when no other file imports it (pages and api of Next.js, routes of SvelteKit, scripts and
# tasks of Hardhat, tests, serverless functions).
ENTRY_FOLDERS = frozenset({
    "pages", "app", "api", "routes", "scripts", "script", "bin", "cmd", "test", "tests",
    "__tests__", "spec", "specs", "e2e", "cypress", "examples", "example", "demo", "demos",
    "tasks", "deploy", "migrations", "functions", "netlify", "supabase", "notebooks",
})  # fmt: skip
ENTRY_STEMS = frozenset({
    "index", "main", "app", "server", "cli", "bot", "worker", "start", "run", "manage", "wsgi",
    "asgi", "setup", "deploy", "seed", "agent", "page", "layout", "route", "middleware",
})  # fmt: skip

# --------------------------------------------------------------------------- the rules

NPM, PYPI, GO, CARGO, MAVEN, SWIFT, NUGET = "npm", "pypi", "go", "cargo", "maven", "swift", "nuget"

_NPM_PREFIXES = ("@hashgraph/", "@hiero-ledger/", "@hashgraphonline/")
_NPM_NAMES = frozenset({"hashconnect", "hedera-agent-kit"})
_PYPI_NAMES = frozenset({"hiero-sdk-python", "hedera-sdk-py", "hedera-agent-kit",
                         "hiero-did-sdk-python"})  # fmt: skip
_GO_PREFIXES = ("github.com/hiero-ledger/", "github.com/hashgraph/")
_CARGO_NAMES = frozenset({"hedera", "hedera-proto"})
_MAVEN_PREFIXES = ("com.hedera.hashgraph:", "org.hiero:", "com.open-elements.hiero:")


def is_hedera_package(ecosystem: str, name: str) -> bool:
    """Whether a dependency is a Hedera library, by its ecosystem and its name."""
    name = name.strip().lower()
    if ecosystem == NPM:
        return name.startswith(_NPM_PREFIXES) or name in _NPM_NAMES
    if ecosystem == PYPI:
        name = name.replace("_", "-")
        return name in _PYPI_NAMES or name.startswith("hiero-")
    if ecosystem == GO:
        return name.startswith(_GO_PREFIXES)
    if ecosystem == CARGO:
        return name in _CARGO_NAMES or name.startswith("hiero")
    if ecosystem == MAVEN:
        return name.startswith(_MAVEN_PREFIXES)
    if ecosystem == SWIFT:
        return "hiero-sdk-swift" in name or "hedera-sdk-swift" in name
    if ecosystem == NUGET:
        return name == "hashgraph" or name.startswith("hedera")
    return False


# The Hedera services, by the classes of Hedera's SDKs that call them. In Go the classes are
# made by functions such as NewTopicCreateTransaction, so a name may follow other letters.
FEATURES: dict[str, re.Pattern[str]] = {
    "Consensus Service (topics)": re.compile(
        r"Topic(?:Create|Update|Delete|MessageSubmit)Transaction\b|TopicMessageQuery\b|"
        r"TopicInfoQuery\b"
    ),
    "Token Service": re.compile(
        r"Token(?:Create|Mint|Burn|Associate|Dissociate|Update|Delete|Wipe|Freeze|Unfreeze|"
        r"GrantKyc|RevokeKyc|Pause|Unpause|FeeScheduleUpdate|UpdateNfts|Airdrop|ClaimAirdrop|"
        r"CancelAirdrop|Reject)Transaction\b|TokenInfoQuery\b|TokenNftInfoQuery\b"
    ),
    "Smart contracts": re.compile(
        r"Contract(?:Create|Execute|Update|Delete)Transaction\b|ContractCreateFlow\b|"
        r"ContractCallQuery\b|ContractInfoQuery\b|ContractBytecodeQuery\b"
    ),
    "Accounts and HBAR transfers": re.compile(
        r"Account(?:Create|Update|Delete)Transaction\b|TransferTransaction\b|"
        r"AccountBalanceQuery\b|AccountInfoQuery\b|AccountRecordsQuery\b|"
        r"AccountAllowance(?:Approve|Delete)Transaction\b"
    ),
    "File Service": re.compile(
        r"File(?:Create|Append|Update|Delete)Transaction\b|FileContentsQuery\b|FileInfoQuery\b"
    ),
    "Scheduled transactions": re.compile(
        r"Schedule(?:Create|Sign|Delete)Transaction\b|ScheduleInfoQuery\b"
    ),
    "Random numbers": re.compile(r"PrngTransaction\b"),
    "Batch transactions": re.compile(r"\bBatchTransaction\b"),
}

RELAY = "Hedera JSON-RPC relay (Hashio)"
CHAIN_ID = "Hedera chain ID in EVM settings"
EVM_NETWORK = "Hedera network of an EVM tool"
SYSTEM_CONTRACTS = "Hedera system contracts in Solidity"
MIRROR_NODE = "Mirror node read by the code"

_RELAY = re.compile(r"hashio\.io", re.IGNORECASE)
# 295, 296 and 297 are the chain IDs of mainnet, testnet and previewnet (0x127 to 0x129).
_CHAIN_ID = re.compile(r"chain[_-]?id[\"']?\s*[:=]\s*[\"']?(?:0x12[789]|29[567])\b", re.IGNORECASE)
# A Hedera network taken from an EVM tool: the chains "hedera", "hederaTestnet" and
# "hederaPreviewnet" of viem and wagmi, a chain of thirdweb made from a Hedera chain ID, and a
# network named after Hedera in the settings of Hardhat, Truffle or Foundry.
_EVM_CHAINS = re.compile(
    r"import\s*\{[^}]{0,3000}?\bhedera(?:Testnet|Previewnet)?\b[^}]{0,3000}?\}\s*from\s*"
    r"[\"'](?:viem/chains|wagmi/chains|@wagmi/core/chains)[\"']"
    r"|\bdefineChain\(\s*(?:29[567]|0x12[789])\s*\)"
)
_EVM_SETTINGS = re.compile(
    r"[\"']?\bhedera(?:[_-]?(?:testnet|mainnet|previewnet|local))?[\"']?\s*[:=]", re.IGNORECASE
)
_EVM_SETTINGS_FILES = ("hardhat.config.", "truffle-config.", "truffle.", "foundry.toml")
_MENTION = re.compile(r"hedera|hashgraph|\bhiero(?:\b|[-_])", re.IGNORECASE)  # not hieroglyph
_SYSTEM_CONTRACTS = re.compile(
    r"\bI?HederaTokenService\b|\bHederaResponseCodes\b|\bIPrngSystemContract\b|"
    r"\bIExchangeRate\b|address\(0x16[789]\)|0x0{37}16[789]\b"
)
_SYSTEM_CONTRACT_FILES = frozenset({
    "hederatokenservice.sol", "ihederatokenservice.sol", "hederaresponsecodes.sol",
    "iprngsystemcontract.sol", "prngsystemcontract.sol", "iexchangerate.sol",
    "safehts.sol", "expiryhelper.sol", "keyhelper.sol", "feehelper.sol",
})  # fmt: skip
_MIRROR = re.compile(
    r"mirrornode\.hedera\.com|/api/v1/(?:accounts|topics|tokens|contracts|transactions)/0\.0\.",
    re.IGNORECASE,
)
# An import of a Hedera library, in each language that the rules above know.
_IMPORTS = re.compile(
    r"""(?:from\s+|require\(\s*|import\s*\(?\s*)["'](?:@hashgraph/|@hiero-ledger/|"""
    r"""@hashgraphonline/|hashconnect["'/]|hedera-agent-kit["'/])"""
    r"""|^\s*(?:from|import)\s+hiero_sdk_python\b"""
    r"""|"github\.com/(?:hiero-ledger|hashgraph)/[^"]+\""""
    r"""|\buse\s+hedera::|^\s*import\s+com\.hedera\.hashgraph\b|^\s*using\s+Hashgraph\b""",
    re.MULTILINE,
)

# --------------------------------------------------------------------------- package files


def _names_pep508(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    names = []
    for item in items:
        if isinstance(item, str) and (found := re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", item)):
            names.append(found.group(1))
    return names


def _keys(table: object) -> list[str]:
    return [str(key) for key in table] if isinstance(table, dict) else []


def package_json(text: str) -> list[str]:
    data = json.loads(text)
    if not isinstance(data, dict):
        return []
    names: list[str] = []
    for part in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        names += _keys(data.get(part))
    return names


def requirements(text: str) -> list[str]:
    names = []
    for line in text.splitlines():
        line = line.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-"):
            egg = re.search(r"#egg=([A-Za-z0-9._-]+)", line)
            if egg:
                names.append(egg.group(1))
            continue
        found = re.match(r"([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        if found:
            names.append(found.group(1))
    return names


def pyproject(text: str) -> list[str]:
    data = tomllib.loads(text)
    project = data.get("project", {})
    names = _names_pep508(project.get("dependencies"))
    for extra in (project.get("optional-dependencies") or {}).values():
        names += _names_pep508(extra)
    for group in (data.get("dependency-groups") or {}).values():
        names += _names_pep508(group)
    poetry = data.get("tool", {}).get("poetry", {})
    names += _keys(poetry.get("dependencies")) + _keys(poetry.get("dev-dependencies"))
    for group in (poetry.get("group") or {}).values():
        if isinstance(group, dict):
            names += _keys(group.get("dependencies"))
    return [name for name in names if name.lower() != "python"]


def pipfile(text: str) -> list[str]:
    data = tomllib.loads(text)
    return _keys(data.get("packages")) + _keys(data.get("dev-packages"))


def go_mod(text: str) -> list[str]:
    names = []
    in_block = False
    for line in text.splitlines():
        line = line.split("//", 1)[0].strip()
        if line.startswith("require ("):
            in_block = True
            continue
        if in_block and line == ")":
            in_block = False
            continue
        if line.startswith("require "):
            line = line.removeprefix("require ").strip()
        elif not in_block:
            continue
        found = re.match(r"(\S+)\s+v\S+", line)
        if found:
            names.append(found.group(1))
    return names


def cargo_toml(text: str) -> list[str]:
    data = tomllib.loads(text)
    names: list[str] = []
    for part in ("dependencies", "dev-dependencies", "build-dependencies"):
        names += _keys(data.get(part))
    names += _keys((data.get("workspace") or {}).get("dependencies"))
    for target in (data.get("target") or {}).values():
        if isinstance(target, dict):
            for part in ("dependencies", "dev-dependencies", "build-dependencies"):
                names += _keys(target.get(part))
    return names


def pom_xml(text: str) -> list[str]:
    return [f"{group}:{artifact}" for group, artifact in re.findall(
        r"<groupId>\s*([^<\s]+)\s*</groupId>\s*<artifactId>\s*([^<\s]+)\s*</artifactId>", text
    )]  # fmt: skip


def gradle(text: str) -> list[str]:
    return [found for found in re.findall(r"""["']([\w.\-]+:[\w.\-]+)(?::[^"']*)?["']""", text)]


def package_swift(text: str) -> list[str]:
    return re.findall(r"https?://(github\.com/[\w.\-]+/[\w.\-]+?)(?:\.git)?[\"']", text)


def csproj(text: str) -> list[str]:
    return re.findall(r"<PackageReference\s+Include=\"([^\"]+)\"", text)


# The package files, by their name: how to read them, and their ecosystem.
PackageReader = Callable[[str], list[str]]


def package_file(name: str) -> tuple[str, PackageReader] | None:
    """The ecosystem and the reader of a package file, by its file name, or None."""
    lower = name.lower()
    if lower == "package.json":
        return NPM, package_json
    if re.fullmatch(r"requirements[\w.-]*\.txt", lower):
        return PYPI, requirements
    if lower == "pyproject.toml":
        return PYPI, pyproject
    if lower == "pipfile":
        return PYPI, pipfile
    if lower == "go.mod":
        return GO, go_mod
    if lower == "cargo.toml":
        return CARGO, cargo_toml
    if lower == "pom.xml":
        return MAVEN, pom_xml
    if lower in ("build.gradle", "build.gradle.kts"):
        return MAVEN, gradle
    if lower == "package.swift":
        return SWIFT, package_swift
    if lower.endswith(".csproj"):
        return NUGET, csproj
    return None


# --------------------------------------------------------------------------- reading


@dataclass
class Seen:
    """In how many files a thing stands, with the first files as examples."""

    files: int = 0
    examples: list[str] = field(default_factory=list)

    def add(self, path: str) -> None:
        self.files += 1
        if len(self.examples) < EXAMPLES:
            self.examples.append(path)


# The kinds of things found, as the table hedera_in_code names them (migration 0014).
PACKAGE, FEATURE, SIGN, IMPORT, MENTION = "package", "feature", "sign", "import", "mention"
IMPORT_NAME = "a Hedera library"
MENTION_NAME = "the word Hedera, Hashgraph or Hiero"


@dataclass(frozen=True)
class Found:
    """One thing found in the code: its kind, its name, in how many files, and the first ones."""

    kind: str
    name: str
    files: int
    examples: tuple[str, ...]


@dataclass
class IdInCode:
    """A Hedera ID that the code names: its network when the text names one, and the files."""

    entity_id: str
    network: str | None
    seen: Seen = field(default_factory=Seen)

    def to_record(self) -> dict:
        return {"id": self.entity_id, "network": self.network, "files": self.seen.files,
                "examples": self.seen.examples}  # fmt: skip


@dataclass
class CodeScan:
    format: int = FORMAT  # the version of the rules that made this reading
    files: int = 0  # files of the project's own code that were read
    commit: str | None = None  # the commit that the archive was made from, from its header
    archive_bytes: int = 0
    archive_sha256: str = ""
    partial: str | None = None  # why the reading stopped before the end, or None
    packages: dict[str, list[str]] = field(default_factory=dict)  # a package: its files
    dependencies: dict[str, list[str]] = field(default_factory=dict)  # a package file: names
    unreadable: list[str] = field(default_factory=list)  # package files that could not be read
    features: dict[str, Seen] = field(default_factory=dict)  # in files that the project uses
    unused: dict[str, Seen] = field(default_factory=dict)  # in files that nothing uses
    signs: dict[str, Seen] = field(default_factory=dict)
    imports: Seen = field(default_factory=Seen)
    mentions: Seen = field(default_factory=Seen)  # files that name Hedera at all
    ids: dict[tuple[str, str | None], IdInCode] = field(default_factory=dict)
    ids_cut: bool = False  # more than MOST_IDS IDs: the first ones are kept

    @property
    def unused_only(self) -> dict[str, Seen]:
        """The services that only files that nothing uses name: none is called."""
        return {name: one for name, one in self.unused.items() if name not in self.features}

    @property
    def uses_hedera(self) -> bool:
        """A package, an import, a call or a sign: more than a mention."""
        return bool(self.packages or self.features or self.signs or self.imports.files)

    def found(self) -> list[Found]:
        """What was found, one item for each thing: the packages, the features, the signs, the
        files that import a Hedera library and the files that mention it, in this order."""
        items = [Found(PACKAGE, name, len(files), tuple(files[:EXAMPLES]))
                 for name, files in sorted(self.packages.items())]  # fmt: skip
        for kind, things in ((FEATURE, self.features), (SIGN, self.signs)):
            items += [Found(kind, name, one.files, tuple(one.examples))
                      for name, one in sorted(things.items())]  # fmt: skip
        for kind, name, one in ((IMPORT, IMPORT_NAME, self.imports),
                                (MENTION, MENTION_NAME, self.mentions)):  # fmt: skip
            if one.files:
                items.append(Found(kind, name, one.files, tuple(one.examples)))
        return items

    def to_json(self) -> bytes:
        def seen(found: dict[str, Seen]) -> dict:
            return {name: {"files": one.files, "examples": one.examples}
                    for name, one in sorted(found.items())}  # fmt: skip

        record = {
            "format": FORMAT, "files": self.files, "commit": self.commit,
            "archive_bytes": self.archive_bytes,
            "archive_sha256": self.archive_sha256, "partial": self.partial,
            "packages": dict(sorted(self.packages.items())),
            "dependencies": dict(sorted(self.dependencies.items())),
            "unreadable": self.unreadable, "features": seen(self.features),
            "unused": seen(self.unused), "signs": seen(self.signs),
            "imports": {"files": self.imports.files, "examples": self.imports.examples},
            "mentions": {"files": self.mentions.files, "examples": self.mentions.examples},
            "ids": [one.to_record() for one in self.ids.values()], "ids_cut": self.ids_cut,
        }  # fmt: skip
        return json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")

    @classmethod
    def from_json(cls, body: bytes) -> CodeScan:
        record = json.loads(body.decode("utf-8"))

        def seen(found: dict) -> dict[str, Seen]:
            return {name: Seen(one["files"], list(one["examples"])) for name, one in found.items()}

        imports = record.get("imports") or {}
        mentions = record.get("mentions") or {}
        ids = {(one["id"], one["network"]): IdInCode(one["id"], one["network"],
                                                     Seen(one["files"], list(one["examples"])))
               for one in record.get("ids") or []}  # fmt: skip
        return cls(
            format=record.get("format", 1), files=record["files"], commit=record.get("commit"),
            archive_bytes=record["archive_bytes"],
            archive_sha256=record.get("archive_sha256", ""), partial=record.get("partial"),
            packages=record.get("packages") or {}, dependencies=record.get("dependencies") or {},
            unreadable=record.get("unreadable") or [], features=seen(record.get("features") or {}),
            unused=seen(record.get("unused") or {}), signs=seen(record.get("signs") or {}),
            imports=Seen(imports.get("files", 0), list(imports.get("examples", []))),
            mentions=Seen(mentions.get("files", 0), list(mentions.get("examples", []))),
            ids=ids, ids_cut=record.get("ids_cut", False),
        )  # fmt: skip


class ReadLimit(Exception):
    """The reading of an archive went past its limit of bytes or of seconds."""


class DownloadBroken(OSError):
    """The download of an archive broke off: the network or the server."""


_COMMIT = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")

# Why a reading stopped before the end of an archive.
LIMIT_BYTES = "the archive is larger than the limit of a live check"
LIMIT_SECONDS = "the archive took longer than the limit of a live check"
BROKE_OFF = "the download broke off"
UNREADABLE = "the archive could not be read to its end"


class LimitedStream(io.RawIOBase):
    """A stream that counts what is read, keeps its SHA-256, and stops at a limit."""

    def __init__(
        self,
        read: Callable[[int], bytes],
        *,
        max_bytes: int | None = None,
        seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._read = read
        self._max_bytes = max_bytes
        self._clock = clock
        self._deadline = clock() + seconds if seconds is not None else None
        self.bytes = 0
        self.digest = hashlib.sha256()
        self.broken: str | None = None  # the error that broke the download off, if one did

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: memoryview) -> int:  # type: ignore[override]
        if self._deadline is not None and self._clock() > self._deadline:
            raise ReadLimit("seconds")
        try:
            data = self._read(len(buffer))
        except Exception as error:  # the network or the server, whatever the library
            self.broken = type(error).__name__
            raise DownloadBroken(self.broken) from None
        if not data:
            return 0
        self.bytes += len(data)
        if self._max_bytes is not None and self.bytes > self._max_bytes:
            raise ReadLimit("bytes")
        self.digest.update(data)
        buffer[: len(data)] = data
        return len(data)


def _commit_of(headers: dict[str, str]) -> str | None:
    """The commit that an archive was made from: git archive writes it as the "comment" of the
    archive's global header (archive-tar.c, write_global_extended_header)."""
    value = str(headers.get("comment", "")).strip().lower()
    return value if _COMMIT.fullmatch(value) else None


def _own_path(member_name: str) -> str | None:
    """The path of a file inside the repository, without the archive's first folder; None for
    a file of a folder that is not the project's own code."""
    parts = PurePosixPath(member_name).parts[1:]
    if not parts or any(part in SKIPPED_FOLDERS for part in parts[:-1]):
        return None
    return "/".join(parts)


def _wanted(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    if name in SKIPPED_FILES or name.endswith((".min.js", ".map")):
        return False
    if name == ".env" or (name.startswith(".env.") and name not in EXAMPLE_ENV):
        return False
    return (
        package_file(name) is not None
        or PurePosixPath(name).suffix in SOURCE_SUFFIXES
        or (name in EXAMPLE_ENV)
    )


@dataclass
class _Calls:
    """The Hedera classes that one file names, kept until the whole archive is read."""

    path: str
    features: list[str]
    imports_hedera: bool


# What a file imports. JavaScript and TypeScript: import ... from "x", import "x", import("x"),
# require("x") and export ... from "x". Python: from x import a, b; import x, y.
_JS_SPECIFIER = re.compile(r"""(?:\bfrom|\bimport|\brequire)\s*\(?\s*["']([^"'\n]{1,300})["']""")
_PY_FROM = re.compile(
    r"^[ \t]*from[ \t]+(\.*[\w.]*)[ \t]+import[ \t]+\(?([\w ,\t*]+)", re.MULTILINE
)
_PY_IMPORT = re.compile(r"^[ \t]*import[ \t]+([\w.]+(?:[ \t]*,[ \t]*[\w.]+)*)", re.MULTILINE)
_PY_MAIN = re.compile(r"""^[ \t]*if[ \t]+__name__[ \t]*==[ \t]*["']__main__["']""", re.MULTILINE)
_NAMED_FILE = re.compile(r"[\w./@-]+\.(?:m?[jt]sx?|c[jt]s|py)\b")


def _bare(path: str) -> str:
    """A path without its suffix: what an import names."""
    return path.rsplit(".", 1)[0] if "." in PurePosixPath(path).name else path


@dataclass
class _Reach:
    """What tells whether a file is used, kept only while the archive is read: every file of the
    code, what each one imports, and the files where a program starts."""

    paths: set[str] = field(default_factory=set)
    imports: dict[str, list[tuple[str, tuple[str, ...]]]] = field(default_factory=dict)
    started: set[str] = field(default_factory=set)  # a Python file with a __main__ block
    named: list[tuple[str, str]] = field(default_factory=list)  # a package.json's folder, a file

    def read(self, path: str, name: str, text: str) -> None:
        self.paths.add(path)
        if name == "package.json":
            for found in _NAMED_FILE.findall(text):
                self.named.append((str(PurePosixPath(path).parent), found))
        if path.endswith(JS_SUFFIXES):
            self.imports[path] = [(found, ()) for found in _JS_SPECIFIER.findall(text)]
        elif path.endswith(PY_SUFFIXES):
            asked = [(module, tuple(part.strip() for part in names.split(",") if part.strip()))
                     for module, names in _PY_FROM.findall(text)]  # fmt: skip
            for names in _PY_IMPORT.findall(text):
                asked += [(part.strip(), ()) for part in names.split(",") if part.strip()]
            self.imports[path] = asked
            if _PY_MAIN.search(text):
                self.started.add(path)

    def used(self) -> set[str]:
        """The files that the project uses: those that another file imports, those where a
        program starts, and every file of a language that is not read this way. When an import
        cannot be placed exactly, every file with its last name counts as imported."""
        tails: dict[str, set[str]] = {}
        for path in self.paths:
            parts = _bare(path).split("/")
            for size in range(1, len(parts) + 1):
                tails.setdefault("/".join(parts[-size:]).lower(), set()).add(path)
        used = {path for path in self.paths if not path.endswith(JS_SUFFIXES + PY_SUFFIXES)}
        used |= {path for path in self.paths if _starts_a_program(path)} | self.started
        for folder, named in self.named:
            used |= _placed(posixpath.normpath(posixpath.join(folder, named)), tails)
        for source, asked in self.imports.items():
            for module, names in asked:
                found = (_placed_js(source, module, tails) if source.endswith(JS_SUFFIXES)
                         else _placed_py(source, module, names, tails))  # fmt: skip
                used |= found - {source}
        return used


def _starts_a_program(path: str) -> bool:
    """A file where a program usually starts: at the root of the repository, in a usual
    folder, with a usual name, a test, a setting of a tool, or a notebook."""
    parts = PurePosixPath(path).parts
    name = parts[-1].lower()
    return (len(parts) == 1 or any(part.lower() in ENTRY_FOLDERS for part in parts[:-1])
            or name.split(".")[0] in ENTRY_STEMS or name.endswith(".ipynb")
            or re.search(r"\.(?:test|spec|config|stories)\.", name) is not None)  # fmt: skip


def _placed(target: str, tails: dict[str, set[str]]) -> set[str]:
    """The files that a path names, with or without its suffix, or as a folder's index."""
    bare = _bare(target).lstrip("./").lower()
    return (
        tails.get(bare, set())
        | tails.get(f"{bare}/index", set())
        | tails.get(f"{bare}/__init__", set())
    )


def _placed_js(source: str, module: str, tails: dict[str, set[str]]) -> set[str]:
    """The files that an import of JavaScript or TypeScript names: by its path when it starts
    with a dot, by the end of its path otherwise (aliases such as @/lib/x), and by its last
    name when neither finds a file."""
    if module.startswith("."):
        found = _placed(posixpath.normpath(posixpath.join(posixpath.dirname(source), module)),
                        tails)  # fmt: skip
    else:
        found = _placed(module.lstrip("@~#/"), tails)
    if not found:
        last = module.rstrip("/").split("/")[-1]
        found = _placed(last, tails) if last and last not in (".", "..") else set()
    return found


def _placed_py(
    source: str, module: str, names: tuple[str, ...], tails: dict[str, set[str]]
) -> set[str]:
    """The files that an import of Python names: the module, relative to the file when it
    starts with dots, and each name taken from it that is a module of its own."""
    dots = len(module) - len(module.lstrip("."))
    rest = module.lstrip(".").replace(".", "/")
    base = posixpath.dirname(source)
    for _ in range(max(dots - 1, 0)):
        base = posixpath.dirname(base)
    root = posixpath.join(base, rest) if dots else rest
    found = _placed(root, tails) if root else set()
    for name in names:
        if name != "*":
            found |= _placed(posixpath.join(root, name) if root else name, tails)
    if not found and rest:
        found = _placed(rest.split("/")[-1], tails)
    return found


def read_file(
    scan: CodeScan, path: str, data: bytes, calls: list[_Calls], reach: _Reach | None = None
) -> None:
    """What one file of the project's code says about Hedera. The classes that it names are
    kept in `calls` and counted at the end (finish), because a class name such as
    TransferTransaction counts only in a file that imports a Hedera library, or in a
    repository whose package files name one."""
    name = PurePosixPath(path).name
    text = data.decode("utf-8", errors="ignore")
    if reach is not None:
        reach.read(path, name, text)
    kind = package_file(name)
    if kind is not None:
        ecosystem, reader = kind
        try:
            names = reader(text)
        except (ValueError, tomllib.TOMLDecodeError):
            scan.unreadable.append(path)
            names = []
        scan.dependencies[path] = sorted(set(names))
        for package in sorted({name for name in names if is_hedera_package(ecosystem, name)}):
            scan.packages.setdefault(package, []).append(path)
    imports_hedera = bool(_IMPORTS.search(text))
    if imports_hedera:
        scan.imports.add(path)
    features = [feature for feature, pattern in FEATURES.items() if pattern.search(text)]
    if features:
        calls.append(_Calls(path, features, imports_hedera))
    signs = set()
    solidity = path.lower().endswith(".sol")
    if name.lower() in _SYSTEM_CONTRACT_FILES or (solidity and _SYSTEM_CONTRACTS.search(text)):
        signs.add(SYSTEM_CONTRACTS)
    if _RELAY.search(text):
        signs.add(RELAY)
    if _CHAIN_ID.search(text):
        signs.add(CHAIN_ID)
    settings = name.lower().startswith(_EVM_SETTINGS_FILES)
    if _EVM_CHAINS.search(text) or (settings and _EVM_SETTINGS.search(text)):
        signs.add(EVM_NETWORK)
    if _MIRROR.search(text):
        signs.add(MIRROR_NODE)
    for sign in sorted(signs):
        scan.signs.setdefault(sign, Seen()).add(path)
    if _MENTION.search(text):
        scan.mentions.add(path)
    for found in find_ids(text):
        key = (found.entity_id, found.network)
        if key not in scan.ids:
            if len(scan.ids) >= MOST_IDS:
                scan.ids_cut = True
                continue
            scan.ids[key] = IdInCode(found.entity_id, found.network)
        scan.ids[key].seen.add(path)


def finish(scan: CodeScan, calls: list[_Calls], reach: _Reach | None = None) -> None:
    """Count the Hedera classes that the files name, now that the package files are known: in
    a file that the project uses as a call, in one that nothing uses apart (`unused`)."""
    used = reach.used() if reach is not None else None
    for one in calls:
        if one.imports_hedera or scan.packages:
            place = scan.features if used is None or one.path in used else scan.unused
            for feature in one.features:
                place.setdefault(feature, Seen()).add(one.path)


def scan_archive(stream: LimitedStream) -> CodeScan:
    """Read a .tar.gz archive of a repository, file after file, and keep what it says about
    Hedera. Stops early at the limit of the stream, and says so in `partial`."""
    scan = CodeScan()
    calls: list[_Calls] = []
    reach = _Reach()
    try:
        with tarfile.open(fileobj=io.BufferedReader(stream, 1 << 16), mode="r|gz") as archive:
            scan.commit = _commit_of(archive.pax_headers)
            for member in archive:
                if not member.isfile() or member.size > MAX_FILE_BYTES:
                    continue
                path = _own_path(member.name)
                if path is None or not _wanted(path):
                    continue
                handle = archive.extractfile(member)
                if handle is None:
                    continue
                scan.files += 1
                read_file(scan, path, handle.read(), calls, reach)
    except ReadLimit as limit:
        scan.partial = LIMIT_BYTES if str(limit) == "bytes" else LIMIT_SECONDS
    except DownloadBroken:
        scan.partial = BROKE_OFF
    except (tarfile.TarError, EOFError, OSError):
        scan.partial = UNREADABLE
    finish(scan, calls, reach)
    scan.archive_bytes = stream.bytes
    scan.archive_sha256 = stream.digest.hexdigest()
    return scan
