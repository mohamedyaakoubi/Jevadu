"""Where Hedera stands in the code of a repository (parse/hedera_code.py). Every archive here is
invented and built in memory."""

from __future__ import annotations

import io
import json
import random

from fakes import ARCHIVE_COMMIT, archive
from hackathon_memory.parse import hedera_code as hc
from hackathon_memory.parse.hedera_code import (
    CHAIN_ID,
    EVM_NETWORK,
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
        "src/main.ts": b'import "./topic";\nimport { pay } from "./pay";\n',  # both are used
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
    assert scan.files == 9  # neither node_modules, nor dist, nor .env, nor the huge file
    assert scan.commit == ARCHIVE_COMMIT
    assert scan.uses_hedera and scan.archive_bytes > 0 and len(scan.archive_sha256) == 64
    record = scan.to_json().decode()
    assert "Quill" not in record and "PRIVATE_KEY" not in record and "not-a-key" not in record


def test_an_archive_with_no_commit_in_its_header_names_none() -> None:
    body = archive({"src/a.ts": b"let a = 1;\n"}, commit=None)
    assert scan_archive(LimitedStream(io.BytesIO(body).read)).commit is None
    odd = archive({"src/a.ts": b"let a = 1;\n"}, commit="not a commit")
    assert scan_archive(LimitedStream(io.BytesIO(odd).read)).commit is None


def test_what_was_found_is_listed_kind_after_kind() -> None:
    files = {
        f"app{n}/package.json": b'{"dependencies": {"@hashgraph/sdk": "2"}}' for n in range(12)
    }
    files["src/topic.py"] = b"from hiero_sdk_python import TopicCreateTransaction\n"
    files["main.py"] = b"import src.topic\n"  # the file is used
    found = scanned(files).found()
    assert [(one.kind, one.name, one.files) for one in found] == [
        (hc.PACKAGE, "@hashgraph/sdk", 12),
        (hc.FEATURE, "Consensus Service (topics)", 1),
        (hc.IMPORT, hc.IMPORT_NAME, 1),
        (hc.MENTION, hc.MENTION_NAME, 13),
    ]
    assert len(found[0].examples) == hc.EXAMPLES  # the count is whole, the examples are not
    assert found[2].examples == ("src/topic.py",)


def test_a_hedera_network_taken_from_an_evm_tool_is_a_sign() -> None:
    scan = scanned({
        "src/wagmi.ts": b'import {\n  mainnet,\n  hederaTestnet,\n} from "viem/chains";\n',
        "src/third.ts": b"export const chain = defineChain(296);\n",
        "hardhat.config.js": b"networks: { hedera_testnet: { url: process.env.RPC_URL } }\n",
        "foundry.toml": b'[rpc_endpoints]\nhedera-testnet = "https://rpc.example.test"\n',
        "src/plain.ts": b'import { mainnet } from "viem/chains";\nconst hedera = { a: 1 };\n',
        "config/app.json": b'{"chainId": "0x128"}',
    })  # fmt: skip
    assert sorted(scan.signs[EVM_NETWORK].examples) == [
        "foundry.toml", "hardhat.config.js", "src/third.ts", "src/wagmi.ts"]  # fmt: skip
    assert scan.signs[CHAIN_ID].examples == ["config/app.json"]
    assert scan.uses_hedera and scan.packages == {} and scan.imports.files == 0


def test_a_mention_is_the_weakest_sign_and_shows_where_to_look() -> None:
    scan = scanned({
        "src/app.tsx": b"<p>Built on Hedera</p>",
        "src/tools.ts": b"// the tools of hiero-ledger",
        "src/glyph.ts": b"const hieroglyph = 1;",
        "README.md": b"Hedera, Hedera, Hedera",
    })  # fmt: skip
    assert sorted(scan.mentions.examples) == ["src/app.tsx", "src/tools.ts"]
    assert not scan.uses_hedera  # a mention is not a use
    assert [one.kind for one in scan.found()] == [hc.MENTION]
    assert CodeScan.from_json(scan.to_json()) == scan


def test_a_class_name_counts_only_with_a_hedera_library() -> None:
    plain = scanned({"package.json": b'{"dependencies": {"ethers": "6"}}',
                     "src/pay.ts": b"class TransferTransaction {}"})  # fmt: skip
    assert plain.features == {} and not plain.uses_hedera
    imported = scanned({"pay.py": b"from hiero_sdk_python import TransferTransaction\n"})
    assert imported.features["Accounts and HBAR transfers"].files == 1
    assert imported.imports.files == 1


SDK = b"const sdk = require('@hashgraph/sdk');\n"


def test_a_service_in_a_file_that_nothing_uses_is_kept_apart() -> None:
    """A wrapper that no file imports, and that starts no program, is code written and never
    reached: its services are not called (8 November 2026, a submission whose check listed the
    Token and File Services from two such files)."""
    files = {
        "package.json": json.dumps({"dependencies": {"@hashgraph/sdk": "2"},
                                    "scripts": {"start": "node server.js"}}).encode(),
        "server.js": b"const app = require('./app');\napp.listen(3000);\n",
        "app.js": b"const api = require('./src/routes/api');\n",
        "src/routes/api.js": b"const { anchor } = require('../agents/trustAgent');\n",
        "src/agents/trustAgent.js": b"function a() { return require('../services/hcsService'); }",
        # Each exports what it does, as the submission's files do: a module that waits for an
        # import, and not a script.
        "src/services/hcsService.js": SDK + b"exports.send = () =>\n"
        b"  new TopicMessageSubmitTransaction();\n",
        "src/services/htsService.js": SDK + b"exports.mint = () => new TokenCreateTransaction();\n",
        "src/services/hfsService.js": SDK + b"module.exports = () => new FileCreateTransaction();",
    }  # fmt: skip
    scan = scanned(files)
    assert {name: one.examples for name, one in scan.features.items()} == {
        "Consensus Service (topics)": ["src/services/hcsService.js"]}  # fmt: skip
    assert {name: one.examples for name, one in scan.unused_only.items()} == {
        "File Service": ["src/services/hfsService.js"],
        "Token Service": ["src/services/htsService.js"],
    }
    assert [one.name for one in scan.found() if one.kind == hc.FEATURE] == [
        "Consensus Service (topics)"]  # fmt: skip
    again = CodeScan.from_json(scan.to_json())
    assert again.unused_only.keys() == scan.unused_only.keys() and again.format == hc.FORMAT


def test_a_file_is_used_when_a_program_starts_there_or_any_file_imports_it() -> None:
    """When it is not sure, a file counts as used: the usual folders and names of a framework,
    a file that package.json names, a Python file with a __main__ block, an import by an alias or
    by the end of its path, and any language that is not read this way."""
    # Each file exports, so that only the sign under test makes it used.
    sdk = b"import { TokenMintTransaction } from '@hashgraph/sdk';\nexport const mint = 1;\n"
    files = {
        "package.json": json.dumps({"dependencies": {"@hashgraph/sdk": "2"},
                                    "scripts": {"mint": "node tools/mint.js"}}).encode(),
        "web/pages/api/mint.ts": sdk,  # a route of Next.js
        "web/src/app/page.tsx": b"import { mint } from '@/lib/hedera';\n",
        "web/src/lib/hedera.ts": sdk,  # by an alias
        "web/src/utils/pay.ts": sdk,
        "web/src/components/Pay.tsx": b"import { pay } from 'utils/pay';\n",  # by its path's end
        "tools/mint.js": sdk,  # named by package.json
        "backend/services/topic.py": b"from hiero_sdk_python import TopicCreateTransaction\n"
        b"def send():\n    return TopicCreateTransaction()\n",
        "backend/api.py": b"from services.topic import send\n",
        "backend/jobs/make_topic.py": b"from hiero_sdk_python import TopicCreateTransaction\n"
        b"if __name__ == '__main__':\n    main()\n",
        "go/topic.go": b'import "github.com/hiero-ledger/x"\nNewTopicCreateTransaction()',
        "web/src/lib/self.ts": sdk + b"import './self';\n",  # only itself: nothing uses it
    }  # fmt: skip
    scan = scanned(files)
    assert sorted(scan.features["Token Service"].examples) == [
        "tools/mint.js",
        "web/pages/api/mint.ts",
        "web/src/lib/hedera.ts",
        "web/src/utils/pay.ts",
    ]
    assert sorted(scan.features["Consensus Service (topics)"].examples) == [
        "backend/jobs/make_topic.py",
        "backend/services/topic.py",
        "go/topic.go",
    ]
    assert scan.unused["Token Service"].examples == ["web/src/lib/self.ts"]
    assert scan.unused_only == {}  # a service that a used file names is called


def test_the_files_that_the_first_rule_took_for_unused_are_used() -> None:
    """Each kind of file that the first rule took for unused in 80 repositories of the collection
    (evals/results/20261108T000912Z-code-reach.json): an import of a name with a dot in it, an
    import of Python in brackets over several lines, a package's __init__.py, and scripts that
    export nothing. And two more ways to reach a file: a workflow names it, a notebook imports
    it."""
    sdk = b"import { TokenCreateTransaction } from '@hashgraph/sdk';\nexport const make = 1;\n"
    py = b"from hiero_sdk_python import TokenCreateTransaction\ndef make():\n    return 1\n"
    notebook = {"cells": [{"cell_type": "markdown", "source": "from nowhere import x"},
                          {"cell_type": "code", "source": ["from helpers.hedera_utils import (\n",
                                                           "    make,\n", ")\n"]}]}  # fmt: skip
    files = {
        "package.json": json.dumps({"dependencies": {"@hashgraph/sdk": "2"}}).encode(),
        "backend/src/services/hedera.service.ts": sdk,
        "backend/src/jobs/mint.ts": b"import { make } from '../services/hedera.service';\n",
        "offchain/create-topic.ts": b"import { TokenCreateTransaction } from '@hashgraph/sdk';\n"
        b"await new TokenCreateTransaction().execute(client);\n",  # a script: it exports nothing
        "agent/hedera/tokens/create.py": py,
        "agent/flow.py": b"from agent.hedera.tokens.create import (\n    make,  # the token\n)\n"
        b"def run():\n    make()\n",
        "agent/hedera/__init__.py": py,
        "agent/setup_token.py": py + b"make()\n",  # a Python script: a call at its top level
        "tools/check/hedera.ts": sdk,
        ".github/workflows/ci.yml": b"steps:\n  - run: npx tsx tools/check/hedera.ts\n",
        "lab/helpers/hedera_utils.py": py,
        "lab/explore.ipynb": json.dumps(notebook).encode(),
        "web/src/lib/dead.ts": sdk,  # it exports, and nothing imports it
    }  # fmt: skip
    scan = scanned(files)
    assert sorted(scan.features["Token Service"].examples) == [
        "agent/hedera/__init__.py",
        "agent/hedera/tokens/create.py",
        "agent/setup_token.py",
        "backend/src/services/hedera.service.ts",
        "lab/helpers/hedera_utils.py",
        "offchain/create-topic.ts",
        "tools/check/hedera.ts",
    ]
    assert scan.unused["Token Service"].examples == ["web/src/lib/dead.ts"]


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


def test_a_reading_that_stopped_early_counts_every_file_as_used() -> None:
    noise = random.Random(7)  # noqa: S311 - random bytes do not compress: a large archive
    files = {"src/lib/token.ts": b'import { TokenCreateTransaction } from "@hashgraph/sdk";\n'}
    files |= {f"src/f{n}.ts": noise.randbytes(50_000) for n in range(20)}
    # The first chunk holds the whole first file; the files that were never read could import it.
    scan = scanned(files, max_bytes=70_000)
    assert scan.partial == "the archive is larger than the limit of a live check"
    assert scan.features["Token Service"].examples == ["src/lib/token.ts"]
    assert scan.unused == {}


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


# --------------------------------------------------------------------------- the IDs


def test_the_ids_of_the_code_are_kept_with_their_files_and_never_their_words() -> None:
    scan = scanned({
        ".env.example": b"OPERATOR_ID=0.0.4870201\nOPERATOR_KEY=invented-placeholder\n",
        "src/topic.ts": b'const topic = "0.0.4870201";\n',
        "src/links.ts": b"// https://hashscan.io/testnet/topic/0.0.4870202\n",
        "package.json": b'{"name": "x", "version": "0.0.3"}',  # a version, never an ID
        "node_modules/x/index.js": b'const token = "0.0.5551000";',  # other people's code
        ".env": b"OPERATOR_ID=0.0.4870209\n",  # never opened
    })  # fmt: skip
    assert {key: one.seen.files for key, one in scan.ids.items()} == {
        ("0.0.4870201", None): 2, ("0.0.4870202", "testnet"): 1}  # fmt: skip
    assert scan.ids[("0.0.4870201", None)].seen.examples == [".env.example", "src/topic.ts"]
    record = scan.to_json().decode()
    assert "placeholder" not in record and "OPERATOR" not in record  # no words around an ID
    assert CodeScan.from_json(scan.to_json()) == scan and not scan.ids_cut


def test_a_repository_that_names_too_many_ids_keeps_the_first_ones(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(hc, "MOST_IDS", 2)
    scan = scanned({"tokens.json": b'["0.0.4870301", "0.0.4870302", "0.0.4870303"]'})
    assert [key[0] for key in scan.ids] == ["0.0.4870301", "0.0.4870302"] and scan.ids_cut
    assert CodeScan.from_json(scan.to_json()).ids_cut
