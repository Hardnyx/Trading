"""Run experimental portfolio comparisons; never change live market inputs."""
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys

if __package__:
    from .refresh_data import download, ROOT
    from .bond_profiles import parse_profile
    from .distributions import DISTRIBUTION_URLS, parse_issuer_history
else:
    from refresh_data import download, ROOT
    from bond_profiles import parse_profile
    from distributions import DISTRIBUTION_URLS, parse_issuer_history


def main():
    if len(sys.argv) < 2:
        raise SystemExit('Usage: python scripts/run_portfolio_robustness.py ACCOUNT_JSON [CONFIG_JSON]')
    market = json.loads((ROOT/'dist/data/market.json').read_text())
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    # The actual account contains IEF. A bond source must be explicit rather
    # than treating this position as a generic 6% expected-return ETF.
    raw = download(DISTRIBUTION_URLS['IEF'], 'issuer-IEF.html', max_age=3600).decode()
    parse_issuer_history(raw, 'IEF', now)  # Validate ticker/product/currency.
    profile = parse_profile(raw, 'IEF', now[:10], now, source_url=DISTRIBUTION_URLS['IEF'])
    if profile['date'] > market['generated_at'][:10]:
        raise ValueError('Current issuer profile is after the market information date; refresh market first')
    out = ROOT/'out'
    out.mkdir(exist_ok=True)
    path = out/'robustness-bond-inputs.json'
    path.write_text(json.dumps({'IEF':profile},indent=2)+'\n')
    subprocess.run(['node',str(ROOT/'scripts/portfolio_robustness.mjs'),str(path),
                    *[str(Path(arg).resolve()) for arg in sys.argv[1:]]],
                   cwd=ROOT,check=True)


if __name__ == '__main__':
    main()
