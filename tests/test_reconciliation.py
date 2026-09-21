from etl.adapters import BestPriceAdapter, VietravelAdapter, PystravelAdapter
from etl.config import DEFAULT_DATA_DIR
from etl.loader.reconciler import Reconciler

def test_full_reconciliation_target_1523():
    bp_bundle = BestPriceAdapter().extract_and_transform(DEFAULT_DATA_DIR)
    vt_bundle = VietravelAdapter().extract_and_transform(DEFAULT_DATA_DIR)
    pys_bundle = PystravelAdapter().extract_and_transform(DEFAULT_DATA_DIR)

    bundles = [bp_bundle, vt_bundle, pys_bundle]
    reconciler = Reconciler(reports_dir="reports")
    report = reconciler.reconcile_run(bundles, {}, dry_run=True)

    assert report["sources"]["BestPrice"]["tours"] == 509
    assert report["sources"]["Vietravel"]["tours"] == 240
    assert report["sources"]["Pystravel"]["tours"] == 774

    assert report["totals"]["tours"] == 1523
    assert report["acceptance_check"]["actual_tours"] == 1523
    assert report["acceptance_check"]["passed"] is True
