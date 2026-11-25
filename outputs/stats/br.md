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
| qwen05b__br__todas | 0.985 [0.968, 0.993] | 0.933 [0.884, 0.961] | 0.038 [0.008, 0.074] | 0.919 [0.869, 0.948] | 0.913 [0.857, 0.950] | 0.940 [0.883, 0.979] | 0.643 [0.423, 0.885] | 0.039 [0.009, 0.079] |
| qwen05b__br__corr | 0.976 [0.947, 0.994] | 0.937 [0.888, 0.968] | 0.038 [0.009, 0.076] | 0.928 [0.879, 0.960] | 0.912 [0.858, 0.949] | 0.929 [0.864, 0.973] | 0.643 [0.422, 0.886] | 0.039 [0.009, 0.077] |
| gemma1b__br__todas | 0.975 [0.951, 0.991] | 0.927 [0.891, 0.953] | 0.033 [0.007, 0.066] | 0.903 [0.864, 0.943] | 0.908 [0.859, 0.945] | 0.918 [0.873, 0.968] | 0.643 [0.425, 0.889] | 0.038 [0.009, 0.078] |
| qwen05b__br__url | 0.974 [0.941, 0.989] | 0.915 [0.829, 0.963] | 0.041 [0.012, 0.078] | 0.891 [0.764, 0.959] | 0.927 [0.895, 0.954] | 0.788 [0.645, 0.891] | 0.644 [0.398, 0.926] | 0.033 [0.005, 0.071] |
| gemma1b__br__corr | 0.973 [0.947, 0.990] | 0.955 [0.918, 0.975] | 0.028 [0.010, 0.059] | 0.950 [0.913, 0.970] | 0.910 [0.856, 0.948] | 0.929 [0.886, 0.976] | 0.728 [0.503, 0.905] | 0.026 [0.008, 0.058] |
| gemma1b__br__url | 0.971 [0.952, 0.986] | 0.931 [0.891, 0.955] | 0.042 [0.014, 0.076] | 0.922 [0.892, 0.947] | 0.901 [0.849, 0.937] | 0.815 [0.707, 0.932] | 0.688 [0.478, 0.892] | 0.028 [0.007, 0.059] |
| xgb__br__todas | 0.920 [0.858, 0.965] | 0.799 [0.644, 0.897] | 0.048 [0.020, 0.084] | 0.709 [0.508, 0.857] | 0.859 [0.794, 0.912] | 0.652 [0.534, 0.777] | 0.645 [0.413, 0.865] | 0.027 [0.008, 0.059] |
| xgb__br__corr | 0.834 [0.755, 0.898] | 0.719 [0.573, 0.820] | 0.103 [0.070, 0.142] | 0.641 [0.457, 0.784] | 0.830 [0.770, 0.880] | sem limiar | | |
| xgb__br__url | 0.744 [0.666, 0.818] | 0.668 [0.539, 0.773] | 0.114 [0.098, 0.131] | 0.580 [0.413, 0.739] | 0.708 [0.625, 0.780] | 0.071 [0.019, 0.135] | 0.619 [0.250, 0.857] | 0.003 [0.001, 0.006] |

## Concentracao dos falsos positivos (teste, limiar da validacao)

| run | FP | dominios com FP | % dos FP nos 2 maiores | 2 maiores |
|---|---|---|---|---|
| qwen05b__br__todas | 92 | 21 | 71% | 2mdn.net (33), brandcdn.com (32) |
| qwen05b__br__corr | 94 | 23 | 69% | 2mdn.net (33), brandcdn.com (32) |
| gemma1b__br__todas | 80 | 20 | 69% | 2mdn.net (33), brandcdn.com (22) |
| qwen05b__br__url | 100 | 35 | 65% | 2mdn.net (33), brandcdn.com (32) |
| gemma1b__br__corr | 69 | 29 | 59% | 2mdn.net (33), essa-vale-a-pena-ver.blogspot.com (8) |
| gemma1b__br__url | 102 | 35 | 59% | brandcdn.com (32), 2mdn.net (28) |
| xgb__br__todas | 118 | 35 | 49% | 2mdn.net (33), brandcdn.com (25) |
| xgb__br__corr | 251 | 115 | 26% | 2mdn.net (33), brandcdn.com (32) |
| xgb__br__url | 279 | 210 | 4% | essa-vale-a-pena-ver.blogspot.com (8), 3isolucoes.com.br (2) |

## Comparacoes pareadas (A - B; p corrigido por Holm)

| A | B | dAP [IC] | p AP | dF1 [IC] | p F1 | A ok/B erra : A erra/B ok (dominios) | p McNemar | AP | erros |
|---|---|---|---|---|---|---|---|---|---|
| qwen05b__br__todas | qwen05b__br__corr | 0.0094 [-0.0037, 0.0296] | 1.000 | -0.0046 [-0.0210, 0.0156] | 1.000 | 65 : 80 (66) | 1.000 | empate | empate |
| qwen05b__br__todas | qwen05b__br__url | 0.0107 [0.0016, 0.0304] | 0.098 | 0.0176 [-0.0236, 0.0861] | 1.000 | 168 : 110 (95) | 1.000 | empate | empate |
| gemma1b__br__todas | gemma1b__br__corr | 0.0022 [-0.0035, 0.0093] | 1.000 | -0.0284 [-0.0504, -0.0047] | 0.048 | 23 : 118 (43) | 0.657 | empate | empate |
| gemma1b__br__todas | gemma1b__br__url | 0.0043 [-0.0161, 0.0216] | 1.000 | -0.0046 [-0.0214, 0.0164] | 1.000 | 75 : 87 (79) | 1.000 | empate | empate |
| xgb__br__todas | xgb__br__corr | 0.0854 [0.0473, 0.1342] | 0.007 | 0.0799 [0.0314, 0.1329] | 0.007 | 334 : 79 (158) | 0.018 | significativa | significativa |
| xgb__br__todas | xgb__br__url | 0.1754 [0.0663, 0.2772] | 0.007 | 0.1309 [-0.0983, 0.3426] | 1.000 | 764 : 374 (402) | 1.000 | significativa | empate |
| qwen05b__br__todas | gemma1b__br__todas | 0.0100 [-0.0032, 0.0295] | 1.000 | 0.0057 [-0.0160, 0.0243] | 1.000 | 70 : 53 (50) | 1.000 | empate | empate |
| qwen05b__br__todas | xgb__br__todas | 0.0655 [0.0261, 0.1207] | 0.007 | 0.1337 [0.0433, 0.2867] | 0.007 | 445 : 47 (122) | 0.387 | significativa | empate |
| gemma1b__br__todas | xgb__br__todas | 0.0555 [0.0185, 0.1129] | 0.007 | 0.1280 [0.0215, 0.2917] | 0.036 | 460 : 79 (127) | 0.493 | significativa | empate |
| qwen05b__br__corr | gemma1b__br__corr | 0.0028 [-0.0124, 0.0124] | 1.000 | -0.0181 [-0.0493, 0.0014] | 0.497 | 38 : 101 (44) | 0.852 | empate | empate |
| qwen05b__br__corr | xgb__br__corr | 0.1415 [0.0856, 0.2120] | 0.007 | 0.2182 [0.1201, 0.3650] | 0.007 | 719 : 51 (190) | 0.024 | significativa | significativa |
| gemma1b__br__corr | xgb__br__corr | 0.1387 [0.0795, 0.2112] | 0.007 | 0.2363 [0.1378, 0.3814] | 0.007 | 759 : 28 (186) | 0.011 | significativa | significativa |
| qwen05b__br__url | gemma1b__br__url | 0.0036 [-0.0198, 0.0153] | 1.000 | -0.0165 [-0.0886, 0.0211] | 1.000 | 89 : 142 (72) | 1.000 | empate | empate |
| qwen05b__br__url | xgb__br__url | 0.2301 [0.1520, 0.3066] | 0.007 | 0.2470 [0.0814, 0.4119] | 0.020 | 938 : 208 (403) | 0.299 | significativa | empate |
| gemma1b__br__url | xgb__br__url | 0.2266 [0.1587, 0.2965] | 0.007 | 0.2634 [0.1548, 0.3952] | 0.007 | 902 : 119 (408) | 0.084 | significativa | empate |

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
