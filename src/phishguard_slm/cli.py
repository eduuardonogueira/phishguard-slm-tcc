"""CLI do repositório de reprodução do TCC.

  phishguard dados                 baixa e prepara os conjuntos paper e br
  phishguard exp ...               matriz de experimentos (treino, avaliação, estatística)
  phishguard predict URL           classifica uma URL no terminal
  phishguard serve                 servidor local para a extensão do navegador
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from .config import Config

app = typer.Typer(
    add_completion=False,
    help="Detecção de phishing com SLMs: reprodução do TCC (UFRA, 2026).",
)
console = Console()


def _cfg(**overrides) -> Config:
    cfg = Config()
    for k, v in overrides.items():
        if v is not None:
            setattr(cfg, k, v)
    return cfg


@app.command()
def dados(
    force: bool = typer.Option(False, help="Baixa de novo mesmo se já houver cópia local."),
) -> None:
    """Baixa o CSV do trabalho-base (GitHub) e o PhishBR-URL (Kaggle) e prepara os dois."""
    from .dados import preparar

    res = preparar(force=force)
    t = Table(title="Conjuntos preparados")
    for c in ("conjunto", "linhas", "treino", "validação", "teste", "domínios em 2+ partições"):
        t.add_column(c, justify="left" if c == "conjunto" else "right")
    for nome, r in res.items():
        cont = r["particao"]["contagem"]
        t.add_row(nome, str(r["linhas"]), str(cont["train"]["total"]), str(cont["val"]["total"]),
                  str(cont["test"]["total"]), str(r["particao"]["dominios_em_mais_de_um_split"]))
    console.print(t)
    if res["br"]["duplicadas_descartadas"]:
        console.print(f"[yellow]br:[/yellow] {res['br']['duplicadas_descartadas']} linhas com URL repetida "
                      "após o mascaramento foram descartadas (ver README).")


def _modelo_do_run(run: str) -> tuple[str, Path, list[str], float]:
    """model_id, pasta do adaptador, atributos e limiar da validação de um run SLM."""
    from .experiments import RUNS_DIR

    rd = RUNS_DIR / run
    man_path = rd / "manifest.json"
    if not man_path.exists():
        raise typer.BadParameter(f"run desconhecido: {run}")
    man = json.loads(man_path.read_text())
    if man["modelo"] == "xgb":
        raise typer.BadParameter("o servidor e o predict usam SLMs; escolha um run qwen05b ou gemma1b")
    if not (rd / "adapter").exists():
        raise typer.BadParameter(f"{rd / 'adapter'} não existe: treine o run antes (phishguard exp train)")
    ev = rd / "evals" / f"{man['dataset']}.json"
    thr = json.loads(ev.read_text())["limiar_validacao"] if ev.exists() else 0.5
    return man["model_id"], rd / "adapter", man["feature_columns"], thr


@app.command()
def predict(
    url: str,
    run: Optional[str] = typer.Option(None, help="Run da matriz (ex.: qwen05b__br__todas). Padrão: outputs/adapter."),
    no_adapter: bool = typer.Option(False, help="Usar o modelo base, sem LoRA."),
    threshold: Optional[float] = typer.Option(None, help="Limiar P(phishing). Padrão: 0,5 ou o da validação do run."),
) -> None:
    """Classifica uma única URL (só o texto da URL, sem atributos de rede)."""
    from .scoring import PhishClassifier

    cfg = _cfg()
    adapter, cols = cfg.adapter_dir, None
    if run:
        cfg.model_id, adapter, cols, thr = _modelo_do_run(run)
        cfg.threshold = thr
    if threshold is not None:
        cfg.threshold = threshold
    kw = {"feature_columns": cols} if cols is not None else {}
    clf = PhishClassifier(cfg, adapter_dir=None if no_adapter else adapter, prefer_cpu=True, **kw)
    pred = clf.predict(url)
    verdict = "PHISHING" if pred.label == 1 else "LEGITIMA"
    console.print(
        f"[bold]{verdict}[/bold]  P(phishing)={pred.prob_phishing:.3f}  limiar={cfg.threshold:.2f}  "
        f"({pred.latency_ms:.0f} ms, {clf.device})"
    )


@app.command()
def serve(
    run: Optional[str] = typer.Option(None, help="Run da matriz a servir. Padrão: outputs/adapter (o do TCC)."),
    no_adapter: bool = typer.Option(False, help="Servir com o modelo base (sem LoRA)."),
    threshold: Optional[float] = typer.Option(None, help="Limiar P(phishing). Padrão: 0,5 ou o da validação do run."),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(5000),
) -> None:
    """Sobe o servidor Flask local usado pela extensão do navegador."""
    from .config import FEATURE_COLUMNS
    from .server import serve as run_serve

    cfg = _cfg()
    adapter, cols = None, FEATURE_COLUMNS
    if run:
        cfg.model_id, adapter, cols, thr = _modelo_do_run(run)
        cfg.threshold = thr
    if threshold is not None:
        cfg.threshold = threshold
    run_serve(cfg, use_adapter=not no_adapter, host=host, port=port, adapter_dir=adapter,
              feature_columns=cols)


# ---------------------------------------------------------------------------
# Experimentos (matriz modelo x dataset x features)
# ---------------------------------------------------------------------------
exp_app = typer.Typer(help="Matriz de experimentos: treina cada combinacao 1x e avalia no teste do proprio dataset.")
app.add_typer(exp_app, name="exp")

_MODELS_HELP = "Modelos: qwen05b, gemma1b, xgb (repita a opcao; padrao: todos)."


@exp_app.command("splits")
def exp_splits(
    dataset: str = typer.Argument(..., help="paper | br"),
    force: bool = typer.Option(False, help="Recria a particao (invalida os runs desse dataset)."),
) -> None:
    """Cria e congela a particao 70/15/15 por dominio."""
    from .experiments import make_splits

    console.print_json(data=make_splits(dataset, force=force))


@exp_app.command("features")
def exp_features(
    min_rotulo: float = typer.Option(0.2, help="|rho| minimo com o rotulo (abaixo = fraca)."),
    max_par: float = typer.Option(0.6, help="|rho| entre duas features a partir do qual uma e redundante."),
    force: bool = typer.Option(False, help="Recalcula (invalida os runs 'corr')."),
    dataset: str = typer.Argument("paper", help="paper | br: o treino de onde sai o 'corr'."),
) -> None:
    """Seleciona o conjunto 'corr' pela correlacao de Spearman no treino do proprio dataset."""
    from .experiments import select_corr

    res = select_corr(dataset, min_rotulo, max_par, force)
    t = Table(title=f"rho com o rotulo (treino de {dataset}) -> corr = {res['sets']['corr']}")
    t.add_column("feature")
    t.add_column("rho", justify="right")
    t.add_column("decisao")
    for k, v in sorted(res["rho_com_rotulo"].items(), key=lambda kv: -abs(kv[1])):
        t.add_row(k, f"{v:+.3f}", "mantida" if k in res["sets"]["corr"] else res["descartadas_corr"].get(k, ""))
    console.print(t)


def _report_sigint() -> None:
    """Diz quem mandou o SIGINT (Ctrl+C) antes de interromper. pid 0 = veio do terminal.

    O SIGINT fica bloqueado nas threads e uma thread de vigia o recebe com
    sigwaitinfo (que informa o remetente), imprime e interrompe o processo.
    """
    import signal
    import sys
    import threading

    if not hasattr(signal, "sigwaitinfo"):  # macOS/Windows: segue o padrao
        return
    signal.pthread_sigmask(signal.SIG_BLOCK, [signal.SIGINT])

    def watch() -> None:
        import _thread

        info = signal.sigwaitinfo([signal.SIGINT])
        who = "o terminal (teclado/cliente SSH)" if info.si_pid == 0 else f"o pid {info.si_pid}"
        try:
            cmd = Path(f"/proc/{info.si_pid}/cmdline").read_bytes().replace(b"\0", b" ").decode().strip()
        except OSError:
            cmd = ""
        print(f"\n[exp] SIGINT (Ctrl+C) enviado por {who}, uid {info.si_uid}" + (f": {cmd}" if cmd else ""),
              file=sys.stderr, flush=True)
        _thread.interrupt_main()

    threading.Thread(target=watch, daemon=True, name="sigint-watch").start()


@exp_app.command("train")
def exp_train(
    model: Optional[list[str]] = typer.Option(None, "--model", "-m", help=_MODELS_HELP),
    dataset: Optional[list[str]] = typer.Option(None, "--dataset", "-d", help="paper, br (padrao: todos os que existem)."),
    features: Optional[list[str]] = typer.Option(None, "--features", "-f", help="todas, corr, url (padrao: todos)."),
    epochs: int = typer.Option(1),
    lr: float = typer.Option(2e-4),
    batch: int = typer.Option(8, help="Batch por passo. Menor = menos memoria de GPU; o acumulo de "
                              "gradiente sobe para manter o batch efetivo de 16 (mesmo resultado)."),
    max_samples: Optional[int] = typer.Option(None, help="Limite de exemplos de treino (smoke test)."),
    force: bool = typer.Option(False, help="Retreina mesmo se o run ja existir."),
    avaliar: bool = typer.Option(True, help="Avalia no teste do proprio dataset logo apos treinar."),
) -> None:
    """Treina as combinacoes pedidas; pula as que ja existem."""
    import os

    from .experiments import eval_run, matrix, train_run

    _report_sigint()
    # GPU compartilhada: reduz fragmentacao quando outros processos ocupam memoria.
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    efetivo = Config().batch_size * Config().grad_accum
    if efetivo % batch:
        raise typer.BadParameter(f"--batch precisa dividir o batch efetivo ({efetivo})")
    for m, d, f in matrix(model, dataset, features):
        cfg = _cfg(epochs=epochs, learning_rate=lr, batch_size=batch, grad_accum=efetivo // batch,
                   max_train_samples=max_samples)
        console.rule(f"{m} | {d} | {f}")
        run_dir = train_run(m, d, f, cfg, force=force)
        if avaliar:
            eval_run(run_dir.name, [d], _cfg())


@exp_app.command("eval")
def exp_eval(
    run: Optional[list[str]] = typer.Option(None, "--run", "-r", help="Nome do run (padrao: todos os treinados)."),
    max_samples: Optional[int] = typer.Option(None, help="Avaliacao parcial (teste rapido)."),
    force: bool = typer.Option(False, help="Refaz avaliacoes existentes."),
) -> None:
    """Avalia runs ja treinados (sem retreinar) nos conjuntos de teste."""
    from .experiments import RUNS_DIR, _manifest, eval_run

    runs = run or sorted(p.parent.name for p in RUNS_DIR.glob("*/manifest.json"))
    for r in runs:
        own = (_manifest(RUNS_DIR / r) or {}).get("dataset")
        eval_run(r, [own], _cfg(), max_samples=max_samples, force=force)


@exp_app.command("status")
def exp_status() -> None:
    """Mostra o que ja foi treinado e avaliado na matriz."""
    from .experiments import status

    df = status()
    t = Table(title="Matriz de experimentos")
    for c in df.columns:
        t.add_column(c)
    for r in df.itertuples(index=False):
        t.add_row(*[str(v) for v in r])
    console.print(t)


@exp_app.command("stats")
def exp_stats(
    dataset: Optional[list[str]] = typer.Option(None, "--dataset", "-d", help="paper, br (padrao: todos)."),
    n_boot: int = typer.Option(2000, "--boot", help="Reamostragens do bootstrap."),
    precisao: float = typer.Option(0.9, help="Precisao-alvo do ponto de operacao (teste realista)."),
) -> None:
    """T4: IC por bootstrap, ponto de operacao e comparacoes pareadas (bootstrap + McNemar + Holm)."""
    from .config import OUTPUTS
    from .config import URL_COLUMN
    from .experiments import RUNS_DIR, available, load
    from .stats import analyze, write

    for d in dataset or available():
        console.rule(f"stats | {d}")
        ds = load(d)  # dominio registrado de cada URL (o mesmo grupo usado na particao)
        groups = dict(zip(ds[URL_COLUMN], ds["dominio"].fillna(ds[URL_COLUMN])))
        res = analyze(RUNS_DIR, d, n_boot=n_boot, target_precision=precisao, seed=_cfg().seed, groups=groups)
        if res["faltando"]:
            console.print(f"[yellow]sem probabilidades por URL (rode 'phishguard exp eval -t {d}'):[/yellow] "
                          + ", ".join(res["faltando"]))
        if res["runs"].empty:
            continue
        t = Table(title=f"{d}: IC 95% (bootstrap, B={n_boot})")
        for c in ("run", "AP", "F1", "FPR", f"recall realista (limiar p/ P>={precisao:.0%} na val)"):
            t.add_column(c)
        for _, r in res["runs"].iterrows():
            ic = lambda k: (f"{r[k]:.3f} [{r[k + '_ic_inf']:.3f}, {r[k + '_ic_sup']:.3f}]"
                            if k in r and pd.notna(r[k]) else "-")
            t.add_row(r["run"], ic("ap"), ic("f1"), ic("fpr"), ic("op_recall"))
        console.print(t)
        if len(res["pares"]):
            t = Table(title=f"{d}: comparacoes pareadas (p corrigido por Holm)")
            for c in ("A", "B", "dAP", "p AP", "dF1", "p F1", "p McNemar", "AP", "erros"):
                t.add_column(c)
            for _, r in res["pares"].iterrows():
                t.add_row(r["a"], r["b"], f"{r['delta_ap']:+.4f}", f"{r['p_ap_holm']:.3f}", f"{r['delta_f1']:+.4f}",
                          f"{r['p_f1_holm']:.3f}", f"{r['p_mcnemar_holm']:.3f}", r["diferenca_ap"],
                          r["diferenca_erros"])
            console.print(t)
        for pth in write(res, OUTPUTS / "stats"):
            console.print(f"[green]salvo em[/green] {pth}")


@exp_app.command("leaderboard")
def exp_leaderboard(
) -> None:
    """Junta as avaliacoes (treino e teste no mesmo dataset) em outputs/leaderboard.csv e .md."""
    from .experiments import LEADERBOARD_CSV, leaderboard

    df = leaderboard()
    if len(df) <= 1:
        console.print("[yellow]Nenhuma avaliacao em outputs/runs/*/evals/ ainda.[/yellow] "
                      "Veja o que falta com: phishguard exp status")
    cols = ["run", "teste", "n_features", "average_precision", "f1", "precision", "recall", "fpr", "lat_p95_ms"]
    df = df.reindex(columns=cols)
    t = Table(title="Leaderboard (limiar da validacao; particao por dominio)")
    for c in cols:
        t.add_column(c)
    for r in df[cols].itertuples(index=False):
        t.add_row(*["" if pd.isna(v) else str(v) for v in r])
    console.print(t)
    console.print(f"[green]salvo em[/green] {LEADERBOARD_CSV}")

