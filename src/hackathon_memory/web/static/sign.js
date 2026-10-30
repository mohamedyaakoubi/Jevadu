// Teams sign their own registration (design 9.6, 29 October 2026). The register's box holds a
// fieldset [data-sign] with the parts of the record. A button signs its text with a Hedera wallet
// such as HashPack (Hedera's WalletConnect library, hedera_signMessage) or with an EVM wallet such
// as MetaMask (EIP-1193, personal_sign), and the hidden fields carry the account, the way of
// signing, the signature and the commit to the server, which checks the signature against the
// account's key on the ledger before it writes. The buttons name the two kinds of wallet, not one
// wallet each, since WalletConnect lists every Hedera wallet that it supports (30 October 2026).
// The WalletConnect library is loaded only when a Hedera wallet is asked for, from a CDN, since
// the site has no build step (tried in a browser on 29 October 2026: about 5 seconds).

const WALLET_CONNECT = "https://esm.sh/@hashgraph/hedera-wallet-connect@2.1.3";
const HIERO_SDK = "https://esm.sh/@hiero-ledger/sdk@2.79.0";

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

async function withEvmWallet(box) {
  const ethereum = window.ethereum;
  if (!ethereum) {
    throw new Error("No EVM wallet, such as MetaMask, is in this browser. Install one, or sign "
      + "with a Hedera wallet.");
  }
  const [address] = await ethereum.request({ method: "eth_requestAccounts" });
  say(box, `Connected to ${short(address)}. Looking for its Hedera account on the test network.`);
  // An EVM wallet knows only the address: the mirror node gives its Hedera account.
  const answer = await fetch(`/register/account?address=${encodeURIComponent(address)}`);
  const found = await answer.json();
  if (!answer.ok) throw new Error(found.problem || "The account of this address was not found.");
  say(box, `Found the Hedera account ${found.account} of ${short(address)}. Sign the text in `
    + "your wallet.");
  const signature = await ethereum.request({
    method: "personal_sign",
    params: [hexOf(signedText(box, found.account)), address],
  });
  return { account: found.account, scheme: "eip191", signature };
}

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

let connector = null; // one WalletConnect connection for the page

async function withHederaWallet(box) {
  if (!box.dataset.projectId) {
    throw new Error("Hedera wallets sign through WalletConnect, which needs a project ID that "
      + "this site does not have yet.");
  }
  say(box, "Choose your Hedera wallet in the list, then approve the connection in it.");
  if (connector === null) {
    const [wc, sdk] = await Promise.all([import(WALLET_CONNECT), import(HIERO_SDK)]);
    const made = new wc.DAppConnector(
      { name: "Jevadu", description: "The register of hackathon submissions on Hedera",
        url: location.origin, icons: [] },
      sdk.LedgerId.TESTNET, box.dataset.projectId, Object.values(wc.HederaJsonRpcMethod),
      [wc.HederaSessionEvent.ChainChanged, wc.HederaSessionEvent.AccountsChanged],
      [wc.HederaChainId.Testnet],
    );
    await made.init({ logger: "error" });
    connector = made;
  }
  if (connector.signers.length === 0) await connector.openModal();
  const signer = connector.signers[connector.signers.length - 1];
  if (!signer) throw new Error("No account was connected. Approve the connection in your wallet.");
  const account = signer.getAccountId().toString();
  say(box, `Connected to the account ${account}. Sign the text in your wallet.`);
  const result = await connector.signMessage({
    signerAccountId: `hedera:testnet:${account}`,
    message: signedText(box, account),
  });
  const signatureMap = result?.signatureMap ?? result?.result?.signatureMap;
  if (!signatureMap) throw new Error("The wallet gave no signature. Sign again.");
  return { account, scheme: "hedera", signature: signatureMap };
}

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
  const button = event.target.closest("[data-sign-with]");
  const box = button && button.closest("[data-sign]");
  if (!box) return;
  const buttons = box.querySelectorAll("[data-sign-with]");
  buttons.forEach((one) => { one.disabled = true; });
  try {
    const signed = button.dataset.signWith === "evm"
      ? await withEvmWallet(box) : await withHederaWallet(box);
    keep(box, signed);
    box.closest("#register-box")?.querySelector("#register-problem")?.replaceChildren();
    say(box, `Signed by the account ${signed.account}. Now click "Register on Hedera testnet".`,
      "done");
  } catch (error) {
    // 4001: the person declined in the wallet (EIP-1193)
    say(box, error && error.code === 4001
      ? "You declined in the wallet, so nothing was signed."
      : (error && error.message) || String(error), "problem");
  } finally {
    buttons.forEach((one) => {
      one.disabled = one.dataset.signWith === "hedera" && !box.dataset.projectId;
    });
  }
});
