// Teams sign their own registration (design 9.6, 29 October 2026). The register's box holds a
// fieldset [data-sign] with the parts of the record. A button signs its text with a Hedera wallet
// such as HashPack (Hedera's WalletConnect library, hedera_signMessage) or with an EVM wallet such
// as MetaMask (EIP-1193, personal_sign), and the hidden fields carry the account, the way of
// signing, the signature and the commit to the server, which checks the signature against the
// account's key on the ledger before it writes. The buttons name the two kinds of wallet, not one
// wallet each, since WalletConnect lists every Hedera wallet that it supports (30 October 2026).
// The WalletConnect library is loaded only when a Hedera wallet is asked for, from a CDN, since
// the site has no build step (tried in a browser on 29 October 2026: about 5 seconds).
// A wallet stays connected after a refresh, as the wallets keep the connection: the box names the
// wallet and its account, signs with it in one click, and lets another wallet be chosen (30
// October 2026). This browser keeps only the kind of wallet connected last (hm-wallet in
// localStorage), to look for it again with no question to the person.

const WALLET_CONNECT = "https://esm.sh/@hashgraph/hedera-wallet-connect@2.1.3";
const HIERO_SDK = "https://esm.sh/@hiero-ledger/sdk@2.79.0";
const KIND = "hm-wallet";
const NO_ACCOUNT = "This address has no Hedera account on the test network yet. Make one with "
  + "the steps above, then click “Sign with this account”.";
const ENDED = "The wallet ended the connection. Choose a wallet again.";

let wallet = null; // the connected wallet: { kind: "hedera" or "evm", name, account, address }

// The same text as signed_text of hedera/signing.py: every part of it is in the record.
function signedText(box, account) {
  return [
    "Jevadu register",
    `Hackathon: ${box.dataset.event}`,
    `Repository fingerprint: ${box.dataset.code}`,
    `Commit: ${box.dataset.commit}`,
    `Account: ${account}`,
  ].join("\n");
}

// The line under the buttons says each step, and a problem or the end plainly, in a box that shows
// (30 October 2026: a problem in small grey words went unseen). An address in it is a link.
function say(box, words, state = "step") {
  const status = box.querySelector(".hm-sign-status");
  if (!status) return;
  status.dataset.state = state;
  status.replaceChildren();
  for (const part of words.split(/(https:\/\/\S*[^\s.,)])/)) {
    if (!part.startsWith("https://")) {
      status.append(part);
      continue;
    }
    const link = document.createElement("a");
    link.href = part;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = part.slice("https://".length);
    status.append(link);
  }
}

function quiet(box) {
  const status = box.querySelector(".hm-sign-status");
  if (!status) return;
  status.replaceChildren();
  delete status.dataset.state;
}

// A problem of the signing; one that `ends` the connection lets the wallet go.
function problem(words, ends = false) {
  return Object.assign(new Error(words), { ends });
}

function short(address) {
  return `${address.slice(0, 6)}…${address.slice(-4)}`;
}

function keep(box, signed) {
  box.querySelector('[name="signer"]').value = signed.account;
  box.querySelector('[name="scheme"]').value = signed.scheme;
  box.querySelector('[name="signature"]').value = signed.signature;
  box.querySelector('[name="signed_commit"]').value = box.dataset.commit;
}

function unsign(box) {
  keep(box, { account: "", scheme: "", signature: "" });
  box.querySelector('[name="signed_commit"]').value = "";
}

function hexOf(text) {
  const bytes = new TextEncoder().encode(text);
  return "0x" + Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function boxes() {
  return document.querySelectorAll("[data-sign]");
}

function kindKept() {
  try {
    return window.localStorage.getItem(KIND);
  } catch (error) {
    return null;
  }
}

function keepKind(kind) {
  try {
    if (kind) window.localStorage.setItem(KIND, kind);
    else window.localStorage.removeItem(KIND);
  } catch (error) { /* the browser keeps nothing: the wallet is chosen again after a refresh */ }
}

// The box names the connected wallet, with its address and its account as IDs, or offers the
// two kinds of wallet.
function name(line, one) {
  const parts = one.kind === "hedera"
    ? [one.name, ", account ", [one.account]]
    : [one.name, ", address ", [short(one.address)],
      ...(one.account ? [", Hedera account ", [one.account]] : [", no Hedera account yet"])];
  line.replaceChildren(...parts.map((part) => {
    if (typeof part === "string") return part;
    const id = document.createElement("span");
    id.className = "id";
    id.textContent = part[0];
    return id;
  }));
}

function show(box) {
  const connected = box.querySelector(".hm-wallet");
  const choice = box.querySelector(".hm-sign-choice");
  if (!connected || !choice) return;
  connected.hidden = !wallet;
  choice.hidden = Boolean(wallet);
  if (!wallet) return;
  name(connected.querySelector(".hm-wallet-who"), wallet);
  const make = connected.querySelector(".hm-wallet-new");
  make.hidden = wallet.kind !== "evm" || Boolean(wallet.account);
  make.querySelector(".hm-wallet-address").textContent = wallet.address || "";
}

// The wallet of every box on the page changes at once; a signature goes with the account it names.
function setWallet(one) {
  const same = wallet && one && wallet.kind === one.kind && wallet.account === one.account;
  if (!same) boxes().forEach(unsign);
  wallet = one;
  keepKind(one ? one.kind : null);
  boxes().forEach(show);
}

// ---------------------------------------------------------------------------- an EVM wallet

// The name of the browser's EVM wallet: the wallet that announces this provider (EIP-6963), else
// what the provider says of itself.
function evmName(ethereum) {
  let name = null;
  const heard = (event) => {
    if (event.detail && event.detail.provider === ethereum) name = event.detail.info?.name || null;
  };
  window.addEventListener("eip6963:announceProvider", heard);
  window.dispatchEvent(new Event("eip6963:requestProvider"));
  window.removeEventListener("eip6963:announceProvider", heard);
  if (name) return name;
  if (ethereum.isRabby) return "Rabby";
  if (ethereum.isBraveWallet) return "Brave Wallet";
  if (ethereum.isCoinbaseWallet) return "Coinbase Wallet";
  return ethereum.isMetaMask ? "MetaMask" : "your EVM wallet";
}

function evmProvider() {
  if (window.ethereum) return window.ethereum;
  throw new Error("No EVM wallet, such as MetaMask, is in this browser. Install one, or sign "
    + "with a Hedera wallet.");
}

// An EVM wallet knows only the address: the mirror node gives its Hedera account, or none yet.
async function evmWallet(ethereum, address) {
  const answer = await fetch(`/register/account?address=${encodeURIComponent(address)}`);
  const found = await answer.json().catch(() => ({}));
  if (!answer.ok && answer.status !== 404) {
    throw new Error(found.problem || "The Hedera account of this address could not be read. "
      + "Try again in a moment.");
  }
  return { kind: "evm", name: evmName(ethereum), address, account: answer.ok ? found.account : null };
}

async function connectEvm(box) {
  const ethereum = evmProvider();
  let address;
  try { // the wallet's own list of accounts, so that another one can be chosen (EIP-2255)
    await ethereum.request({ method: "wallet_requestPermissions", params: [{ eth_accounts: {} }] });
    [address] = await ethereum.request({ method: "eth_accounts" });
  } catch (error) {
    if (error && error.code === 4001) throw error; // declined in the wallet
    [address] = await ethereum.request({ method: "eth_requestAccounts" }); // a wallet without it
  }
  if (!address) throw new Error("No address was connected. Approve the connection in your wallet.");
  say(box, `Connected to ${short(address)}. Looking for its Hedera account on the test network.`);
  return evmWallet(ethereum, address);
}

async function signEvm(box) {
  const ethereum = evmProvider();
  say(box, `Sign the text in ${wallet.name}.`);
  const signature = await ethereum.request({
    method: "personal_sign",
    params: [hexOf(signedText(box, wallet.account)), wallet.address],
  });
  return { account: wallet.account, scheme: "eip191", signature };
}

// An EVM wallet that changes its account while it is connected: the box follows it.
if (window.ethereum && typeof window.ethereum.on === "function") {
  window.ethereum.on("accountsChanged", async (accounts) => {
    if (!wallet || wallet.kind !== "evm") return;
    const [address] = accounts || [];
    if (address && address.toLowerCase() === wallet.address.toLowerCase()) return;
    let one = null;
    try {
      if (address) one = await evmWallet(window.ethereum, address);
    } catch (error) { /* it is chosen again */ }
    setWallet(one);
  });
}

// ------------------------------------------------------------------------- a Hedera wallet

// The window of a check is a modal dialog, and the page behind a modal dialog cannot be reached.
// WalletConnect adds its list of wallets at the end of the page, once (the element wcm-modal, by
// document.body.insertAdjacentElement in the constructor of @walletconnect/modal 2.7.0), so the
// list opened behind the window (30 October 2026). The list must be born inside the open window:
// it listens for "open" from its constructor and stops listening when it leaves the page
// (disconnectedCallback in @walletconnect/modal-ui 2.7.0), so a list moved after its birth never
// opens again, which a first fix did. That one call of the library is sent into the window.
const addToBody = document.body.insertAdjacentElement.bind(document.body);
document.body.insertAdjacentElement = (where, element) => {
  const open = element && element.tagName === "WCM-MODAL" && document.querySelector("dialog[open]");
  return open ? open.insertAdjacentElement(where, element) : addToBody(where, element);
};

let connecting = null; // the one WalletConnect connection of the page, once it is asked for

function hederaConnector(projectId) {
  if (connecting === null) {
    connecting = (async () => {
      const [wc, sdk] = await Promise.all([import(WALLET_CONNECT), import(HIERO_SDK)]);
      const made = new wc.DAppConnector(
        { name: "Jevadu", description: "The register of hackathon submissions on Hedera",
          url: location.origin, icons: [] },
        sdk.LedgerId.TESTNET, projectId, Object.values(wc.HederaJsonRpcMethod),
        [wc.HederaSessionEvent.ChainChanged, wc.HederaSessionEvent.AccountsChanged],
        [wc.HederaChainId.Testnet],
      );
      // init brings back a connection that the wallet kept (DAppConnector.init of
      // @hashgraph/hedera-wallet-connect 2.1.3 makes a signer of each session it finds)
      await made.init({ logger: "error" });
      return made;
    })();
    connecting.catch(() => { connecting = null; }); // a load that failed can be tried again
  }
  return connecting;
}

// The last account that the wallet connected, with the wallet's own name for itself.
function hederaWallet(made) {
  const signer = made.signers[made.signers.length - 1];
  if (!signer) return null;
  let name = "your Hedera wallet";
  try {
    name = made.walletConnectClient.session.get(signer.topic).peer.metadata.name || name;
  } catch (error) { /* the connection gives no name */ }
  return { kind: "hedera", name, account: signer.getAccountId().toString() };
}

async function connectHedera(box) {
  if (!box.dataset.projectId) {
    throw new Error("Hedera wallets sign through WalletConnect, which needs a project ID that "
      + "this site does not have yet.");
  }
  say(box, "Choose your Hedera wallet in the list, then approve the connection in it.");
  const made = await hederaConnector(box.dataset.projectId);
  if (made.signers.length === 0) await made.openModal();
  const one = hederaWallet(made);
  if (!one) throw new Error("No account was connected. Approve the connection in your wallet.");
  return one;
}

async function signHedera(box) {
  const made = await hederaConnector(box.dataset.projectId);
  if (!made.signers.some((signer) => signer.getAccountId().toString() === wallet.account)) {
    throw problem(ENDED, true);
  }
  say(box, `Sign the text in ${wallet.name}.`);
  const result = await made.signMessage({
    signerAccountId: `hedera:testnet:${wallet.account}`,
    message: signedText(box, wallet.account),
  });
  const signatureMap = result?.signatureMap ?? result?.result?.signatureMap;
  if (!signatureMap) throw new Error("The wallet gave no signature. Sign again.");
  return { account: wallet.account, scheme: "hedera", signature: signatureMap };
}

// ------------------------------------------------------------------- the box of the register

// Another wallet: this one is let go, in the wallet too where the wallet allows it.
async function letGo(box) {
  const was = wallet;
  setWallet(null);
  if (was && was.kind === "hedera" && connecting) {
    try {
      await (await connecting).disconnectAll();
    } catch (error) { /* the wallet had ended it already */ }
  } else if (was && was.kind === "evm" && window.ethereum) {
    try {
      await window.ethereum.request({
        method: "wallet_revokePermissions", params: [{ eth_accounts: {} }],
      });
    } catch (error) { /* a wallet without it: its own list of accounts opens next time */ }
  }
  say(box, "Disconnected. Choose a wallet to sign with.");
}

async function copyAddress(button) {
  const code = button.closest(".hm-wallet-new")?.querySelector(".hm-wallet-address");
  if (!code) return;
  try {
    await navigator.clipboard.writeText(code.textContent);
    button.textContent = "Copied";
    setTimeout(() => { button.textContent = "Copy"; }, 2000);
  } catch (error) { // no clipboard here: the address is selected, ready to be copied
    window.getSelection().selectAllChildren(code);
  }
}

// After a refresh, the wallet connected last in this browser is looked for, with no question to
// the person: WalletConnect brings back the connection that a Hedera wallet kept, and an EVM
// wallet names the addresses that it lets this site see (eth_accounts asks nothing).
let restoring = null;

function restore(projectId) {
  restoring ??= (async () => {
    const kind = kindKept();
    let one = null;
    try {
      if (kind === "hedera") {
        one = hederaWallet(await hederaConnector(projectId));
      } else if (kind === "evm") {
        const [address] = await window.ethereum.request({ method: "eth_accounts" });
        if (address) one = await evmWallet(window.ethereum, address);
      }
    } catch (error) { /* it is chosen again */ }
    if (!wallet) setWallet(one); // a wallet chosen meanwhile stands
  })();
  return restoring;
}

async function setUp(box) {
  if (box.dataset.signReady) return;
  box.dataset.signReady = "1";
  const kind = kindKept();
  const can = (kind === "hedera" && box.dataset.projectId) || (kind === "evm" && window.ethereum);
  if (!wallet && restoring === null && can) {
    box.querySelector(".hm-sign-choice").hidden = true;
    say(box, "Looking for the wallet that you connected before.");
    await restore(box.dataset.projectId);
    quiet(box);
  }
  show(box);
}

function setUpAll() {
  boxes().forEach((box) => { setUp(box); });
}

setUpAll();
document.addEventListener("htmx:afterSettle", setUpAll);

// A problem of the register shows above its box, which stays as it was (30 October 2026). The
// answer names the newest commit when GitHub was asked again. A team that adds its line to the
// README makes a commit, and the record names the newest one, so the next signature must name it:
// a signature of an older commit is let go, else every new signature would name the old one.
document.addEventListener("htmx:afterSettle", (event) => {
  const place = event.detail.target;
  if (!place || place.id !== "register-problem") return;
  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  place.focus({ preventScroll: true });
  place.scrollIntoView({ block: "nearest", behavior: still ? "auto" : "smooth" });
  const latest = place.querySelector("[data-latest-commit]")?.dataset.latestCommit;
  const register = place.closest("#register-box");
  const box = register && register.querySelector("[data-sign]");
  if (!latest || !box || box.dataset.commit === latest) return;
  box.dataset.commit = latest;
  const now = register.querySelector(".hm-commit-now");
  if (now) now.textContent = `${latest.slice(0, 12)}…`;
  if (!box.querySelector('[name="signature"]').value) return;
  unsign(box);
  say(box, `The repository has a newer commit, ${latest.slice(0, 12)}…, and the record will name `
    + "it. Sign again.", "problem");
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest(
    "[data-sign-with], [data-sign-now], [data-wallet-other], [data-wallet-copy]");
  const box = button && button.closest("[data-sign]");
  if (!box) return;
  if (button.hasAttribute("data-wallet-copy")) {
    copyAddress(button);
    return;
  }
  const buttons = box.querySelectorAll("button");
  buttons.forEach((one) => { one.disabled = true; });
  try {
    if (button.hasAttribute("data-wallet-other")) {
      await letGo(box);
      return;
    }
    if (button.dataset.signWith) {
      setWallet(button.dataset.signWith === "evm" ? await connectEvm(box) : await connectHedera(box));
    } else if (wallet && wallet.kind === "evm" && !wallet.account) { // the faucet may have made it
      say(box, `Looking for the Hedera account of ${short(wallet.address)} again.`);
      setWallet(await evmWallet(evmProvider(), wallet.address));
    }
    if (!wallet) throw problem(ENDED, true);
    if (wallet.kind === "evm" && !wallet.account) throw problem(NO_ACCOUNT);
    const signed = wallet.kind === "evm" ? await signEvm(box) : await signHedera(box);
    keep(box, signed);
    box.closest("#register-box")?.querySelector("#register-problem")?.replaceChildren();
    say(box, `Signed by the account ${signed.account}. Now click "Register on Hedera testnet".`,
      "done");
  } catch (error) {
    if (error && error.ends) setWallet(null);
    // 4001: the person declined in the wallet (EIP-1193)
    say(box, error && error.code === 4001
      ? "You declined in the wallet, so nothing was signed."
      : (error && error.message) || String(error), "problem");
  } finally {
    buttons.forEach((one) => { one.disabled = false; });
    const hedera = box.querySelector('[data-sign-with="hedera"]');
    if (hedera) hedera.disabled = !box.dataset.projectId;
  }
});
