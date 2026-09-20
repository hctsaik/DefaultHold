from __future__ import annotations

import argparse
import json
import sys

from vai_hold.composition.bootstrap import build_app
from vai_hold.domain.errors import ConfigError, OracleNotImplemented, UnknownFunctionCode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vai_hold")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="run a function-code pipeline")
    run_p.add_argument("--function-code", required=True)
    run_p.add_argument("--config", default=None)
    run_p.add_argument("--order-id", default=None)
    run_p.add_argument("--limit", type=int, default=500)
    run_p.add_argument("--sponsor", default=None)
    run_p.add_argument("--evidence", default=None)
    run_p.add_argument("--actor", default=None)
    run_p.add_argument("--approver", default=None)
    tree_p = sub.add_parser("gen-tree", help="regenerate living decision mermaid + locator")
    sub.add_parser("gen-evidence", help="run mock E2E scenarios and write Facts/Action evidence")
    scen_p = sub.add_parser("run-scenarios", help="DAO 撈題庫 → 判斷/Action → 比對 Facts（Order DB 預設 SQLite＝Oracle 彩排）")
    scen_p.add_argument(
        "--backend",
        choices=("sqlite", "memory"),
        default="sqlite",
        help="Order DB：sqlite 當 Oracle 彩排（預設）；memory 只圖快",
    )
    sub.add_parser("gen-scenario-html", help="用已存的 scenario_run 產出情境總覽 HTML（不重跑）")
    sub.add_parser("gen-order-db", help="產出可檢查的 Order DB SQLite（C09 data_error、A123456.01 片號）")
    inv = sub.add_parser("investigate", help="從 log 產查案筆記（最後一輪 EVAL，不是第一筆 A2-01）")
    inv.add_argument("--lot", required=True)
    inv.add_argument("--order-id", default=None)
    inv.add_argument("--log", required=True, help="log 檔路徑")
    args = parser.parse_args(argv)

    if args.cmd == "gen-tree":
        from vai_hold.tools.gen_decision_tree import write_artifacts

        write_artifacts()
        print("Design/generated/ updated")
        return 0
    if args.cmd == "gen-evidence":
        from vai_hold.tools.scenario_evidence import write_all

        print(write_all())
        return 0
    if args.cmd == "run-scenarios":
        from pathlib import Path

        from vai_hold.adapters.persistence.sqlite.scenario_catalog import SqliteScenarioCatalog
        from vai_hold.application.scenario_runner import run_catalog
        from vai_hold.tools.seed_scenario_catalog import seed_catalog

        if args.backend == "sqlite":
            from vai_hold.tools.persist_scenario_orders import persist_catalog_sqlite, verify_persisted

            results, catalog_db, orders_root = persist_catalog_sqlite()
            cat = SqliteScenarioCatalog(catalog_db)
            problems = verify_persisted(results, orders_root, cat)
            failed = [r for r in results if not r.passed]
            print(
                f"scenarios={len(results)} passed={len(results) - len(failed)} failed={len(failed)} "
                f"catalog={catalog_db} orders={orders_root}"
            )
            for r in failed:
                print(f"FAIL {r.scenario_id} {r.title}")
                for d in r.diffs:
                    print(f"  {d}")
            for p in problems:
                print(f"VERIFY {p}")
            return 1 if failed or problems else 0

        db = Path("Design/generated/scenario_catalog.sqlite")
        cat = SqliteScenarioCatalog(db)
        seed_catalog(cat)
        results = run_catalog(cat, backend="memory")
        failed = [r for r in results if not r.passed]
        print(
            f"scenarios={len(results)} passed={len(results) - len(failed)} failed={len(failed)} "
            f"catalog={db} order_db=memory"
        )
        for r in failed:
            print(f"FAIL {r.scenario_id} {r.title}")
            for d in r.diffs:
                print(f"  {d}")
        return 1 if failed else 0
    if args.cmd == "gen-scenario-html":
        from vai_hold.tools.write_scenario_html import write_all_scenario_html

        print(write_all_scenario_html())
        return 0
    if args.cmd == "gen-order-db":
        from vai_hold.tools.export_order_sqlite import export_order_db

        print(export_order_db())
        return 0
    if args.cmd == "investigate":
        from pathlib import Path

        from vai_hold.investigate import render_case

        text = Path(args.log).read_text(encoding="utf-8")
        sys.stdout.write(render_case(text, args.lot, order_id=args.order_id))
        return 0
    if args.cmd != "run":
        parser.print_help()
        return 2
    try:
        app = build_app(config_path=args.config)
        result = app.run(
            args.function_code,
            {
                "order_id": args.order_id,
                "limit": args.limit,
                "sponsor": args.sponsor,
                "evidence": args.evidence,
                "actor": args.actor,
                "approver": args.approver,
            },
        )
    except UnknownFunctionCode as exc:
        print(f"unknown function code: {exc}", file=sys.stderr)
        return 2
    except (ConfigError, OracleNotImplemented) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result.__dict__, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
