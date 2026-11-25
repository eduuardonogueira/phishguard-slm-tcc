# Estatistica - teste paper

Teste: 8346 URLs de 797 dominios; realista: 3796 (7.0% phishing).

## Metodo

- **IC de 95%**: bootstrap percentil com 2000 reamostragens (Efron & Tibshirani, 1993), sorteando
  **dominios** e nao URLs (bootstrap de clusters; Field & Welsh, 2007): URLs do mesmo dominio nao sao
  independentes, e a particao tambem e por dominio.
- **Limiar**: o de melhor F1 na validacao; o teste nunca escolhe limiar (Arp et al., 2022).
- **Ponto de operacao**: limiar escolhido na validacao para precisao >= 90% na prevalencia
  do teste realista (7.0% de phishing), aplicado ao teste realista (Axelsson, 2000;
  Whittaker et al., 2010). Sem limiar = a validacao nao atinge essa precisao.
- **Comparacoes** (mesmas URLs): bootstrap pareado (por dominio) da diferenca de AP e de F1 (Koehn, 2004;
  Berg-Kirkpatrick et al., 2012) e McNemar sobre os acertos (Dietterich, 1998) na versao para dados
  agrupados (Durkalski et al., 2003), com correcao
  de Holm (1979) dentro do dataset. Familia fixada antes dos resultados: mesmo modelo
  (todas x corr, todas x url) e mesmas features (cada par de modelos).
- **Leitura**: "empate" = nao ha evidencia de diferenca com alfa = 0,05 apos Holm. Com 2000
  reamostragens, o menor p do bootstrap e 1/2000 antes da correcao.

## Por run (IC 95%)

| run | AP | F1 | FPR | recall | realista no limiar p/ P>=90% (val): recall | precisao | FPR |
|---|---|---|---|---|---|---|---|
| qwen05b__paper__todas | 1.000 [0.996, 1.000] | 0.981 [0.880, 0.999] | 0.051 [0.000, 0.169] | 0.998 [0.990, 1.000] | 1.000 [1.000, 1.000] | 0.899 [0.522, 1.000] | 0.008 [0.000, 0.032] |
| qwen05b__paper__corr | 1.000 [0.995, 1.000] | 0.936 [0.646, 0.999] | 0.184 [0.003, 0.655] | 0.999 [0.992, 1.000] | 1.000 [1.000, 1.000] | 0.350 [0.063, 0.998] | 0.140 [0.000, 0.500] |
| gemma1b__paper__url | 0.999 [0.988, 1.000] | 0.961 [0.748, 0.999] | 0.108 [0.001, 0.392] | 0.998 [0.985, 0.999] | 0.992 [0.968, 1.000] | 0.652 [0.191, 0.998] | 0.040 [0.000, 0.141] |
| qwen05b__paper__url | 0.998 [0.977, 1.000] | 0.942 [0.661, 0.998] | 0.165 [0.004, 0.598] | 0.998 [0.988, 1.000] | 0.989 [0.947, 1.000] | 0.525 [0.102, 1.000] | 0.067 [0.000, 0.294] |
| xgb__paper__todas | 0.998 [0.983, 1.000] | 0.903 [0.590, 0.999] | 0.291 [0.010, 0.485] | 0.999 [0.994, 1.000] | 0.936 [0.876, 0.993] | 0.880 [0.463, 1.000] | 0.010 [0.000, 0.041] |
| gemma1b__paper__corr | 0.997 [0.958, 1.000] | 0.952 [0.695, 0.999] | 0.133 [0.000, 0.599] | 0.998 [0.985, 0.999] | 0.989 [0.949, 1.000] | 0.400 [0.064, 1.000] | 0.112 [0.000, 0.494] |
| gemma1b__paper__todas | 0.997 [0.972, 1.000] | 0.953 [0.701, 0.999] | 0.129 [0.000, 0.571] | 0.997 [0.982, 0.999] | 0.996 [0.968, 1.000] | 0.387 [0.062, 1.000] | 0.119 [0.000, 0.517] |
| xgb__paper__url | 0.976 [0.739, 0.996] | 0.796 [0.389, 0.954] | 0.694 [0.604, 0.885] | 0.998 [0.988, 0.999] | 0.568 [0.082, 0.739] | 0.956 [0.368, 0.993] | 0.002 [0.001, 0.008] |
| xgb__paper__corr | 0.973 [0.862, 1.000] | 0.817 [0.401, 0.991] | 0.554 [0.004, 0.928] | 0.972 [0.945, 0.992] | 0.955 [0.861, 0.981] | 0.465 [0.096, 0.988] | 0.083 [0.003, 0.226] |

## Concentracao dos falsos positivos (teste, limiar da validacao)

| run | FP | dominios com FP | % dos FP nos 2 maiores | 2 maiores |
|---|---|---|---|---|
| qwen05b__paper__todas | 181 | 4 | 99% | blog.google (140), berkeley.edu (39) |
| qwen05b__paper__corr | 650 | 8 | 98% | 4shared.com (412), berkeley.edu (225) |
| gemma1b__paper__url | 380 | 5 | 98% | 4shared.com (263), berkeley.edu (111) |
| qwen05b__paper__url | 582 | 9 | 96% | 4shared.com (434), berkeley.edu (126) |
| xgb__paper__todas | 1027 | 12 | 97% | bing.com (633), blog.google (364) |
| gemma1b__paper__corr | 469 | 3 | 100% | 4shared.com (448), berkeley.edu (20) |
| gemma1b__paper__todas | 455 | 3 | 100% | 4shared.com (427), berkeley.edu (27) |
| xgb__paper__url | 2449 | 40 | 53% | bing.com (860), 4shared.com (440) |
| xgb__paper__corr | 1954 | 7 | 99% | bing.com (1405), blog.google (536) |

## Comparacoes pareadas (A - B; p corrigido por Holm)

| A | B | dAP [IC] | p AP | dF1 [IC] | p F1 | A ok/B erra : A erra/B ok (dominios) | p McNemar | AP | erros |
|---|---|---|---|---|---|---|---|---|---|
| qwen05b__paper__todas | qwen05b__paper__corr | 0.0000 [-0.0008, 0.0021] | 1.000 | 0.0444 [-0.0328, 0.2729] | 1.000 | 604 : 139 (9) | 1.000 | empate | empate |
| qwen05b__paper__todas | qwen05b__paper__url | 0.0013 [-0.0001, 0.0208] | 1.000 | 0.0385 [-0.0393, 0.2554] | 1.000 | 539 : 138 (11) | 1.000 | empate | empate |
| gemma1b__paper__todas | gemma1b__paper__corr | -0.0006 [-0.0056, 0.0204] | 1.000 | 0.0009 [-0.0047, 0.0074] | 1.000 | 33 : 23 (12) | 1.000 | empate | empate |
| gemma1b__paper__todas | gemma1b__paper__url | -0.0026 [-0.0183, 0.0018] | 1.000 | -0.0076 [-0.0636, 0.0389] | 1.000 | 95 : 174 (16) | 1.000 | empate | empate |
| xgb__paper__todas | xgb__paper__corr | 0.0248 [0.0001, 0.1223] | 0.252 | 0.0856 [0.0043, 0.1901] | 0.012 | 1124 : 67 (53) | 1.000 | empate | empate |
| xgb__paper__todas | xgb__paper__url | 0.0220 [0.0040, 0.2454] | 0.007 | 0.1066 [0.0226, 0.3179] | 0.007 | 1766 : 341 (41) | 0.578 | significativa | empate |
| qwen05b__paper__todas | gemma1b__paper__todas | 0.0031 [-0.0003, 0.0255] | 1.000 | 0.0274 [-0.0600, 0.2362] | 1.000 | 451 : 170 (12) | 1.000 | empate | empate |
| qwen05b__paper__todas | xgb__paper__todas | 0.0022 [0.0000, 0.0148] | 0.252 | 0.0777 [-0.0034, 0.3306] | 1.000 | 922 : 78 (14) | 1.000 | empate | empate |
| gemma1b__paper__todas | xgb__paper__todas | -0.0009 [-0.0191, 0.0105] | 1.000 | 0.0503 [-0.1262, 0.2985] | 1.000 | 1028 : 465 (23) | 1.000 | empate | empate |
| qwen05b__paper__corr | gemma1b__paper__corr | 0.0025 [-0.0005, 0.0385] | 1.000 | -0.0161 [-0.0995, 0.0125] | 1.000 | 53 : 227 (14) | 1.000 | empate | empate |
| qwen05b__paper__corr | xgb__paper__corr | 0.0270 [0.0001, 0.1332] | 0.252 | 0.1189 [-0.1305, 0.4274] | 1.000 | 2071 : 635 (52) | 1.000 | empate | empate |
| gemma1b__paper__corr | xgb__paper__corr | 0.0245 [-0.0052, 0.1187] | 1.000 | 0.1350 [-0.1022, 0.4742] | 1.000 | 2084 : 474 (57) | 1.000 | empate | empate |
| qwen05b__paper__url | gemma1b__paper__url | -0.0008 [-0.0129, 0.0011] | 1.000 | -0.0187 [-0.0883, -0.0002] | 0.440 | 49 : 248 (16) | 1.000 | empate | empate |
| qwen05b__paper__url | xgb__paper__url | 0.0230 [0.0041, 0.2372] | 0.007 | 0.1458 [0.0196, 0.4121] | 0.007 | 1915 : 47 (45) | 0.889 | significativa | empate |
| gemma1b__paper__url | xgb__paper__url | 0.0238 [0.0043, 0.2504] | 0.007 | 0.1645 [0.0320, 0.4501] | 0.007 | 2101 : 34 (52) | 0.682 | significativa | empate |

## Referencias

- Arp, D. et al. Dos and Don'ts of Machine Learning in Computer Security. USENIX Security, 2022.
- Axelsson, S. The base-rate fallacy and the difficulty of intrusion detection. ACM TISSEC, 2000.
- Berg-Kirkpatrick, T. et al. An Empirical Investigation of Statistical Significance in NLP. EMNLP-CoNLL, 2012.
- Dietterich, T. Approximate Statistical Tests for Comparing Supervised Classification Learning Algorithms. Neural Computation, 1998.
- Durkalski, V. L. et al. Analysis of clustered matched-pair data. Statistics in Medicine, 2003.
- Efron, B.; Tibshirani, R. An Introduction to the Bootstrap. Chapman & Hall, 1993.
- Field, C. A.; Welsh, A. H. Bootstrapping clustered data. J. R. Statist. Soc. B, 2007.
- Holm, S. A simple sequentially rejective multiple test procedure. Scand. J. Statistics, 1979.
- Koehn, P. Statistical Significance Tests for Machine Translation Evaluation. EMNLP, 2004.
- Whittaker, C.; Ryner, B.; Nazif, M. Large-Scale Automatic Classification of Phishing Pages. NDSS, 2010.
