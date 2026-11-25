// Escuta as mensagens enviadas pelo background.js e exibe o aviso na pagina.
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.mensagem) {
        exibirMensagem(request.mensagem, request.type);
    }
    // Confirma o recebimento para o background nao registrar um falso
    // "message port closed" (que dispararia reenvios e banners duplicados).
    sendResponse({ ok: true });
});

// Exibe o aviso (verde = seguro, vermelho = suspeito/erro) por 5 segundos.
function exibirMensagem(mensagem, type) {
    // Remove um aviso anterior, se houver, para nao acumular divs.
    const anterior = document.getElementById('custom-mensagem');
    if (anterior) anterior.remove();

    const t = parseInt(type, 10);
    const seguro = t === 0;

    const el = document.createElement('div');
    el.id = 'custom-mensagem';
    el.className = seguro ? 'pg-safe' : 'pg-danger';

    const icone = document.createElement('span');
    icone.className = 'pg-icon';
    icone.textContent = seguro ? '✅' : '⚠️';

    const texto = document.createElement('span');
    texto.className = 'pg-text';
    // Remove emoji/entidade inicial que o servidor ja envia, para nao duplicar.
    texto.innerHTML = String(mensagem).replace(
        /^\s*(&#\d+;|[✅⚠️❗✔])\s*/,
        ''
    );

    el.appendChild(icone);
    el.appendChild(texto);
    document.body.appendChild(el);

    // Auto-dismiss com animacao de saida.
    setTimeout(() => {
        el.classList.add('pg-hide');
        setTimeout(() => el.remove(), 320);
    }, 5000);
}
