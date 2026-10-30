"""Optional reproducible figure for the frozen account diagnostic (Matplotlib)."""
import argparse
import json
from pathlib import Path
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def plot_accounts(source, output, preview=None):
    report = json.loads(Path(source).read_text())
    accounts = {a["id"]: a for a in report["runs"][0]["accounts"]}
    names = [("ttm_monthly", "TTM mensual", "#62b0ff"),
             ("yield_monthly", "BPA/precio mensual", "#f5ad42"),
             ("index_monthly", "SPY mensual", "#5dcf9c"),
             ("ttm_initial_hold", "Cesta TTM inicial mantenida", "#ce8bee")]
    with plt.style.context("dark_background"):
        plt.rcParams["svg.hashsalt"] = report["protocol"]["id"]
        fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
        fig.patch.set_facecolor("#14181f")
        for axis in axes:
            axis.set_facecolor("#14181f")
            axis.grid(alpha=.15)
            axis.spines[["top", "right"]].set_visible(False)
        for key, label, color in names:
            rows = accounts[key]["nav"]
            days = [date.fromisoformat(r["date"]) for r in rows]
            axes[0].plot(days, [r["nav"] / 1000 for r in rows], label=label, color=color, lw=1.6)
            axes[1].plot(days, [100 * (1 - r["cash"] / r["nav"]) for r in rows], color=color, lw=1.5)
        axes[0].set_ylabel("Patrimonio neto · miles de USD")
        axes[0].set_title("Cuenta reconstruida: rendimiento y exposición efectiva", loc="left", pad=14)
        axes[0].legend(loc="upper left", frameon=False, fontsize=8)
        axes[1].set_ylabel("Exposición a renta variable · %")
        axes[1].set_ylim(0, 80)
        axes[1].xaxis.set_major_locator(mdates.YearLocator())
        axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        axes[1].axhline(35, color="white", alpha=.4, lw=.8, ls="--")
        fig.text(.085, .035, "31-oct-2022 a 28-oct-2026 · Costes base · Dividendos reinvertidos brutos\n"
                 "Diagnóstico de señal con catálogo y universo actuales. No valida la cartera de producción.",
                 fontsize=8, color="#c5c8ce")
        fig.subplots_adjust(left=.085, right=.97, top=.92, bottom=.15, hspace=.16)
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, metadata={"Date": None})
        if Path(output).suffix.lower() == ".svg":
            svg = Path(output)
            svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
        if preview:
            fig.savefig(preview, dpi=140)
        plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="out/ttm-account-backtest-v2.json")
    parser.add_argument("--output", default="out/ttm-account-backtest-v2.svg")
    parser.add_argument("--preview")
    args = parser.parse_args()
    plot_accounts(args.input, args.output, args.preview)
