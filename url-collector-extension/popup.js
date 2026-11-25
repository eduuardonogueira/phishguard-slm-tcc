// Logica do popup: toggle de validacao automatica + validacao manual.

const SERVER_URL = "http://127.0.0.1:5000/receive_url";

document.addEventListener("DOMContentLoaded", async () => {
  const toggle = document.getElementById("autoToggle");
  const checkBtn = document.getElementById("checkBtn");
  const result = document.getElementById("result");

  // Estado do toggle de validacao automatica (default: ligado).
  const { autoValidation = true } =
    await chrome.storage.local.get("autoValidation");
  toggle.checked = autoValidation;

  toggle.addEventListener("change", () => {
    chrome.storage.local.set({ autoValidation: toggle.checked });
  });

  // Validacao manual do site atual.
  checkBtn.addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({
      active: true,
      currentWindow: true,
    });
    const url = tab && tab.url ? tab.url : "";

    if (!/^https?:\/\//i.test(url)) {
      renderResult(result, "error", "❌", "Página sem URL válida para verificar.");
      return;
    }

    const features = tab ? await getDomFeatures(tab.id) : {};

    checkBtn.disabled = true;
    renderLoading(result);
    try {
      const resp = await fetch(SERVER_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, features }),
      });
      const data = await resp.json();
      const seguro = parseInt(data.type, 10) === 0;
      renderResult(
        result,
        seguro ? "safe" : "danger",
        seguro ? "✅" : "⚠️",
        seguro ? "Navegação Segura" : "Site Suspeito — possível phishing!",
        url,
      );
    } catch (e) {
      renderResult(
        result,
        "error",
        "❌",
        "Servidor offline. Rode: phishguard serve",
      );
    } finally {
      checkBtn.disabled = false;
    }
  });
});

// Injeta o extrator na aba ativa e retorna as features do DOM. Retorna {}
// quando a injecao falha (paginas restritas).
async function getDomFeatures(tabId) {
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: extractDomFeatures,
    });
    return (results && results[0] && results[0].result) || {};
  } catch (e) {
    return {};
  }
}

function renderLoading(el) {
  el.className = "result loading show";
  el.innerHTML = '<div class="spinner"></div><span>Verificando…</span>';
}

function renderResult(el, kind, icon, texto, url) {
  el.className = `result ${kind} show`;
  const urlHtml = url ? `<div class="url">${escapeHtml(url)}</div>` : "";
  el.innerHTML =
    `<div class="verdict"><span>${icon}</span><span>${escapeHtml(texto)}</span></div>` +
    urlHtml;
}

function escapeHtml(s) {
  return String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c],
  );
}
