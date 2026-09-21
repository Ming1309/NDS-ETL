import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
from etl.adapters.base import SourceBundle

class Reconciler:
    def __init__(self, reports_dir: str = "reports"):
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def reconcile_run(
        self,
        bundles: List[SourceBundle],
        load_counts: Dict[str, Dict[str, int]],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Generate comprehensive reconciliation report."""
        report = {
            "generated_at": datetime.now().isoformat(),
            "dry_run": dry_run,
            "sources": {},
            "totals": {
                "tours": 0,
                "departures": 0,
                "prices": 0,
                "itineraries": 0,
                "reviews": 0,
                "unmapped_items": 0,
                "issues": 0,
            },
            "acceptance_check": {
                "target_tours": 1523,
                "actual_tours": 0,
                "passed": False,
                "source_targets": {
                    "BestPrice": 509,
                    "Vietravel": 240,
                    "Pystravel": 774
                }
            }
        }

        for b in bundles:
            sname = b.source_name
            counts = load_counts.get(sname, {})
            # Production acceptance is based on the transaction that committed,
            # never merely on records produced by a transformer.
            committed = bool(counts.get("committed")) or dry_run
            tour_count = (counts.get("tours", 0) if committed and not dry_run else len(b.tours))
            dep_count = len(b.departures)
            price_count = len(b.prices)
            itin_count = len(b.itineraries)
            rev_count = len(b.reviews)
            unmapped_count = len(b.unmapped_items)
            issue_count = len(b.issues)

            report["sources"][sname] = {
                "tours": tour_count,
                "departures": dep_count,
                "prices": price_count,
                "itineraries": itin_count,
                "reviews": rev_count,
                "unmapped_items": unmapped_count,
                "issues": issue_count,
                "metrics": b.metrics,
                "load_counts": counts,
                "status": counts.get("status", "DRY_RUN" if dry_run else "FAILED"),
                "raw_records": len(b.raw_records),
                "file_hashes": b.file_hashes,
                "issues_summary": [
                    {
                        "error_code": iss.error_code,
                        "severity": iss.severity,
                        "record_key": iss.record_key,
                        "message": iss.message
                    } for iss in b.issues[:10]  # sample first 10
                ]
            }

            report["totals"]["tours"] += tour_count
            report["totals"]["departures"] += dep_count
            report["totals"]["prices"] += price_count
            report["totals"]["itineraries"] += itin_count
            report["totals"]["reviews"] += rev_count
            report["totals"]["unmapped_items"] += unmapped_count
            report["totals"]["issues"] += issue_count

        # Calculate target based on sources in this run
        target_tours = sum(
            report["acceptance_check"]["source_targets"].get(sname, 0)
            for sname in report["sources"].keys()
        )
        total_tours = report["totals"]["tours"]
        report["acceptance_check"]["target_tours"] = target_tours
        report["acceptance_check"]["actual_tours"] = total_tours
        all_committed = dry_run or all(
            data["status"] == "COMPLETED" for data in report["sources"].values()
        )
        report["acceptance_check"]["passed"] = (all_committed and total_tours == target_tours and target_tours > 0)

        # Save to reports dir
        report_file = self.reports_dir / f"reconciliation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        report["report_path"] = str(report_file)
        return report

    def print_terminal_summary(self, report: Dict[str, Any]) -> None:
        """Print clean, professional ASCII summary table on terminal."""
        print("\n" + "=" * 78)
        print("                      NDS-ETL RECONCILIATION REPORT")
        print("=" * 78)
        print(f" Mode: {'DRY-RUN (Simulated)' if report['dry_run'] else 'PRODUCTION (Committed)'}")
        print(f" Generated At: {report['generated_at']}")
        print("-" * 78)
        print(f" {'Source':<12} | {'Tours':<7} | {'Deps':<7} | {'Prices':<7} | {'Revs':<7} | {'Unmapped':<8} | {'Issues':<6}")
        print("-" * 78)

        for sname, sdata in report["sources"].items():
            print(f" {sname:<12} | {sdata['tours']:<7} | {sdata['departures']:<7} | {sdata['prices']:<7} | "
                  f"{sdata['reviews']:<7} | {sdata['unmapped_items']:<8} | {sdata['issues']:<6}")

        print("-" * 78)
        tot = report["totals"]
        print(f" {'TOTAL':<12} | {tot['tours']:<7} | {tot['departures']:<7} | {tot['prices']:<7} | "
              f"{tot['reviews']:<7} | {tot['unmapped_items']:<8} | {tot['issues']:<6}")
        print("=" * 78)

        acc = report["acceptance_check"]
        status_sym = "PASSED (OK)" if acc["passed"] else "FAILED (DISCREPANCY)"
        print(f" Acceptance Target: {acc['target_tours']} tours (509 BestPrice + 240 Vietravel + 774 Pystravel)")
        print(f" Actual Ingested:   {acc['actual_tours']} tours -> Status: {status_sym}")
        print(f" Full JSON Report:  {report.get('report_path')}")
        print("=" * 78 + "\n")
