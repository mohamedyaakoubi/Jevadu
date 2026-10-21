"""Where Hedera stands in the code of a repository (parse/hedera_code.py). Every archive here is
invented and built in memory."""

from __future__ import annotations

import io
import json
import random

from fakes import archive
from hackathon_memory.parse import hedera_code as hc
from hackathon_memory.parse.hedera_code import (
    CHAIN_ID,
    MIRROR_NODE,
    RELAY,
    SYSTEM_CONTRACTS,
    CodeScan,
    LimitedStream,
    is_hedera_package,
    scan_archive,
)


def scanned(files: dict[str, bytes], **limits: object) -> CodeScan:
    body = archive(files)
    return scan_archive(LimitedStream(io.BytesIO(body).read, **limits))  # type: ignore[arg-type]


# --------------------------------------------------------------------------- the packages


def test_the_hedera_packages_of_each_ecosystem() -> None:
    yes = [("npm", "@hashgraph/sdk"), ("npm", "@hashgraph/hedera-wallet-connect"),
           ("npm", "hashconnect"), ("npm", "hedera-agent-kit"), ("npm", "@hiero-ledger/sdk"),
           ("npm", "@hashgraphonline/standards-sdk"), ("pypi", "hiero-sdk-python"),
           ("pypi", "Hiero_SDK_Python"), ("pypi", "hedera-agent-kit"),
           ("go", "github.com/hiero-ledger/hiero-sdk-go/v2"),
           ("go", "github.com/hashgraph/hedera-sdk-go/v2"), ("cargo", "hedera"),
           ("maven", "com.hedera.hashgraph:sdk"), ("maven", "org.hiero:hiero-enterprise"),
           ("swift", "github.com/hiero-ledger/hiero-sdk-swift"),
           ("nuget", "Hashgraph")]  # fmt: skip
    no = [("npm", "ethers"), ("npm", "hedera"), ("npm", "@hashgraphx/sdk"), ("pypi", "web3"),
          ("go", "github.com/ethereum/go-ethereum"), ("cargo", "hedera-like"),
          ("maven", "org.web3j:core"), ("nuget", "Nethereum.Web3")]  # fmt: skip
    assert all(is_hedera_package(*one) for one in yes)
    assert not any(is_hedera_package(*one) for one in no)


def test_each_kind_of_package_file_gives_its_dependencies() -> None:
    assert hc.package_json(json.dumps({
        "name": "app", "author": "Quill Invented <quill@example.test>",
        "dependencies": {"@hashgraph/sdk": "^2.50.0"}, "devDependencies": {"vitest": "1"},
    })) == ["@hashgraph/sdk", "vitest"]  # fmt: skip
    assert hc.requirements(
        "# the tools\nhiero-sdk-python>=0.1  # the SDK\nrequests[socks]==2.0\n"
        "-r more.txt\n-e git+https://example.test/x.git#egg=hedera-agent-kit\n"
    ) == ["hiero-sdk-python", "requests", "hedera-agent-kit"]
    assert hc.pyproject(
        '[project]\ndependencies = ["hiero-sdk-python>=0.1", "fastapi"]\n'
        '[project.optional-dependencies]\ndev = ["pytest"]\n'
        '[tool.poetry.dependencies]\npython = "^3.11"\nhttpx = "*"\n'
    ) == ["hiero-sdk-python", "fastapi", "pytest", "httpx"]
    assert hc.pipfile('[packages]\nhiero-sdk-python = "*"\n[dev-packages]\nruff = "*"\n') == [
        "hiero-sdk-python", "ruff"]  # fmt: skip
    assert hc.go_mod(
        "module example.test/app\n\ngo 1.22\n\nrequire (\n"
        "\tgithub.com/hiero-ledger/hiero-sdk-go/v2 v2.60.0\n"
        "\tgithub.com/pkg/errors v0.9.1 // why\n)\n"
        "require golang.org/x/net v0.20.0\n"
    ) == ["github.com/hiero-ledger/hiero-sdk-go/v2", "github.com/pkg/errors", "golang.org/x/net"]
    assert hc.cargo_toml('[dependencies]\nhedera = "0.34"\ntokio = { version = "1" }\n') == [
        "hedera", "tokio"]  # fmt: skip
    assert hc.pom_xml(
        "<dependency><groupId>com.hedera.hashgraph</groupId>\n<artifactId>sdk</artifactId>"
        "</dependency>"
    ) == ["com.hedera.hashgraph:sdk"]
    assert hc.gradle('implementation "com.hedera.hashgraph:sdk:2.77.0"') == [
        "com.hedera.hashgraph:sdk"]  # fmt: skip
    assert hc.package_swift(
        '.package(url: "https://github.com/hiero-ledger/hiero-sdk-swift.git", from: "0.30.0")'
    ) == ["github.com/hiero-ledger/hiero-sdk-swift"]
    assert hc.csproj('<PackageReference Include="Hashgraph" Version="10.0.0" />') == ["Hashgraph"]


# --------------------------------------------------------------------------- a whole archive


def test_an_archive_says_where_hedera_stands_and_skips_what_is_not_the_projects() -> None:
    files = {
        "package.json": json.dumps(
            {"dependencies": {"@hashgraph/sdk": "^2", "react": "18"}, "author": "Quill Invented"}
        ).encode(),  # fmt: skip
        "node_modules/hashconnect/package.json": b'{"dependencies": {"hashconnect": "1"}}',
        "src/topic.ts": b'import { Client, TopicCreateTransaction } from "@hashgraph/sdk";\n'
        b"await new TopicCreateTransaction().execute(client);\n",
        "src/pay.ts": b"const tx = new TransferTransaction();\n",  # no import: the package counts
        "hardhat.config.ts": b'networks: { hedera: { url: "https://testnet.hashio.io/api", '
        b"chainId: 296 } }",
        "contracts/IHederaTokenService.sol": b"interface IHederaTokenService {}\n",
        "contracts/Token.sol": b'import "./IHederaTokenService.sol";\n'
        b"address constant HTS = address(0x167);\n",
        "scripts/mirror.py": b'URL = "https://testnet.mirrornode.hedera.com/api/v1/accounts/0.0.5"',
        ".env": b"PRIVATE_KEY=302e not-a-key\nRPC=https://testnet.hashio.io/api\n",
        ".env.example": b"MIRROR=https://testnet.mirrornode.hedera.com\n",
        "dist/bundle.js": b"new TokenCreateTransaction()",
        "src/huge.ts": b"// " + b"x" * (hc.MAX_FILE_BYTES + 1),
        "README.md": b"We use TokenCreateTransaction.",
    }
    scan = scanned(files)
    assert scan.partial is None
    assert scan.packages == {"@hashgraph/sdk": ["package.json"]}
    assert scan.dependencies == {"package.json": ["@hashgraph/sdk", "react"]}
    assert scan.imports.files == 1 and scan.imports.examples == ["src/topic.ts"]
    assert {name: one.examples for name, one in scan.features.items()} == {
        "Accounts and HBAR transfers": ["src/pay.ts"],
        "Consensus Service (topics)": ["src/topic.ts"],
    }
    assert scan.signs[RELAY].examples == ["hardhat.config.ts"]  # .env was never opened
    assert scan.signs[CHAIN_ID].examples == ["hardhat.config.ts"]
    assert scan.signs[SYSTEM_CONTRACTS].files == 2
    assert sorted(scan.signs[MIRROR_NODE].examples) == [".env.example", "scripts/mirror.py"]
    assert scan.files == 8  # neither node_modules, nor dist, nor .env, nor the huge file
    assert scan.uses_hedera and scan.archive_bytes > 0 and len(scan.archive_sha256) == 64
    record = scan.to_json().decode()
    assert "Quill" not in record and "PRIVATE_KEY" not in record and "not-a-key" not in record


def test_a_class_name_counts_only_with_a_hedera_library() -> None:
    plain = scanned({"package.json": b'{"dependencies": {"ethers": "6"}}',
                     "src/pay.ts": b"class TransferTransaction {}"})  # fmt: skip
    assert plain.features == {} and not plain.uses_hedera
    imported = scanned({"src/pay.py": b"from hiero_sdk_python import TransferTransaction\n"})
    assert imported.features["Accounts and HBAR transfers"].files == 1
    assert imported.imports.files == 1


def test_a_go_file_names_its_classes_through_functions() -> None:
    scan = scanned({"main.go": b'import "github.com/hiero-ledger/hiero-sdk-go/v2/sdk"\n'
                               b"tx := hedera.NewTokenCreateTransaction()\n"})  # fmt: skip
    assert scan.features["Token Service"].files == 1 and scan.imports.files == 1


def test_a_record_reads_back_as_it_was_written() -> None:
    scan = scanned({"package.json": b'{"dependencies": {"hashconnect": "3"}}',
                    "src/a.ts": b'import { HashConnect } from "hashconnect";\n'})  # fmt: skip
    again = CodeScan.from_json(scan.to_json())
    assert again == scan


def test_a_limit_of_bytes_or_seconds_stops_the_reading_and_says_so() -> None:
    noise = random.Random(7)  # noqa: S311 - random bytes do not compress: a large archive
    files = {f"src/f{n}.ts": noise.randbytes(50_000) for n in range(20)}
    small = scanned(files, max_bytes=20_000)
    assert small.partial == "the archive is larger than the limit of a live check"
    moments = iter([0.0, 0.0, 99.0, 99.0, 99.0, 99.0])
    slow = scanned(files, seconds=10.0, clock=lambda: next(moments, 99.0))
    assert slow.partial == "the archive took longer than the limit of a live check"


def test_a_broken_archive_is_said_to_be_broken() -> None:
    body = archive({"package.json": b'{"dependencies": {"@hashgraph/sdk": "2"}}'})[:-40]
    scan = scan_archive(LimitedStream(io.BytesIO(body).read))
    assert scan.partial == "the archive could not be read to its end"


def test_an_unreadable_package_file_is_named_and_the_rest_goes_on() -> None:
    go_mod = b"require github.com/hashgraph/hedera-sdk-go/v2 v2.1.0\n"
    scan = scanned({"package.json": b"{ not json", "pyproject.toml": b"[project\n",
                    "go.mod": go_mod})  # fmt: skip
    assert sorted(scan.unreadable) == ["package.json", "pyproject.toml"]
    assert scan.packages == {"github.com/hashgraph/hedera-sdk-go/v2": ["go.mod"]}
