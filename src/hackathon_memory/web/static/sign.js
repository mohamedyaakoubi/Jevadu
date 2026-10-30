// Teams sign their own registration (design 9.6, 29 October 2026). The register's box holds a
// fieldset [data-sign] with the parts of the record. A button signs its text with MetaMask
// (EIP-1193, personal_sign) or with HashPack (Hedera's WalletConnect library, hedera_signMessage),
// and the hidden fields carry the account, the way of signing, the signature and the commit to the
// server, which checks the signature against the account's key on the ledger before it writes.
// The WalletConnect library is loaded only when HashPack is asked for, from a CDN, since the site
// has no build step (tried in a browser on 29 October 2026: about 5 seconds).

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

function say(box, words) {
  const status = box.querySelector(".hm-sign-status");
  if (status) status.textContent = words;
}

function keep(box, signed) {
  box.querySelector('[name="signer"]').value = signed.account;
  box.querySelector('[name="scheme"]').value = signed.scheme;
  box.querySelector('[name="signature"]').value = signed.signature;
  box.querySelector('[name="signed_commit"]').value = box.dataset.commit;
}

function hexOf(text) {
  const bytes = new TextEncoder().encode(text);
  return "0x" + Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function withMetaMask(box) {
  const ethereum = window.ethereum;
  if (!ethereum) {
    throw new Error("MetaMask is not in this browser. Install it, or sign with HashPack.");
  }
  const [address] = await ethereum.request({ method: "eth_requestAccounts" });
  // MetaMask knows only the address: the mirror node gives its Hedera account.
  const answer = await fetch(`/register/account?address=${encodeURIComponent(address)}`);
  const found = await answer.json();
  if (!answer.ok) throw new Error(found.problem || "The account of this address was not found.");
  say(box, `Sign the text in MetaMask, for the account ${found.account}.`);
  const signature = await ethereum.request({
    method: "personal_sign",
    params: [hexOf(signedText(box, found.account)), address],
  });
  return { account: found.account, scheme: "eip191", signature };
}

// The window of a check is a modal dialog, and the page behind a modal dialog cannot be reached.
// WalletConnect adds its list of wallets at the end of the page (the element wcm-modal, made by
// the constructor of @walletconnect/modal 2.7.0, dist/index.js), so the list opened behind the
// window (30 October 2026). It goes into the open window as soon as it is added.
function walletsInWindow() {
  const list = document.querySelector("wcm-modal");
  const open = document.querySelector("dialog[open]");
  if (list && open && list.parentElement !== open) open.appendChild(list);
}
new MutationObserver(walletsInWindow).observe(document.body, { childList: true });

let connector = null; // one WalletConnect connection for the page

async function withHashPack(box) {
  if (!box.dataset.projectId) {
    throw new Error("HashPack signs through WalletConnect, which needs a project ID that this "
      + "site does not have yet.");
  }
  say(box, "Opening WalletConnect: choose HashPack, then approve the connection.");
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
  if (connector.signers.length === 0) {
    walletsInWindow(); // the list may have been made before this window opened
    await connector.openModal();
  }
  const signer = connector.signers[connector.signers.length - 1];
  if (!signer) throw new Error("No account was connected. Approve the connection in HashPack.");
  const account = signer.getAccountId().toString();
  say(box, `Sign the text in HashPack, for the account ${account}.`);
  const result = await connector.signMessage({
    signerAccountId: `hedera:testnet:${account}`,
    message: signedText(box, account),
  });
  const signatureMap = result?.signatureMap ?? result?.result?.signatureMap;
  if (!signatureMap) throw new Error("HashPack gave no signature. Sign again.");
  return { account, scheme: "hedera", signature: signatureMap };
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-sign-with]");
  const box = button && button.closest("[data-sign]");
  if (!box) return;
  const buttons = box.querySelectorAll("[data-sign-with]");
  buttons.forEach((one) => { one.disabled = true; });
  try {
    const signed = button.dataset.signWith === "metamask"
      ? await withMetaMask(box) : await withHashPack(box);
    keep(box, signed);
    say(box, `Signed by the account ${signed.account}. Now click "Register on Hedera testnet".`);
  } catch (error) {
    // 4001: the person declined in the wallet (EIP-1193)
    say(box, error && error.code === 4001
      ? "You declined in the wallet, so nothing was signed."
      : (error && error.message) || String(error));
  } finally {
    buttons.forEach((one) => {
      one.disabled = one.dataset.signWith === "hashpack" && !box.dataset.projectId;
    });
  }
});
