# Estatistica - teste br

Teste: 4221 URLs de 1964 dominios; realista: 2630 (7.0% phishing).

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

| run | AP | F1 | FPR | recall | F1 conferidas | realista no limiar p/ P>=90% (val): recall | precisao | FPR |
|---|---|---|---|---|---|---|---|---|
| qwen05b__br__todas | 0.978 [0.957, 0.991] | 0.926 [0.876, 0.958] | 0.043 [0.014, 0.079] | 0.914 [0.856, 0.951] | 0.926 [0.885, 0.957] | 0.946 [0.900, 0.984] | 0.624 [0.412, 0.847] | 0.043 [0.014, 0.082] |
| qwen05b__br__url | 0.977 [0.943, 0.991] | 0.940 [0.891, 0.966] | 0.042 [0.012, 0.079] | 0.937 [0.894, 0.959] | 0.906 [0.850, 0.943] | 0.897 [0.831, 0.942] | 0.637 [0.413, 0.890] | 0.038 [0.009, 0.078] |
| gemma1b__br__corr | 0.975 [0.955, 0.989] | 0.947 [0.904, 0.970] | 0.044 [0.015, 0.081] | 0.953 [0.923, 0.970] | 0.913 [0.860, 0.949] | 0.946 [0.907, 0.985] | 0.644 [0.435, 0.874] | 0.039 [0.011, 0.078] |
| gemma1b__br__todas | 0.974 [0.956, 0.988] | 0.933 [0.892, 0.958] | 0.038 [0.008, 0.074] | 0.919 [0.885, 0.947] | 0.911 [0.859, 0.948] | 0.940 [0.904, 0.978] | 0.638 [0.427, 0.875] | 0.040 [0.011, 0.080] |
| qwen05b__br__corr | 0.973 [0.951, 0.989] | 0.942 [0.894, 0.969] | 0.043 [0.013, 0.080] | 0.943 [0.899, 0.966] | 0.913 [0.858, 0.951] | 0.935 [0.879, 0.974] | 0.628 [0.415, 0.859] | 0.042 [0.012, 0.081] |
| gemma1b__br__url | 0.963 [0.939, 0.985] | 0.937 [0.895, 0.961] | 0.046 [0.016, 0.083] | 0.937 [0.910, 0.956] | 0.917 [0.864, 0.952] | 0.821 [0.728, 0.925] | 0.634 [0.426, 0.881] | 0.036 [0.008, 0.072] |
| xgb__br__todas | 0.919 [0.857, 0.965] | 0.821 [0.669, 0.915] | 0.063 [0.032, 0.100] | 0.757 [0.553, 0.900] | 0.850 [0.786, 0.902] | 0.625 [0.516, 0.749] | 0.646 [0.407, 0.873] | 0.026 [0.007, 0.058] |
| xgb__br__corr | 0.833 [0.755, 0.897] | 0.719 [0.573, 0.820] | 0.103 [0.071, 0.142] | 0.641 [0.457, 0.784] | 0.830 [0.770, 0.880] | sem limiar | | |
| xgb__br__url | 0.746 [0.666, 0.821] | 0.656 [0.529, 0.764] | 0.099 [0.084, 0.115] | 0.555 [0.397, 0.709] | 0.691 [0.608, 0.765] | 0.071 [0.019, 0.135] | 0.619 [0.250, 0.857] | 0.003 [0.001, 0.006] |

## Concentracao dos falsos positivos (teste, limiar da validacao)

| run | FP | dominios com FP | % dos FP nos 2 maiores | 2 maiores |
|---|---|---|---|---|
| qwen05b__br__todas | 105 | 33 | 62% | 2mdn.net (33), brandcdn.com (32) |
| qwen05b__br__url | 102 | 29 | 64% | 2mdn.net (33), brandcdn.com (32) |
| gemma1b__br__corr | 108 | 36 | 60% | 2mdn.net (33), brandcdn.com (32) |
| gemma1b__br__todas | 92 | 22 | 71% | 2mdn.net (33), brandcdn.com (32) |
| qwen05b__br__corr | 105 | 33 | 62% | 2mdn.net (33), brandcdn.com (32) |
| gemma1b__br__url | 113 | 41 | 58% | 2mdn.net (33), brandcdn.com (32) |
| xgb__br__todas | 153 | 58 | 42% | 2mdn.net (33), brandcdn.com (31) |
| xgb__br__corr | 252 | 116 | 26% | 2mdn.net (33), brandcdn.com (32) |
| xgb__br__url | 242 | 182 | 4% | essa-vale-a-pena-ver.blogspot.com (8), 3isolucoes.com.br (2) |

## Comparacoes pareadas (A - B; p corrigido por Holm)

| A | B | dAP [IC] | p AP | dF1 [IC] | p F1 | A ok/B erra : A erra/B ok (dominios) | p McNemar | AP | erros |
|---|---|---|---|---|---|---|---|---|---|
| qwen05b__br__todas | qwen05b__br__corr | 0.0045 [-0.0093, 0.0180] | 1.000 | -0.0154 [-0.0394, 0.0059] | 1.000 | 45 : 96 (53) | 1.000 | empate | empate |
| qwen05b__br__todas | qwen05b__br__url | 0.0008 [-0.0054, 0.0165] | 1.000 | -0.0132 [-0.0402, 0.0124] | 1.000 | 82 : 126 (89) | 1.000 | empate | empate |
| gemma1b__br__todas | gemma1b__br__corr | -0.0006 [-0.0047, 0.0059] | 1.000 | -0.0140 [-0.0239, -0.0028] | 0.064 | 28 : 73 (56) | 0.729 | empate | empate |
| gemma1b__br__todas | gemma1b__br__url | 0.0114 [-0.0017, 0.0281] | 0.749 | -0.0044 [-0.0148, 0.0084] | 1.000 | 62 : 74 (85) | 1.000 | empate | empate |
| xgb__br__todas | xgb__br__corr | 0.0857 [0.0486, 0.1331] | 0.007 | 0.1024 [0.0481, 0.1699] | 0.007 | 374 : 69 (160) | 0.024 | significativa | significativa |
| xgb__br__todas | xgb__br__url | 0.1733 [0.0621, 0.2761] | 0.007 | 0.1649 [-0.0633, 0.3719] | 1.000 | 784 : 337 (403) | 1.000 | significativa | empate |
| qwen05b__br__todas | gemma1b__br__todas | 0.0035 [-0.0100, 0.0143] | 1.000 | -0.0062 [-0.0365, 0.0125] | 1.000 | 61 : 83 (55) | 1.000 | empate | empate |
| qwen05b__br__todas | xgb__br__todas | 0.0587 [0.0222, 0.1093] | 0.007 | 0.1052 [0.0141, 0.2608] | 0.063 | 412 : 85 (135) | 0.729 | significativa | empate |
| gemma1b__br__todas | xgb__br__todas | 0.0552 [0.0162, 0.1163] | 0.007 | 0.1114 [0.0197, 0.2675] | 0.020 | 418 : 69 (142) | 0.698 | significativa | empate |
| qwen05b__br__corr | gemma1b__br__corr | -0.0017 [-0.0115, 0.0055] | 1.000 | -0.0048 [-0.0179, 0.0026] | 1.000 | 34 : 50 (45) | 1.000 | empate | empate |
| qwen05b__br__corr | xgb__br__corr | 0.1399 [0.0830, 0.2104] | 0.007 | 0.2230 [0.1288, 0.3678] | 0.007 | 716 : 33 (189) | 0.020 | significativa | significativa |
| gemma1b__br__corr | xgb__br__corr | 0.1416 [0.0823, 0.2148] | 0.007 | 0.2279 [0.1303, 0.3742] | 0.007 | 736 : 37 (183) | 0.016 | significativa | significativa |
| qwen05b__br__url | gemma1b__br__url | 0.0141 [-0.0095, 0.0299] | 1.000 | 0.0026 [-0.0117, 0.0120] | 1.000 | 55 : 45 (62) | 1.000 | empate | empate |
| qwen05b__br__url | xgb__br__url | 0.2311 [0.1534, 0.3092] | 0.007 | 0.2833 [0.1655, 0.4258] | 0.007 | 935 : 117 (400) | 0.109 | significativa | empate |
| gemma1b__br__url | xgb__br__url | 0.2170 [0.1455, 0.2899] | 0.007 | 0.2807 [0.1688, 0.4152] | 0.007 | 928 : 120 (409) | 0.089 | significativa | empate |

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
