"""Where Hedera stands in the code of a repository (design 7.3, 21 October 2026).

The archive of the repository's default branch is read as a stream, on this computer, and
nothing of it is kept. Every file of the project's own code is read, with no order and no
limit on how many. What is kept is what the plain text matching found, with no AI:

* **packages:** the Hedera packages that the package files name: package.json, requirements
  files, pyproject.toml, Pipfile, go.mod, Cargo.toml, pom.xml, build.gradle, Package.swift and
  .csproj. The names of all their dependencies are kept too, so that a later rule can read them
  again; no other part of a package file is kept (it can name its authors);
* **features:** the Hedera services that the source code calls, by the names of the classes of
  Hedera's SDKs, which are the same in every language (TopicCreateTransaction and the like);
* **imports:** the source files that import a Hedera library;
* **signs:** Hedera's JSON-RPC relay (Hashio) or its chain IDs in the code or the settings of an
  EVM project, a Hedera network taken from an EVM tool (viem, wagmi, thirdweb, or a network of
  Hardhat or Foundry named after Hedera), Hedera's system contracts in Solidity, and the mirror
  node read by the code;
* **mentions:** the files that name Hedera, Hashgraph or Hiero at all, in code, settings or
  comments. The weakest sign, kept so that a person sees where to look when nothing else was
  found.

It says what the code names. It does not run the code, and it cannot tell whether a line is ever
executed. Folders of other people's code (node_modules, vendor) and generated files are left
out: they are not the project's own code. Files named .env are never opened: they may hold
secrets.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import tarfile
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

FORMAT = 2  # 2 (21 October 2026): the Hedera networks of EVM tools, and the mentions
EXAMPLES = 10  # the files kept as examples for each thing found; the count is always complete
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
    features: dict[str, Seen] = field(default_factory=dict)
    signs: dict[str, Seen] = field(default_factory=dict)
    imports: Seen = field(default_factory=Seen)
    mentions: Seen = field(default_factory=Seen)  # files that name Hedera at all

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
            "signs": seen(self.signs),
            "imports": {"files": self.imports.files, "examples": self.imports.examples},
            "mentions": {"files": self.mentions.files, "examples": self.mentions.examples},
        }  # fmt: skip
        return json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")

    @classmethod
    def from_json(cls, body: bytes) -> CodeScan:
        record = json.loads(body.decode("utf-8"))

        def seen(found: dict) -> dict[str, Seen]:
            return {name: Seen(one["files"], list(one["examples"])) for name, one in found.items()}

        imports = record.get("imports") or {}
        mentions = record.get("mentions") or {}
        return cls(
            format=record.get("format", 1), files=record["files"], commit=record.get("commit"),
            archive_bytes=record["archive_bytes"],
            archive_sha256=record.get("archive_sha256", ""), partial=record.get("partial"),
            packages=record.get("packages") or {}, dependencies=record.get("dependencies") or {},
            unreadable=record.get("unreadable") or [], features=seen(record.get("features") or {}),
            signs=seen(record.get("signs") or {}),
            imports=Seen(imports.get("files", 0), list(imports.get("examples", []))),
            mentions=Seen(mentions.get("files", 0), list(mentions.get("examples", []))),
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


def read_file(scan: CodeScan, path: str, data: bytes, calls: list[_Calls]) -> None:
    """What one file of the project's code says about Hedera. The classes that it names are
    kept in `calls` and counted at the end (finish), because a class name such as
    TransferTransaction counts only in a file that imports a Hedera library, or in a
    repository whose package files name one."""
    name = PurePosixPath(path).name
    text = data.decode("utf-8", errors="ignore")
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


def finish(scan: CodeScan, calls: list[_Calls]) -> None:
    """Count the Hedera classes that the files name, now that the package files are known."""
    for one in calls:
        if one.imports_hedera or scan.packages:
            for feature in one.features:
                scan.features.setdefault(feature, Seen()).add(one.path)


def scan_archive(stream: LimitedStream) -> CodeScan:
    """Read a .tar.gz archive of a repository, file after file, and keep what it says about
    Hedera. Stops early at the limit of the stream, and says so in `partial`."""
    scan = CodeScan()
    calls: list[_Calls] = []
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
                read_file(scan, path, handle.read(), calls)
    except ReadLimit as limit:
        scan.partial = LIMIT_BYTES if str(limit) == "bytes" else LIMIT_SECONDS
    except DownloadBroken:
        scan.partial = BROKE_OFF
    except (tarfile.TarError, EOFError, OSError):
        scan.partial = UNREADABLE
    finish(scan, calls)
    scan.archive_bytes = stream.bytes
    scan.archive_sha256 = stream.digest.hexdigest()
    return scan
