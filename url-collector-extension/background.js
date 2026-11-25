// Classifica a URL da navegacao no servidor e mostra o veredito na aba.
//
// Usa onCompleted (nao onBeforeNavigate): so notificamos depois que a pagina
// de destino terminou de carregar, garantindo que o content script ja esteja
// ativo para receber a mensagem. Com onBeforeNavigate havia uma corrida em que
// respostas rapidas (tipicamente sites seguros) chegavam antes do content
// script novo registrar o listener e a mensagem "Navegacao Segura" se perdia.

// Extrator de features do DOM (define extractDomFeatures no escopo do worker).
importScripts("dom-features.js");

const SERVER_URL = "http://127.0.0.1:5000/receive_url";

// Trava anti-duplicata: guarda a ultima URL classificada por aba. Muitos sites
// disparam onCompleted mais de uma vez (redirects), o que geraria banners
// repetidos. Ignora a mesma URL na mesma aba dentro de uma janela curta.
const lastSeen = new Map(); // tabId -> { url, ts }
const DEDUPE_MS = 3000;

chrome.webNavigation.onCompleted.addListener(async (details) => {
  // Apenas o frame principal (ignora iframes).
  if (details.frameId !== 0) return;

  // Respeita o toggle de validacao automatica do popup (default: ligado).
  const { autoValidation = true } = await chrome.storage.local.get(
    "autoValidation",
  );
  if (!autoValidation) return;

  // Evita classificar a mesma URL repetidamente na mesma aba.
  const now = Date.now();
  const prev = lastSeen.get(details.tabId);
  if (prev && prev.url === details.url && now - prev.ts < DEDUPE_MS) return;
  lastSeen.set(details.tabId, { url: details.url, ts: now });

  // Extrai as features do DOM da aba e classifica (modo unico: o servidor
  // reune URL + rede + DOM).
  const features = await getDomFeatures(details.tabId);
  classifyAndNotify(details.url, details.tabId, features);
});

// Limpa o registro quando a aba e fechada.
chrome.tabs.onRemoved.addListener((tabId) => lastSeen.delete(tabId));

// Injeta o extrator na aba e retorna as features do DOM. Retorna {} quando a
// injecao falha (paginas restritas: chrome://, web store, etc.).
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

function classifyAndNotify(url, tabId, features) {
  fetch(SERVER_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: url, features: features }),
  })
    .then((response) => response.json())
    .then((data) => {
      console.log("Resposta do servidor:", data);
      if (data && data.message) {
        notifyTab(tabId, data.message, data.type);
      } else {
        notifyTab(tabId, "Resposta do servidor vazia ou invalida.", -1);
      }
    })
    .catch((error) => {
      notifyTab(
        tabId,
        "ERRO DE COMUNICACAO!\nVerifique se o software esta executando corretamente.\nCaso nao queira mais receber este alerta, desative a extensao nas configuracoes do navegador.",
        1,
      );
    });
}

// Envia a mensagem ao content script da aba. So refaz o envio quando o erro e
// "receptor inexistente" (content script ainda nao registrou o listener em
// navegacoes muito rapidas). NAO refaz por "message port closed", que ocorre
// mesmo quando a mensagem foi entregue -- era isso que causava banners
// duplicados.
function notifyTab(tabId, mensagem, type, attempt = 0) {
  chrome.tabs.sendMessage(tabId, { mensagem: mensagem, type: type }, () => {
    const err = chrome.runtime.lastError;
    if (!err) return;
    const semReceptor =
      /Receiving end does not exist|Could not establish connection/i.test(
        err.message || "",
      );
    if (semReceptor && attempt < 3) {
      setTimeout(() => notifyTab(tabId, mensagem, type, attempt + 1), 300);
    }
  });
}
