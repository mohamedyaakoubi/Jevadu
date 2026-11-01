"""The step `mainnet_what`: what each transaction of the own IDs on Hedera's main network did, and
what the accounts that made those IDs also made there (design 7.6, 1 November 2026).

It runs after the step `mainnet`, which reads what each transaction cost; the step `refresh` runs
both. For each own ID with transactions that are not explained yet:
- a topic: its messages, each read as check/mainnet_what.message_of says;
- a contract: its calls, each named by its function, from the Solidity files of the project's
  repository on GitHub and from a common library;
- a scheduled transaction: what it holds, and the moment that it ran;
- an account, a token or a transaction: each transaction, for the tokens that it moved.
Then each account that made an own ID, and each own account itself, is followed: the tokens,
topics, contracts and schedules that it made on the main network from 30 days before the project's
event on, through its own transactions and the contracts that its EVM address deployed. An account
that made more than MAX_ACCOUNTS accounts in that time is a service that makes accounts for many
people (design 8.4), so it is not followed.

Everything comes from the mirror node, a public API asked one request at a time with a pause, and
from GitHub's API (allowed on 10 October 2026). An error of the node leaves that ID for the next
run; five errors in a row stop the step, because then the node is away (design rule 10).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime

from hackathon_memory.check.history import MAX_EVENTS
from hackathon_memory.check.mainnet_what import (
    SCHEDULE_RAN,
    Thing,
    call_of,
    functions_of,
    long_zero,
    message_of,
    names_from,
    scheduled_of,
    token_words,
    transfer_what,
)
from hackathon_memory.check.makers import ask_maker, payer_of
from hackathon_memory.collect.github import solidity_files
from hackathon_memory.collect.polite import PoliteClient
from hackathon_memory.db.mainnet import MainnetStore, OwnThing
from hackathon_memory.db.runs import Run
from hackathon_memory.hedera.mirror import MirrorError, MirrorNode, decode_message, when
from hackathon_memory.parse.hedera_ids import ACCOUNT, CONTRACT, SCHEDULE, TOKEN, TOPIC
from hackathon_memory.pipeline.check_ids import NodeIsAway

STEP = "mainnet_what"
MAX_ERRORS_IN_A_ROW = 5
MAX_ACCOUNTS = 50  # an account that made more accounts in the time is a service (design 8.4)
MAX_HOLDERS = 100
MAX_SOURCES = 12  # the Solidity files read from one repository
FIRST = {SCHEDULE: 0, CONTRACT: 1, TOPIC: 2, TOKEN: 3}  # a schedule names the moment that it ran
MAKES = {"TOKENCREATION": TOKEN, "CONSENSUSCREATETOPIC": TOPIC,
         "CONTRACTCREATEINSTANCE": CONTRACT, "SCHEDULECREATE": SCHEDULE}  # fmt: skip

# The Solidity files of a repository, by its address: (path, text). It may fail as GitHub fails.
CodeOf = Callable[[str], list[tuple[str, str]]]


def _now() -> datetime:
    return datetime.now(UTC)


def solidity_of(client: PoliteClient | None) -> CodeOf | None:
    """The reader of a repository's Solidity files through GitHub's API; None without a client."""
    if client is None:
        return None
    return lambda repository: solidity_files(client, repository, limit=MAX_SOURCES)


class _Errors:
    """The errors of the node in a row: five stop the step."""

    def __init__(self, run: Run) -> None:
        self.run, self.in_a_row = run, 0

    def failed(self, what: str, error: MirrorError) -> None:
        self.run.counts["errors_of_the_node"] += 1
        self.run.problem(what, str(error))
        self.in_a_row += 1
        if self.in_a_row >= MAX_ERRORS_IN_A_ROW:
            raise NodeIsAway(f"the mirror node failed {self.in_a_row} times in a row") from None

    def clear(self) -> None:
        self.in_a_row = 0


def explain_mainnet(
    store: MainnetStore,
    mirrors: Mapping[str, MirrorNode],
    code_of: CodeOf | None,
    run: Run,
    *,
    now: Callable[[], datetime] = _now,
    projects: set[int] | None = None,
) -> None:
    """Explain the transactions of the own IDs on the main network that are not explained yet,
    and follow the accounts that made them; with `projects`, of these projects only."""
    mirror = mirrors.get("mainnet")
    if mirror is None:
        return
    things = sorted(store.own_things(projects=projects), key=lambda one: FIRST.get(one.kind, 9))
    makers = store.makers()
    errors = _Errors(run)
    followed: dict[str, datetime] = {}
    for one in things:
        try:
            maker = _explain(store, mirror, code_of, one, makers, run, now)
        except MirrorError as error:
            errors.failed(f"the {one.kind} {one.entity_id} on the main network", error)
            continue
        errors.clear()
        if one.since is not None:
            for account in (maker, one.ledger_id if one.kind == ACCOUNT else None):
                if account:
                    followed[account] = min(followed.get(account, one.since), one.since)
    own = {one.ledger_id for one in things}
    for account, since in sorted(followed.items()):
        try:
            _follow(store, mirror, account, since, own, run, now)
        except MirrorError as error:
            errors.failed(f"what {account} made on the main network", error)
            continue
        errors.clear()


def _explain(
    store: MainnetStore,
    mirror: MirrorNode,
    code_of: CodeOf | None,
    one: OwnThing,
    makers: Mapping[str, str | None],
    run: Run,
    now: Callable[[], datetime],
) -> str | None:
    """Explain the moments of one own ID, and keep it as a thing when it is new or changed.
    Returns the account that made it."""
    todo = set(one.todo)
    if one.kind == SCHEDULE:
        scheduled = scheduled_of(mirror.schedule(one.ledger_id) or {})
        if scheduled.executed:  # the moment that it ran may stand in an account's history
            store.explain(scheduled.executed, SCHEDULE_RAN, (), now())
        _explained(store, todo - {scheduled.executed}, run, now)
        store.save_thing(Thing(one.ledger_id, SCHEDULE, one.made_at, one.made_by,
                               name=scheduled.memo, scheduled=scheduled.what,
                               executed=scheduled.executed), now())  # fmt: skip
        return one.made_by
    if one.kind == TOPIC and (todo or one.ledger_id not in makers):
        messages, _cut = mirror.topic_history(one.ledger_id, max_rows=MAX_EVENTS)
        read = {str(message.get("consensus_timestamp")): message_of(decode_message(message))
                for message in messages}  # fmt: skip
        for stamp in sorted(todo):
            said = read.get(stamp)
            store.explain(stamp, said.what if said else None, said.networks if said else (), now())
        run.counts["mainnet_explained"] += len(todo)
        fields = Counter(said.fields for said in read.values() if said.fields).most_common(1)
        newest = mirror.topic_messages(one.ledger_id, newest_first=True)
        store.save_thing(Thing(one.ledger_id, TOPIC, one.made_at, one.made_by,
                               name=_memo(mirror.topic(one.ledger_id)),
                               fields=fields[0][0] if fields else (),
                               messages=_sequence(newest, len(messages))), now())  # fmt: skip
        return one.made_by
    if one.kind == CONTRACT and (todo or one.ledger_id not in makers):
        results, _cut = mirror.contract_history(one.ledger_id, max_rows=MAX_EVENTS)
        functions = functions_of(_sources(code_of, one.repository, run) if todo else ())
        ids, called = {one.ledger_id, one.entity_id}, set()
        for result in results:
            stamp = str(result.get("timestamp") or "")
            if stamp in todo:
                store.explain(stamp, call_of(result, ids, functions), (), now())
                called.add(str(result.get("function_parameters") or "")[:10].lower())
                todo.discard(stamp)
                run.counts["mainnet_explained"] += 1
        _explained(store, todo, run, now)
        store.save_thing(Thing(one.ledger_id, CONTRACT, one.made_at, one.made_by,
                               name=_memo(mirror.contract(one.ledger_id)),
                               names_from=names_from(functions, called)), now())  # fmt: skip
        return one.made_by
    if one.kind in (TOPIC, CONTRACT):
        return makers.get(one.ledger_id) or one.made_by
    symbols: dict[str, str] = {}
    for stamp in sorted(todo):
        transaction = mirror.transaction_at(stamp) or {}
        for token_id in _tokens_of(transaction):
            if token_id not in symbols:
                token = mirror.token(token_id) or {}
                symbols[token_id] = str(token.get("symbol") or "") or token_id
        store.explain(stamp, transfer_what(transaction, symbols), (), now())
        run.counts["mainnet_explained"] += 1
    if one.kind == TOKEN:
        store.save_thing(_token(mirror, one.ledger_id, one.made_at, one.made_by), now())
        return one.made_by
    if one.kind == ACCOUNT:
        known = makers.get(one.ledger_id)  # a mark of _follow alone names no maker
        if known:
            return known
        maker = one.made_by or (ask_maker(mirror, one.ledger_id, one.made_at)
                                if one.made_at else None)  # fmt: skip
        store.save_thing(Thing(one.ledger_id, ACCOUNT, one.made_at, maker), now())
        return maker
    return one.made_by


def _follow(
    store: MainnetStore,
    mirror: MirrorNode,
    account: str,
    since: datetime,
    own: set[str],
    run: Run,
    now: Callable[[], datetime],
) -> None:
    """Keep the things that an account made on the main network from `since` on, besides the own
    IDs: through its own transactions, and the contracts that its EVM addresses deployed."""
    rows, _cut = mirror.account_history(account, max_rows=MAX_EVENTS, since=since)
    paid = [row for row in rows if row.get("result") == "SUCCESS"
            and payer_of(str(row.get("transaction_id") or "")) == account]  # fmt: skip
    if sum(row.get("name") == "CRYPTOCREATEACCOUNT" for row in paid) > MAX_ACCOUNTS:
        run.counts["mainnet_services_not_followed"] += 1
        store.mark_followed(account, "service", now())
        return
    made: dict[str, tuple[str, str]] = {}  # entity -> (kind, moment)
    for row in paid:
        kind, entity = MAKES.get(str(row.get("name"))), str(row.get("entity_id") or "")
        if kind and entity:
            made.setdefault(entity, (kind, str(row.get("consensus_timestamp"))))
    about = mirror.account(account) or {}
    for address in sorted({long_zero(account), str(about.get("evm_address") or "").lower()}
                          - {None, ""}):  # fmt: skip
        results, _cut = mirror.results_from(str(address), since=since, max_rows=MAX_EVENTS)
        for result in results:
            for entity in result.get("created_contract_ids") or ():
                made.setdefault(str(entity), (CONTRACT, str(result.get("timestamp"))))
    for entity, (kind, stamp) in sorted(made.items(), key=lambda item: item[1][1]):
        if entity in own:
            continue
        store.save_thing(_made(mirror, entity, kind, when(stamp), account), now())
        run.counts["mainnet_things_followed"] += 1
    store.mark_followed(account, "read", now())


def _made(mirror: MirrorNode, entity: str, kind: str, made_at: datetime, maker: str) -> Thing:
    """A thing that an account made, read: a contract is not asked about, since a factory can
    make hundreds in a day (MemeWarp's made 165, 27 and 28 September 2025)."""
    if kind == CONTRACT:
        return Thing(entity, CONTRACT, made_at, maker)
    if kind == TOKEN:
        return _token(mirror, entity, made_at, maker)
    if kind == TOPIC:
        newest = mirror.topic_messages(entity, newest_first=True)
        return Thing(entity, TOPIC, made_at, maker, name=_memo(mirror.topic(entity)),
                     messages=_sequence(newest, 0))  # fmt: skip
    if kind == SCHEDULE:
        scheduled = scheduled_of(mirror.schedule(entity) or {})
        return Thing(entity, SCHEDULE, made_at, maker, name=scheduled.memo,
                     scheduled=scheduled.what, executed=scheduled.executed)  # fmt: skip
    raise AssertionError(f"not a kind that is made once: {kind}")


def _token(mirror: MirrorNode, entity: str, made_at: datetime | None, maker: str | None) -> Thing:
    token = mirror.token(entity) or {}
    holders, _more = mirror.token_holders(entity, max_rows=MAX_HOLDERS)
    treasury = str(token.get("treasury_account_id") or "")
    return Thing(entity, TOKEN, made_at, maker, name=token_words(token),
                 held_by_others=len(set(holders) - {treasury}))  # fmt: skip


def _explained(store: MainnetStore, stamps: Iterable[str], run: Run,
               now: Callable[[], datetime]) -> None:  # fmt: skip
    """Moments whose kind says it all, such as the creation of a schedule."""
    for stamp in sorted(stamps):
        store.explain(stamp, None, (), now())
        run.counts["mainnet_explained"] += 1


def _sources(code_of: CodeOf | None, repository: str | None, run: Run) -> list[tuple[str, str]]:
    """The Solidity files of a repository, or none when GitHub cannot be asked."""
    if code_of is None or not repository:
        return []
    try:
        return code_of(repository)
    except Exception as error:  # noqa: BLE001 (GitHub's own rules stop it; the library still names)
        run.problem(f"the Solidity files of {repository}", str(error)[:200])
        return []


def _tokens_of(transaction: Mapping) -> list[str]:
    found = [str(one.get("token_id")) for one in transaction.get("token_transfers") or ()]
    found += [str(one.get("token_id")) for one in transaction.get("nft_transfers") or ()]
    return sorted({one for one in found if one and one != "None"})


def _memo(answer: Mapping | None) -> str | None:
    return str((answer or {}).get("memo") or "").strip()[:120] or None


def _sequence(newest: list[dict], fallback: int) -> int:
    """The messages of a topic so far: the number of its newest message."""
    return int(newest[0].get("sequence_number") or fallback) if newest else fallback


def mainnet_what_lines(run: Run) -> list[str]:
    """What a run of the step did, in plain words."""
    counts = run.counts
    lines = [f"Transactions on the main network explained: {counts['mainnet_explained']:,}."]
    if counts["mainnet_things_followed"]:
        lines.append("Things that the same accounts made there, read: "
                     f"{counts['mainnet_things_followed']:,}.")  # fmt: skip
    if counts["mainnet_services_not_followed"]:
        lines.append(f"Accounts not followed, because they made more than {MAX_ACCOUNTS} "
                     f"accounts: {counts['mainnet_services_not_followed']}.")  # fmt: skip
    if counts["errors_of_the_node"]:
        lines.append(f"Not read, because the mirror node failed: {counts['errors_of_the_node']}.")
    return lines
