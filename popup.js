// PATTI SHOT v2 - popup
const captureBtn = document.getElementById("captureBtn");
const statusEl = document.getElementById("status");
const unsupportedEl = document.getElementById("unsupported");
const fmtPng = document.getElementById("fmtPng");
const fmtPdf = document.getElementById("fmtPdf");

// バージョン表示はmanifest.jsonから取得（必ず一致させるため）
document.getElementById("version").textContent = "v" + chrome.runtime.getManifest().version;

let activeTabId = null;

function isCapturableUrl(url) {
  if (!url) return false;
  if (!/^https?:\/\//.test(url)) return false;
  if (url.startsWith("https://chromewebstore.google.com")) return false;
  return true;
}

// 形式選択を保存・復元（デフォルトは両方ON）
chrome.storage.local.get({ formats: { png: true, pdf: true } }, ({ formats }) => {
  fmtPng.checked = formats.png !== false;
  fmtPdf.checked = formats.pdf !== false;
});
function saveFormats() {
  chrome.storage.local.set({ formats: { png: fmtPng.checked, pdf: fmtPdf.checked } });
  // 両方OFFでは撮影できない
  captureBtn.disabled = !fmtPng.checked && !fmtPdf.checked;
  statusEl.textContent = captureBtn.disabled ? "保存形式(PNG/PDF)を選んでください" : "";
}
fmtPng.addEventListener("change", saveFormats);
fmtPdf.addEventListener("change", saveFormats);

// 開いた時点のタブが撮影可能かチェック
chrome.tabs.query({ active: true, lastFocusedWindow: true }, (tabs) => {
  const tab = tabs && tabs[0];
  if (!tab || !isCapturableUrl(tab.url)) {
    unsupportedEl.style.display = "block";
    captureBtn.disabled = true;
    return;
  }
  activeTabId = tab.id;
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "patti-progress") {
    statusEl.textContent = msg.text;
  }
});

captureBtn.addEventListener("click", async () => {
  if (activeTabId === null) return;
  captureBtn.disabled = true;
  statusEl.classList.remove("note");
  statusEl.textContent = "ページ読み込み中…";
  try {
    const res = await chrome.runtime.sendMessage({
      type: "patti-capture",
      tabId: activeTabId,
      formats: { png: fmtPng.checked, pdf: fmtPdf.checked },
    });
    if (res && res.ok) {
      statusEl.textContent = "保存完了！";
      if (res.note) {
        statusEl.classList.add("note");
        statusEl.textContent = "保存完了！ " + res.note;
      }
    } else {
      statusEl.textContent = (res && res.error) || "エラーが発生しました";
    }
  } catch (e) {
    statusEl.textContent = "エラー: " + ((e && e.message) || e);
  } finally {
    captureBtn.disabled = false;
  }
});
