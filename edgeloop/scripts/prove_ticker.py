"""Phase 1 proof: one ticker, end to end, with a printed provenance record.

    python -m edgeloop.scripts.prove_ticker NVDA            # recorded bodies
    python -m edgeloop.scripts.prove_ticker NVDA --live     # real HTTP, needs FMP_API_KEY

What this demonstrates, and nothing more:

* the client fetches the seven endpoints a single-ticker analysis needs,
* under the 8-uncached-call budget,
* through the cache and the rate governor,
* parsing into typed models,
* producing a provenance record per fetch with data_asof separated from
  fetched_at and a missing[] register,
* and persisting those records to the database.

What it does NOT demonstrate: any forecast. There is no quant core yet -- that
is phase 2. This script deliberately prints no mu, no sigma, and no quantiles,
because printing a number the system cannot yet stand behind is the exact
failure mode the ledger exists to prevent.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from ..config import REPO_ROOT, load_settings
from ..data import endpoints as ep
from ..data.db import create_all, create_db_engine, session_factory
from ..data.fmp import FmpClient, FmpError, RateLimited
from ..data.models import ProvenanceRecord
from ..data.provenance import Provenance, input_hash

RULE = "=" * 78


def banner(text: str) -> None:
    print(f"\n{RULE}\n{text}\n{RULE}")


async def run(symbol: str, live: bool) -> int:
    settings = load_settings()

    banner(f"edgeloop II -- phase 1 proof -- {symbol}")
    print(f"model_version : {settings.model_version}")
    print(f"transport     : {'live HTTP' if live else 'recorded fixtures'}")
    print(f"database      : {settings.redacted()['database_url']}")
    print(f"FMP_API_KEY   : {settings.redacted()['fmp']['api_key']}")

    if live and not settings.fmp.configured:
        print(
            "\nFATAL: --live requires FMP_API_KEY in the environment.\n"
            "       It must never be written into the repo."
        )
        return 2

    client = (
        FmpClient(settings=settings)
        if live
        else FmpClient.from_fixtures(REPO_ROOT / "fixtures", settings=settings)
    )

    # ---------------------------------------------------------------- fetch
    banner("FETCH -- the seven calls a single-ticker analysis costs")
    results: dict[str, object] = {}
    try:
        async with client:
            results["quote"] = await client.quote(symbol)
            results["price_history"] = await client.price_history(symbol)
            results["profile"] = await client.profile(symbol)
            results["key_metrics_ttm"] = await client.key_metrics_ttm(symbol)
            results["income_statement"] = await client.income_statement(symbol)
            results["treasury_rates"] = await client.treasury_rates()
            results["market_risk_premium"] = await client.market_risk_premium()
    except RateLimited as exc:
        print(f"\nSTOPPED by the rate governor: {exc}")
        return 3
    except FmpError as exc:
        print(f"\nFMP error: {exc}")
        return 4

    for name, fetched in results.items():
        print(f"  {name:<22} {len(fetched.rows):>4} row(s)  quality={fetched.provenance.quality.value}")

    # ------------------------------------------------------------- budget
    banner("CALL BUDGET -- spec says a single ticker analysis costs under 8 uncached calls")
    print(f"  {client.budget.render()}")
    within = client.budget.uncached < 8
    print(f"  uncached={client.budget.uncached}  budget=8  -> {'WITHIN' if within else 'OVER'} BUDGET")

    governor_budget = client.governor.budget(
        results["quote"].provenance.fetched_at
    )
    print(f"  governor: {governor_budget}")

    # --------------------------------------------------------- provenance
    banner("PROVENANCE RECORDS")
    for name, fetched in results.items():
        print(f"\n[{name}]")
        print(fetched.provenance.render())

    # ------------------------------------------- the point-in-time example
    banner("POINT-IN-TIME -- why data_asof is not fetched_at")
    statement = results["income_statement"].first
    if statement is not None:
        print(f"  fiscal period end (date)      : {statement.date}")
        print(f"  filing date                   : {statement.filingDate}")
        print(f"  SEC acceptance (acceptedDate) : {statement.acceptedDate}")
        print(f"  -> data_asof used             : {statement.as_of()}")
        if statement.filingDate and statement.date:
            gap = (statement.filingDate - statement.date).days
            print(
                f"\n  The fiscal period ended {gap} days before the world could know.\n"
                f"  A backtest keyed on 'date' would trade on this filing {gap} days early.\n"
                "  That is the leak point-in-time discipline exists to close."
            )

    # ------------------------------------------------------ missing fields
    banner("MISSING FIELD REGISTER -- constraint 5")
    total_missing = sum(len(f.provenance.missing) for f in results.values())
    if total_missing == 0:
        print("  No expected field was absent in this run.")
        print("  (An empty register is a result, not an absence of checking --")
        print("   every fetch declared the fields it depends on via expect_fields.)")
    else:
        for name, fetched in results.items():
            for miss in fetched.provenance.missing:
                print(f"  {name}: {miss}")
    print("\n  Nothing above was interpolated, estimated, or carried forward.")

    # -------------------------------------------------------- reproducibility
    banner("REPRODUCIBILITY -- input_hash over the price series and parameters")
    bars = results["price_history"].rows
    series = [(str(b.date), b.price) for b in bars]
    digest = input_hash(
        {
            "symbol": symbol,
            "series": series,
            "model_version": settings.model_version,
            "shrink_1y": settings.drift.shrink_1y,
            "shrink_3y": settings.drift.shrink_3y,
        }
    )
    print(f"  bars           : {len(series)}")
    if series:
        print(f"  range          : {series[-1][0]} .. {series[0][0]}")
    print(f"  input_hash     : {digest}")
    print("  Re-running against the same bodies reproduces this hash exactly.")

    # ------------------------------------------------------------- persist
    banner("PERSIST -- provenance records to the database")
    engine = create_db_engine(settings)
    create_all(engine)
    Session = session_factory(engine)
    with Session() as session:
        for fetched in results.values():
            prov: Provenance = fetched.provenance
            session.add(
                ProvenanceRecord(
                    source=prov.source,
                    endpoint=prov.endpoint,
                    params_json=json.dumps(prov.params, sort_keys=True),
                    fetched_at=prov.fetched_at,
                    data_asof=prov.data_asof,
                    quality=prov.quality.value,
                    cache_hit=prov.cache_hit,
                    missing_json=json.dumps([str(m) for m in prov.missing]) or None,
                    note=prov.note or None,
                )
            )
        session.commit()
        count = session.query(ProvenanceRecord).count()
    print(f"  provenance_records rows now in database: {count}")

    # ------------------------------------------------- what is not verified
    banner("WHAT IS NOT VERIFIED")
    unverified = ep.unverified_paths()
    print(f"  {len(unverified)} endpoint path(s) have never been confirmed by docs or a live 200:")
    for endpoint in unverified:
        print(f"    - {endpoint.key:<24} {endpoint.url}")
    shapes = ep.unverified_shapes()
    print(f"\n  {len(shapes)} response shape(s) never observed; their models are provisional:")
    for endpoint in shapes:
        print(f"    - {endpoint.key}")
    print(f"\n  Plan-blocked endpoints (kept visible on purpose): "
          f"{', '.join(e.key for e in ep.blocked())}")
    print(f"\n  {ep.OPTIONS_AVAILABILITY}")

    banner("PHASE 1 PROOF COMPLETE")
    return 0 if within else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", nargs="?", default="NVDA")
    parser.add_argument(
        "--live",
        action="store_true",
        help="use real HTTP instead of recorded bodies; requires FMP_API_KEY",
    )
    args = parser.parse_args()
    return asyncio.run(run(args.symbol.upper(), args.live))


if __name__ == "__main__":
    sys.exit(main())
