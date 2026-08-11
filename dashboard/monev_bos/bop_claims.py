"""Repository-backed BOP transaction claim dataset helpers."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional


DATASET_PATH = Path(__file__).with_name("data") / "bop_transactions_2026_tw02.json"
DATASET_PATHS = {
    (2025, 4): Path(__file__).with_name("data") / "bop_transactions_2025_tw04.json",
    (2026, 1): Path(__file__).with_name("data") / "bop_transactions_2026_tw01.json",
    (2026, 2): DATASET_PATH,
}
SUPPORTED_BOP_CLAIM_PERIODS = frozenset(DATASET_PATHS)


def is_bop_claim_period(year: int, tw: int) -> bool:
    return (int(year), int(tw)) in SUPPORTED_BOP_CLAIM_PERIODS


@lru_cache(maxsize=3)
def load_bop_claim_dataset(year: int = 2026, tw: int = 2) -> Dict[str, Any]:
    period = (int(year), int(tw))
    dataset_path = DATASET_PATH if period == (2026, 2) else DATASET_PATHS.get(period)
    if not dataset_path:
        raise ValueError("Periode dataset klaim BOP tidak didukung.")
    with dataset_path.open(encoding="utf-8") as source:
        dataset = json.load(source)

    if dataset.get("schema_version") != 1:
        raise ValueError("Versi dataset klaim BOP tidak didukung.")
    if dataset.get("fund_source") != "BOP":
        raise ValueError("Dataset klaim harus menggunakan sumber dana BOP.")
    if dataset.get("year") != period[0] or dataset.get("tw") != period[1]:
        raise ValueError("Periode di dalam dataset klaim BOP tidak sesuai.")

    return dataset


def get_school_bop_claim(npsn: Optional[str], year: int, tw: int) -> Optional[Dict[str, Any]]:
    """Return claim data belonging to one NPSN for the requested pilot period."""
    clean_npsn = str(npsn or "").strip()
    if not clean_npsn or not is_bop_claim_period(year, tw):
        return None

    dataset = load_bop_claim_dataset(year, tw)
    school = next(
        (item for item in dataset.get("schools", []) if str(item.get("npsn", "")).strip() == clean_npsn),
        None,
    )
    if not school:
        return None

    transactions: List[Dict[str, Any]] = []
    for sequence, item in enumerate(school.get("transactions", []), start=1):
        account_code = str(item.get("account_code") or "").strip()
        amount = int(item.get("amount") or 0)
        if not account_code or amount <= 0:
            continue
        transactions.append(
            {
                "activity_code": f"BOP{str(int(year))[-2:]}T{int(tw)}-{clean_npsn}-{account_code.replace('.', '')}",
                "activity_name": str(item.get("description") or account_code).strip(),
                "account_code": account_code,
                "realized_amount": amount,
                "bku_number": f"KLAIM/TW{int(tw):02d}/{sequence:02d}",
                "item_name": f"Klaim data realisasi BOP {int(year)} TW {int(tw):02d}",
                "item_specs": f"Sumber: {dataset.get('dataset_id')}",
                "item_quantity": 1,
            }
        )

    return {
        "dataset_id": dataset.get("dataset_id"),
        "year": int(year),
        "tw": int(tw),
        "school_name": school.get("name"),
        "npsn": clean_npsn,
        "transactions": transactions,
        "total_amount": sum(item["realized_amount"] for item in transactions),
    }


def recommend_expense_type(
    description: str,
    amount: float,
    expense_types: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Choose the closest active expense type for a source account description."""
    source = str(description or "").casefold()
    normalized_types = [
        (item, str(item.get("name") or "").casefold()) for item in expense_types
    ]

    def find(*keywords: str) -> Optional[Dict[str, Any]]:
        for item, name in normalized_types:
            if all(keyword.casefold() in name for keyword in keywords):
                return item
        return None

    if "makanan dan minuman rapat" in source:
        return find("makan minum rapat")
    if "makanan dan minuman aktivitas lapangan" in source:
        return find("makan minum harian")
    if "narasumber" in source:
        return find("narsumber") or find("narasumber")
    if "sewa kendaraan" in source:
        return find("sewa kendaraan")
    if "sewa alat reproduksi" in source or "penggandaan" in source:
        return find("sewa foto copy")
    if any(keyword in source for keyword in ("tagihan telepon", "tagihan air", "tagihan listrik", "internet")):
        return find("tali")
    if "kursus" in source or "pelatihan" in source:
        return find("biaya kepesertaan") or find("instruktur")
    if "pemeliharaan" in source:
        if "bangunan gedung" in source:
            return find("pemeliharaan", "kib-c")
        threshold = "50jt - 200jt" if float(amount or 0) >= 50_000_000 else "dibawah rp 50jt"
        return find("pemeliharaan", threshold, "kib-b")

    threshold = "50jt- 200 jt" if float(amount or 0) >= 50_000_000 else "dibawah rp 50 jt"
    return find("belanja barang", threshold)
