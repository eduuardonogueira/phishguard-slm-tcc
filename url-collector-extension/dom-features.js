// Extrai sinais do DOM da pagina carregada, para o modo offline.
//
// Roda NO CONTEXTO DA PAGINA via chrome.scripting.executeScript({func: ...}).
// Nao faz requisicoes de rede: le apenas o DOM ja renderizado no navegador
// (melhor que um fetch server-side, que nao executaria JS). Retorna features
// binarias (0/1) no mesmo formato do dataset.
//
// Carregado no service worker via importScripts("dom-features.js") e no popup
// via <script src="dom-features.js">, para ser referenciado por ambos.
function extractDomFeatures() {
  try {
    return {
      // Campos de formulario (login/senha) sao um forte sinal de phishing.
      html_input: document.querySelector("input, textarea, select") ? 1 : 0,
      // Iframes escondidos sao comuns em paginas maliciosas.
      iframe: document.querySelector("iframe") ? 1 : 0,
      // Redirecionamento automatico via meta refresh.
      redirect: document.querySelector('meta[http-equiv="refresh" i]') ? 1 : 0,
    };
  } catch (e) {
    return {};
  }
}
