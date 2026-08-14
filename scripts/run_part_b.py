"""Reproduce your Part B results. Run from the project root:

    python scripts/run_part_b.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src import data_access, etl, features, fusion, portfolios, robustness, sentiment  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "results" / "data"
FIG_DIR = ROOT / "results" / "figures"
TAB_DIR = ROOT / "results" / "tables"

# Fixed categorical palette (validated order - see the dataviz skill), used
# instead of matplotlib defaults for every figure below.
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
POS, NEG = "#2a78d6", "#e34948"

FUND_SPECS = [
    ("equity", "min_variance"), ("equity", "max_sharpe"), ("equity", "equal_weight"),
    ("crypto", "min_variance"), ("crypto", "max_sharpe"), ("crypto", "equal_weight"),
    ("combined", "min_variance"), ("combined", "max_sharpe"), ("combined", "equal_weight"),
]
K_SENSITIVITY = [0.25, 0.5, 1.0]


def _style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#e5e4e0", linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def build_return_matrices():
    eq = etl.load_clean_equities()
    cr = etl.load_clean_crypto()
    wide_eq = features.daily_returns(eq).pivot(index="date", columns="ticker", values="ret").dropna(how="any")
    wide_cr = features.daily_returns(cr).pivot(index="date", columns="ticker", values="ret").dropna(how="any")
    # crypto returns computed on its own calendar first, then left-merged onto
    # the equity trading calendar for the combined fund (DATA_GUIDE.md rule)
    combined = wide_eq.join(wide_cr, how="left").dropna(how="any")
    return wide_eq, wide_cr, combined


def run_funds(wide_eq, wide_cr, combined):
    universes = {
        "equity": (wide_eq, 252, 252),
        "crypto": (wide_cr, 365, 365),
        "combined": (combined, 252, 252),
    }
    results = {}
    for family, method in FUND_SPECS:
        wide, window, ppy = universes[family]
        bt = portfolios.oos_backtest(wide, method=method, window=window, periods_per_year=ppy)
        metrics = portfolios.performance_metrics(bt["daily_returns"], periods_per_year=ppy)
        fund_name = f"{family}_{method}"
        results[fund_name] = {"family": family, "method": method, "ppy": ppy, **bt, "metrics": metrics}
        print(f"[funds] {fund_name}: first live {bt['first_live_date'].date()}, "
              f"Sharpe {metrics['sharpe']:.2f}")
    return results


def run_sentiment():
    nh = data_access.load_news_headlines()
    panel = features.assemble_headline_panel(nh)
    scored_vanilla = sentiment.score_headlines(panel, use_extended_lexicon=False)
    scored_ext = sentiment.score_headlines(panel, use_extended_lexicon=True)
    neutral_rates = {
        "vanilla_neutral_rate": float((scored_vanilla["compound"] == 0).mean()),
        "extended_neutral_rate": float((scored_ext["compound"] == 0).mean()),
    }
    print(f"[sentiment] neutral rate: vanilla {neutral_rates['vanilla_neutral_rate']:.1%} "
          f"-> extended {neutral_rates['extended_neutral_rate']:.1%}")
    return {
        "tsi_vanilla": sentiment.ticker_sentiment_index(scored_vanilla),
        "tsi_ext": sentiment.ticker_sentiment_index(scored_ext),
        "sector_vanilla": sentiment.sector_sentiment_index(scored_vanilla),
        "sector_ext": sentiment.sector_sentiment_index(scored_ext),
        "neutral_rates": neutral_rates,
    }


def run_fusion(fund_results, wide_eq, sent):
    rows = []
    fusion_outputs = {}
    equity_funds = {n: r for n, r in fund_results.items() if r["family"] == "equity"}

    for name, r in equity_funds.items():
        rows.append({"fund": name, "variant": "base", "k": None, **r["metrics"]})

        for variant, tsi in [("vanilla_tilt", sent["tsi_vanilla"]), ("extended_tilt", sent["tsi_ext"])]:
            tw = fusion.apply_sentiment(r["weights"], tsi, k=fusion.TILT_INTENSITY)
            bt = portfolios.weights_to_backtest(tw, wide_eq)
            m = portfolios.performance_metrics(bt["daily_returns"])
            rows.append({"fund": name, "variant": variant, "k": fusion.TILT_INTENSITY, **m})
            if name == "equity_min_variance" and variant == "extended_tilt":
                fusion_outputs["headline"] = {"base": r, "tilted_bt": bt, "tilted_weights": tw}

        for k in K_SENSITIVITY:
            tw = fusion.apply_sentiment(r["weights"], sent["tsi_ext"], k=k)
            bt = portfolios.weights_to_backtest(tw, wide_eq)
            m = portfolios.performance_metrics(bt["daily_returns"])
            rows.append({"fund": name, "variant": "extended_tilt_ksens", "k": k, **m})

    fusion_df = pd.DataFrame(rows)
    base_sharpe = fusion_df.loc[(fusion_df["fund"] == "equity_min_variance")
                                 & (fusion_df["variant"] == "base"), "sharpe"].iloc[0]
    ext_sharpe = fusion_df.loc[(fusion_df["fund"] == "equity_min_variance")
                                & (fusion_df["variant"] == "extended_tilt"), "sharpe"].iloc[0]
    print(f"[fusion] equity_min_variance: base Sharpe {base_sharpe:.2f} "
          f"-> extended_tilt Sharpe {ext_sharpe:.2f}")
    return fusion_df, fusion_outputs


def run_robustness(fund_results, wide_eq, sent):
    """Two checks the fusion comparison alone can't answer: does lagged
    sentiment actually predict future returns, and does the real
    ticker-level sentiment mapping beat a randomised placebo. See
    src/robustness.py."""
    eq = etl.load_clean_equities()
    daily_ret_long = features.daily_returns(eq)
    pred_power = robustness.predictive_power(sent["tsi_ext"], daily_ret_long)
    print("[robustness] predictive power:\n" + pred_power.to_string(index=False))

    equity_funds = {n: r for n, r in fund_results.items() if r["family"] == "equity"}
    placebo_rows = []
    tilt_corr_rows = []
    for name, r in equity_funds.items():
        placebo = robustness.placebo_test(r["weights"], sent["tsi_ext"], wide_eq)
        placebo_rows.append({"fund": name, **placebo})
        print(f"[robustness] {name} placebo: real Sharpe {placebo['real_sharpe']:.3f}, "
              f"shuffle mean {placebo['shuffle_mean']:.3f} +/- {placebo['shuffle_std']:.3f}, "
              f"real at {placebo['percentile']:.0f}th percentile")

        tilt_corr = robustness.weight_tilt_correlation(r["weights"], sent["tsi_ext"])
        tilt_corr_rows.append({"fund": name, **tilt_corr})

    return pred_power, pd.DataFrame(placebo_rows), pd.DataFrame(tilt_corr_rows)


def plot_growth_of_1(fund_results):
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, method in enumerate(["min_variance", "max_sharpe", "equal_weight"]):
        r = fund_results[f"combined_{method}"]
        ax.plot(r["growth_of_1"].index, r["growth_of_1"].values, color=CAT[i], linewidth=2,
                label=method.replace("_", " "))
    _style(ax)
    ax.set_title("Growth of $1 - combined equity+crypto funds")
    ax.set_ylabel("Value of $1 invested")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "growth_of_1_combined.png", dpi=150)
    plt.close(fig)


def plot_drawdown(fund_results):
    r = fund_results["combined_min_variance"]
    wealth = r["growth_of_1"]
    drawdown = wealth / wealth.cummax() - 1
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.fill_between(drawdown.index, drawdown.values, 0, color=NEG, alpha=0.35)
    ax.plot(drawdown.index, drawdown.values, color=NEG, linewidth=1.2)
    _style(ax)
    ax.set_title("Drawdown - combined min-variance fund")
    ax.set_ylabel("Drawdown")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "drawdown_combined_min_variance.png", dpi=150)
    plt.close(fig)


def plot_weights_over_time(fund_results):
    r = fund_results["equity_min_variance"]
    sector_map = data_access.load_sector_universe().set_index("ticker")["sector"]
    w = r["weights"].copy()
    w_by_sector = w.T.groupby(sector_map.reindex(w.columns)).sum().T

    avg = w_by_sector.mean().sort_values(ascending=False)
    top = avg.index[:7].tolist()
    other = [c for c in w_by_sector.columns if c not in top]
    plot_df = w_by_sector[top].copy()
    if other:
        plot_df["Other"] = w_by_sector[other].sum(axis=1)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.stackplot(plot_df.index, plot_df.values.T, labels=plot_df.columns,
                 colors=CAT[:len(plot_df.columns)], alpha=0.9)
    _style(ax)
    ax.set_title("Weights over time (by sector) - equity min-variance fund")
    ax.set_ylabel("Weight")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "weights_over_time_equity_min_variance.png", dpi=150)
    plt.close(fig)


def plot_sharpe_barplot(performance_metrics):
    families = ["equity", "crypto", "combined"]
    methods = ["min_variance", "max_sharpe", "equal_weight"]
    fig, ax = plt.subplots(figsize=(9, 5))
    x = range(len(families))
    width = 0.25
    for i, method in enumerate(methods):
        vals = [performance_metrics.loc[(performance_metrics["asset_family"] == fam)
                                         & (performance_metrics["method"] == method), "sharpe"].iloc[0]
                for fam in families]
        ax.bar([xi + (i - 1) * width for xi in x], vals, width=width, color=CAT[i],
               label=method.replace("_", " "))
    _style(ax)
    ax.set_xticks(list(x))
    ax.set_xticklabels(families)
    ax.set_ylabel("Sharpe ratio (rf=0)")
    ax.set_title("Sharpe ratio by fund")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "sharpe_barplot.png", dpi=150)
    plt.close(fig)


def plot_sentiment_index(sector_index):
    fig, ax = plt.subplots(figsize=(9, 5))
    sectors = sorted(sector_index["sector"].unique())
    colors = (CAT * 2)[:len(sectors)]
    for sec, color in zip(sectors, colors):
        s = sector_index[sector_index["sector"] == sec].set_index("trading_date")["sentiment"]
        ax.plot(s.index, s.rolling(20).mean().values, color=color, linewidth=1.3, label=sec)
    _style(ax)
    ax.axhline(0, color="#9a9a95", linewidth=1)
    ax.set_title("Sector sentiment index (20-day rolling mean, extended lexicon)")
    ax.set_ylabel("Sentiment (compound)")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=7)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "sector_sentiment_index.png", dpi=150)
    plt.close(fig)


def plot_fusion_before_after(fusion_df):
    equity_funds = ["equity_min_variance", "equity_max_sharpe", "equity_equal_weight"]
    variants = ["base", "vanilla_tilt", "extended_tilt"]
    fig, ax = plt.subplots(figsize=(9, 5))
    x = range(len(equity_funds))
    width = 0.25
    for i, variant in enumerate(variants):
        vals = [fusion_df.loc[(fusion_df["fund"] == f) & (fusion_df["variant"] == variant), "sharpe"].iloc[0]
                for f in equity_funds]
        ax.bar([xi + (i - 1) * width for xi in x], vals, width=width, color=CAT[i],
               label=variant.replace("_", " "))
    _style(ax)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f.replace("equity_", "") for f in equity_funds])
    ax.set_ylabel("Sharpe ratio (rf=0)")
    ax.set_title("Fusion before vs after - equity funds")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fusion_before_after.png", dpi=150)
    plt.close(fig)


def plot_sharpe_sensitivity(fusion_df):
    """Sharpe ratio vs tilt strength k in {0, 0.25, 0.5, 1.0} per equity fund
    (extended lexicon) - what "Figure 7" in the report actually names, as
    opposed to the base/vanilla/extended-at-fixed-k comparison in
    plot_fusion_before_after."""
    equity_funds = ["equity_min_variance", "equity_max_sharpe", "equity_equal_weight"]
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, f in enumerate(equity_funds):
        base = fusion_df.loc[(fusion_df["fund"] == f) & (fusion_df["variant"] == "base"), "sharpe"].iloc[0]
        ks = (fusion_df.loc[(fusion_df["fund"] == f) & (fusion_df["variant"] == "extended_tilt_ksens")]
              .sort_values("k"))
        xs = [0.0] + ks["k"].tolist()
        ys = [base] + ks["sharpe"].tolist()
        ax.plot(xs, ys, color=CAT[i], linewidth=2, marker="o",
                label=f.replace("equity_", "").replace("_", " "))
    _style(ax)
    ax.set_xlabel("Sentiment tilt strength (k)")
    ax.set_ylabel("Sharpe ratio (rf=0)")
    ax.set_title("Sharpe ratio sensitivity to sentiment-tilt strength - equity funds (extended lexicon)")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "sharpe_sensitivity.png", dpi=150)
    plt.close(fig)


def plot_neutral_rate(neutral_rates):
    fig, ax = plt.subplots(figsize=(6.5, 4))
    labels = ["Vanilla VADER", "Extended lexicon"]
    vals = [neutral_rates["vanilla_neutral_rate"], neutral_rates["extended_neutral_rate"]]
    ax.bar(labels, vals, color=[CAT[0], CAT[2]])
    _style(ax)
    ax.set_ylabel("Share of headlines scoring exactly neutral")
    ax.set_title("Neutral-headline rate: before vs after lexicon extension")
    for i, v in enumerate(vals):
        ax.text(i, v + 0.005, f"{v:.1%}", ha="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "lexicon_neutral_rate.png", dpi=150)
    plt.close(fig)


def save_outputs(fund_results, sent, fusion_df):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    TAB_DIR.mkdir(parents=True, exist_ok=True)

    fund_returns = pd.concat(
        [pd.DataFrame({"fund": name, "date": r["daily_returns"].index, "daily_return": r["daily_returns"].values})
         for name, r in fund_results.items()], ignore_index=True)
    fund_returns.to_csv(DATA_DIR / "fund_returns.csv", index=False)

    fund_weights = pd.concat(
        [r["weights"].reset_index().melt(id_vars="date", var_name="ticker", value_name="weight").assign(fund=name)
         for name, r in fund_results.items()], ignore_index=True)[["fund", "date", "ticker", "weight"]]
    fund_weights.to_csv(DATA_DIR / "fund_weights.csv", index=False)

    sent["sector_ext"].to_csv(DATA_DIR / "sector_sentiment_index.csv", index=False)
    sent["sector_vanilla"].to_csv(DATA_DIR / "sector_sentiment_index_vanilla.csv", index=False)

    performance_metrics = pd.DataFrame([
        {"fund": name, "asset_family": r["family"], "method": r["method"],
         "first_live_date": r["first_live_date"], "window": r["window"],
         "periods_per_year": r["ppy"], **r["metrics"]}
        for name, r in fund_results.items()
    ])
    performance_metrics.to_csv(TAB_DIR / "performance_metrics.csv", index=False)

    fusion_df.to_csv(TAB_DIR / "fusion_comparison.csv", index=False)
    pd.DataFrame([sent["neutral_rates"]]).to_csv(TAB_DIR / "lexicon_neutral_rate.csv", index=False)

    return fund_returns, fund_weights, performance_metrics


def save_robustness_outputs(pred_power, placebo_df, tilt_corr_df):
    TAB_DIR.mkdir(parents=True, exist_ok=True)
    pred_power.to_csv(TAB_DIR / "predictive_power.csv", index=False)
    placebo_df.to_csv(TAB_DIR / "placebo_test.csv", index=False)
    tilt_corr_df.to_csv(TAB_DIR / "weight_tilt_correlation.csv", index=False)


def main():
    print("[run_part_b] loading + cleaning data...")
    wide_eq, wide_cr, combined = build_return_matrices()

    print("[run_part_b] running the 9-fund walk-forward backtests...")
    fund_results = run_funds(wide_eq, wide_cr, combined)

    print("[run_part_b] scoring sentiment (vanilla + extended lexicon)...")
    sent = run_sentiment()

    print("[run_part_b] applying the sentiment fusion...")
    fusion_df, fusion_outputs = run_fusion(fund_results, wide_eq, sent)

    print("[run_part_b] running sentiment robustness checks (predictive power, placebo test)...")
    pred_power, placebo_df, tilt_corr_df = run_robustness(fund_results, wide_eq, sent)

    print("[run_part_b] saving results/ data, tables, and figures...")
    fund_returns, fund_weights, performance_metrics = save_outputs(fund_results, sent, fusion_df)
    save_robustness_outputs(pred_power, placebo_df, tilt_corr_df)

    plot_growth_of_1(fund_results)
    plot_drawdown(fund_results)
    plot_weights_over_time(fund_results)
    plot_sharpe_barplot(performance_metrics)
    plot_sentiment_index(sent["sector_ext"])
    plot_fusion_before_after(fusion_df)
    plot_sharpe_sensitivity(fusion_df)
    plot_neutral_rate(sent["neutral_rates"])

    print("[run_part_b] done.")
    print(performance_metrics[["fund", "annualised_return", "annualised_vol", "sharpe", "max_drawdown"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
