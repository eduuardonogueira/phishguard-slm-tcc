# PhishGuard SLM

Código para reproduzir o Trabalho de Conclusão de Curso (TCC) *Detecção de phishing localizado (PT-BR) com um small language model executado localmente*, de Eduardo Nogueira, na Universidade Federal Rural da Amazônia (UFRA, 2026). O trabalho avalia modelos de linguagem pequenos (SLMs), executados no próprio computador do usuário, na detecção de URLs de *phishing* dirigidas ao público brasileiro.

O trabalho compara dois modelos de linguagem pequenos (SLMs) ajustados com LoRA, Qwen2.5-0.5B-Instruct e Gemma 3 1B, com o XGBoost do trabalho-base, o Phishing Guardian (Guarizi; Mascarenhas; Moraes, 2025). A comparação usa dois conjuntos de dados, o do trabalho-base e o PhishBR-URL, montado no TCC com *phishing* dirigido ao público brasileiro. O repositório também traz o servidor local e a extensão de navegador que usam o modelo durante a navegação.

O repositório contém:

1. a obtenção e preparação dos dois conjuntos de dados;
2. a matriz de 18 experimentos (3 modelos × 2 conjuntos × 3 conjuntos de atributos), com treino, avaliação e análise estatística;
3. os resultados obtidos no TCC (`outputs/`);
4. o servidor local e a extensão do Chrome.

## Estrutura

```
src/phishguard_slm/
  dados.py        baixa e prepara os conjuntos paper e br
  dominios.py     domínio registrado (eTLD+1) pela Public Suffix List embutida
  featurize.py    8 atributos léxicos e conversão de escala do trabalho-base
  experiments.py  matriz de experimentos: partições, seleção de atributos, treino, avaliação
  train.py        ajuste LoRA dos SLMs
  scoring.py      P(phishing) pelo SLM (log-probabilidades de "sim" e "nao")
  prompting.py    prompt em português com a URL e os atributos
  evaluate.py     métricas e escolha do limiar na validação
  stats.py        IC por bootstrap de domínio, McNemar e correção de Holm
  features.py     atributos calculados em tempo real (WHOIS, TLS, Open PageRank)
  server.py       servidor Flask usado pela extensão
  cli.py          comando `phishguard`
src/pages/dashboard.html   painel do servidor
url-collector-extension/   extensão do Chrome (Manifest V3)
scripts/                   tabelas e figuras complementares do TCC
datasets/splits/           partição do paper e conjuntos de atributos (congelados)
outputs/                   resultados do TCC (ver abaixo)
```

## Instalação

São necessários Python 3.10 a 3.12 e o [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env   # preencha HF_TOKEN se for treinar o Gemma 3
```

O Gemma 3 1B é um modelo restrito no Hugging Face. Para usá-lo, aceite a licença em https://huggingface.co/google/gemma-3-1b-it e coloque um token de leitura em `HF_TOKEN`.

## Dados

```bash
uv run phishguard dados
```

O comando baixa e confere pelo SHA-256 os dois conjuntos:

- **paper**: o CSV publicado no repositório do [Phishing Guardian](https://github.com/bguarizi/phishing-guardian), no commit `d520a9a`, com 50.261 linhas antes da limpeza. O arquivo não é redistribuído aqui.
- **br**: o [PhishBR-URL](https://www.kaggle.com/datasets/eduuardonog/phishbr-url), versão 1 (DOI [10.34740/KAGGLE/DSV/22753851](https://doi.org/10.34740/kaggle/dsv/22753851), CC BY-SA 4.0). O download não exige conta no Kaggle.

Em seguida, o comando gera as duas versões de cada conjunto. A versão bruta, em unidades originais, é a lida pelos SLMs. A normalizada, na escala do trabalho-base, é a usada pelo XGBoost. As partições de treino, validação e teste são as mesmas do TCC: a do paper está versionada em `datasets/splits/paper.csv`, e a do BR vem da coluna `split` do PhishBR-URL. Nas duas, nenhum domínio registrado aparece em mais de uma partição.

### Diferenças em relação aos dados do TCC

O PhishBR-URL foi publicado com dados pessoais mascarados. Em 306 das 26.724 URLs, e-mails, números no formato de CPF e valores de parâmetros como `token`, `session` e `senha` tiveram cada letra e dígito trocados por `x`, mantendo o comprimento. Os 13 atributos não mudam, mas o texto lido pelos SLMs muda nessas URLs. Por isso, um novo treino com os mesmos parâmetros deve dar números próximos aos do TCC, não idênticos.

Duas URLs de treino ficaram idênticas a outras após o mascaramento. Como a URL é a chave da partição, `phishguard dados` descarta essas cópias, e o BR passa a ter 26.722 linhas, 18.751 delas no treino. As 227 URLs de validação e teste que foram mascaradas aparecem mascaradas também nos arquivos de `outputs/runs/*/scores/`.

## Reprodução dos experimentos

O treino dos SLMs exige GPU. O XGBoost roda em CPU.

```bash
uv run phishguard exp train                  # as 18 combinações; pula as já concluídas
uv run phishguard exp train -m xgb -d br     # só uma parte da matriz
uv run phishguard exp status                 # o que já foi treinado e avaliado
uv run phishguard exp stats                  # IC 95%, ponto de operação, comparações pareadas
uv run phishguard exp leaderboard            # outputs/leaderboard.csv e .md
```

Os eixos da matriz são:

- **Modelo:** `qwen05b` (Qwen/Qwen2.5-0.5B-Instruct + LoRA), `gemma1b` (google/gemma-3-1b-it + LoRA) e `xgb` (XGBoost com 300 árvores, profundidade 6 e taxa de aprendizado 0,1, sem busca de hiperparâmetros).
- **Conjunto de dados:** `paper` e `br`. Cada modelo é avaliado só no teste do conjunto em que foi treinado.
- **Atributos:** `todas` (os 13 do trabalho-base), `corr` (selecionados pela correlação de Spearman no treino de cada conjunto, em `datasets/splits/feature_sets*.json`) e `url` (só o texto da URL para os SLMs; os 8 atributos léxicos para o XGBoost).

O LoRA usa r = 16, α = 32, *dropout* 0,05 e as projeções `q`, `k`, `v` e `o`, com 1 época, taxa de aprendizado 2e-4, *batch* efetivo 16 e semente 42 (`src/phishguard_slm/config.py`). O limiar de decisão é o de melhor F1 na validação. O teste também é avaliado com prevalência realista de *phishing* (7%).

Cada run grava em `outputs/runs/<modelo>__<conjunto>__<atributos>/` o manifesto (hashes do dado e da partição, hiperparâmetros), as métricas, a latência em CPU e a probabilidade de cada URL do teste. Os pesos treinados não são versionados. Um run só é refeito se o dado, a partição ou o conjunto de atributos mudarem. Como os manifestos de `outputs/` registram os hashes dos dados originais do TCC, o primeiro `exp train` refaz todos os runs.

Os scripts de `scripts/` geram as tabelas e figuras complementares a partir das probabilidades salvas, sem carregar modelos:

```bash
uv run --extra figuras python scripts/tcc_extras.py --dataset br
uv run --extra figuras python scripts/tcc_extras.py --dataset paper   # ou --dataset base
uv run python scripts/tcc_erros.py
```

Com os dados publicados, `exp stats`, `exp leaderboard` e `tcc_extras.py` reproduzem exatamente os arquivos de `outputs/`. Em `tcc_erros.py` há uma única diferença: a fração de *phishing* em hospedagem compartilhada, na última coluna de `br_fn_dominios.csv`, sai 0,1583 em vez de 0,1589, porque o mascaramento e as duas linhas descartadas mudam o conjunto de referência. Os arquivos de `outputs/` guardam os valores do TCC.

## Resultados do TCC

- `outputs/leaderboard.md`: métricas no teste de cada run (AP, F1, precisão, revocação, FPR, latência).
- `outputs/stats/`: intervalos de confiança, comparações pareadas, erros por fonte e por sufixo.
- `outputs/figuras/`: curvas precisão-revocação, calibração, AP × latência e arquitetura da ferramenta.
- `outputs/runs/`: manifestos, avaliações e probabilidades por URL dos 18 runs.

## Uso local com a extensão do navegador

1. Suba o servidor:

   ```bash
   uv run phishguard serve
   ```

   Por padrão, o servidor carrega o adaptador LoRA do Qwen2.5-0.5B-Instruct versionado em `outputs/adapter/`, que é a versão integrada à extensão no TCC, com limiar 0,5. O modelo base é baixado do Hugging Face na primeira execução. Para servir um run treinado na matriz, com os atributos e o limiar da validação desse run, use `uv run phishguard serve --run qwen05b__br__todas`.

2. No Chrome, abra `chrome://extensions`, ative o **Modo do desenvolvedor**, clique em **Carregar sem compactação** e escolha a pasta `url-collector-extension/`.

3. Navegue normalmente. A cada página, a extensão envia a URL e os atributos lidos da página (`html_input`, `iframe` e `redirect`) para `http://127.0.0.1:5000/receive_url`. O servidor calcula os atributos de rede: idade do domínio por WHOIS, validade do certificado TLS e, se houver `OPENPAGERANK_API_KEY`, o PageRank. Em seguida, responde com o veredito exibido no aviso da página. O painel com latência e uso de memória fica em http://127.0.0.1:5000/dashboard.

Para classificar uma URL no terminal: `uv run phishguard predict "https://exemplo.com.br/login"`.

**Privacidade.** O modelo roda no próprio computador. Mesmo assim, as consultas WHOIS e TLS saem para a rede, e o domínio visitado é enviado à Open PageRank quando a chave está configurada.

## Como citar

Trabalho de conclusão de curso:

> NOGUEIRA, Eduardo. **Detecção de phishing localizado (PT-BR) com um small language model executado localmente**. 2026. Trabalho de Conclusão de Curso – Universidade Federal Rural da Amazônia, 2026.

Conjunto de dados:

> NOGUEIRA, Eduardo. **PhishBR-URL**: URLs de *phishing* dirigido ao público brasileiro. Kaggle, 2026. Conjunto de dados. DOI: 10.34740/KAGGLE/DSV/22753851.

Trabalho-base:

> GUARIZI, Bianca Domingos; MASCARENHAS, Dalbert Matos; MORAES, Igor Monteiro. Phishing Guardian: detecção de sites de phishing com Machine Learning. *In*: SIMPÓSIO BRASILEIRO DE CIBERSEGURANÇA (SBSEG), 25., 2025. **Anais** [...]. Porto Alegre: SBC, 2025. p. 693-709. DOI: 10.5753/sbseg.2025.11491.

## Licenças

- **Código:** MIT (`LICENSE`).
- **Extensão:** derivada da extensão do Phishing Guardian.
- **PhishBR-URL:** CC BY-SA 4.0.
- **CSV do trabalho-base:** não é redistribuído aqui; é baixado do repositório original.
- **Adaptador em `outputs/adapter/`:** derivado do Qwen2.5-0.5B-Instruct (Apache 2.0).
