import json
from contextlib import contextmanager

from dashboard.monev_bos import bop_claims
from dashboard.monev_bos import queries


def teardown_function():
    bop_claims.load_bop_claim_dataset.cache_clear()


def test_get_school_bop_claim_matches_npsn_and_builds_stable_codes(tmp_path, monkeypatch):
    dataset_path = tmp_path / "claims.json"
    dataset_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset_id": "bop-2026-tw02-jakut-wilayah-2",
                "fund_source": "BOP",
                "year": 2026,
                "tw": 2,
                "schools": [
                    {
                        "npsn": "20100565",
                        "name": "SDN CONTOH",
                        "transactions": [
                            {
                                "account_code": "5.1.02.01.001.00012",
                                "description": "Belanja Bahan",
                                "amount": 125000,
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bop_claims, "DATASET_PATH", dataset_path)
    bop_claims.load_bop_claim_dataset.cache_clear()

    claim = bop_claims.get_school_bop_claim("20100565", 2026, 2)

    assert claim["school_name"] == "SDN CONTOH"
    assert claim["total_amount"] == 125000
    assert claim["transactions"][0]["activity_code"] == "BOP26T2-20100565-51020100100012"


def test_get_school_bop_claim_is_limited_to_pilot_period():
    assert bop_claims.get_school_bop_claim("20100565", 2025, 2) is None
    assert bop_claims.get_school_bop_claim("20100565", 2026, 3) is None


def test_additional_claim_periods_are_available_and_use_unique_period_codes():
    claim_2025_tw4 = bop_claims.get_school_bop_claim("20100565", 2025, 4)
    claim_2026_tw1 = bop_claims.get_school_bop_claim("20100565", 2026, 1)

    assert claim_2025_tw4["transactions"]
    assert claim_2026_tw1["transactions"]
    assert all(item["activity_code"].startswith("BOP25T4-") for item in claim_2025_tw4["transactions"])
    assert all(item["activity_code"].startswith("BOP26T1-") for item in claim_2026_tw1["transactions"])
    assert claim_2025_tw4["transactions"][0]["account_code"].count(".") == 5


def test_all_repository_claim_datasets_have_consistent_totals():
    expected = {
        (2025, 4): (133, 1275, 21_158_453_544),
        (2026, 1): (132, 571, 7_453_637_773),
        (2026, 2): (133, 1020, 19_804_690_147),
    }
    all_codes = []
    for period, totals in expected.items():
        dataset = bop_claims.load_bop_claim_dataset(*period)
        assert (dataset["school_count"], dataset["transaction_count"], dataset["total_amount"]) == totals
        for school in dataset["schools"]:
            claim = bop_claims.get_school_bop_claim(school["npsn"], *period)
            all_codes.extend(item["activity_code"] for item in claim["transactions"])
    assert len(all_codes) == len(set(all_codes))


def test_repository_dataset_totals_and_claim_codes_are_consistent():
    dataset = bop_claims.load_bop_claim_dataset()
    all_codes = []
    calculated_total = 0

    for school in dataset["schools"]:
        claim = bop_claims.get_school_bop_claim(school["npsn"], 2026, 2)
        all_codes.extend(item["activity_code"] for item in claim["transactions"])
        calculated_total += claim["total_amount"]

    assert dataset["school_count"] == 133
    assert dataset["transaction_count"] == len(all_codes) == 1020
    assert len(all_codes) == len(set(all_codes))
    assert dataset["total_amount"] == calculated_total == 19_804_690_147


def test_adjusted_claim_transaction_is_inserted_with_step_details(monkeypatch):
    class FakeCursor:
        last_query = ""

        def execute(self, query, params):
            self.last_query = query
            assert query.count("%s") == len(params)

        def fetchone(self):
            if "SELECT r.id" in self.last_query:
                return {"id": 10, "school_id": 20, "status": "draft", "year": 2026, "tw": 2}
            if "FROM monev_bos_activities" in self.last_query and "FOR UPDATE" in self.last_query:
                return None
            return {"id": 99}

    @contextmanager
    def fake_get_cursor(commit=False):
        yield FakeCursor()

    monkeypatch.setattr(queries, "get_cursor", fake_get_cursor)
    result = queries.claim_bop_transactions(
        10,
        20,
        [
            {
                "activity_code": "BOP26T2-20100565-51020100100012",
                "activity_name": "Kegiatan yang disesuaikan",
                "account_code": "5.1.02.01.001.00012",
                "realized_amount": 125000,
                "vendor_name": "Toko Contoh",
                "vendor_id": 7,
                "bku_number": "BKU/01",
                "item_name": "Tinta",
                "item_specs": "Sumber JSON",
                "item_quantity": 1,
                "expense_type_id": 3,
            }
        ],
    )
    assert result == {"inserted": 1, "updated": 0, "skipped": 0}


def test_reclaim_updates_the_existing_transaction_without_duplication(monkeypatch):
    executed_queries = []

    class FakeCursor:
        last_query = ""

        def execute(self, query, params):
            self.last_query = query
            executed_queries.append(query)
            assert query.count("%s") == len(params)

        def fetchone(self):
            if "SELECT r.id" in self.last_query:
                return {"id": 10, "school_id": 20, "status": "draft", "year": 2026, "tw": 2}
            if "FROM monev_bos_activities" in self.last_query and "FOR UPDATE" in self.last_query:
                return {"id": 99, "status": "pending"}
            return None

    @contextmanager
    def fake_get_cursor(commit=False):
        yield FakeCursor()

    monkeypatch.setattr(queries, "get_cursor", fake_get_cursor)
    transaction = bop_claims.get_school_bop_claim("20100565", 2026, 2)["transactions"][0]
    transaction.update(
        {
            "activity_name": "Kegiatan hasil klaim ulang",
            "vendor_name": None,
            "vendor_id": None,
            "expense_type_id": 3,
        }
    )

    result = queries.claim_bop_transactions(10, 20, [transaction])

    assert result == {"inserted": 0, "updated": 1, "skipped": 0}
    assert any("UPDATE monev_bos_activities" in query for query in executed_queries)
    assert not any("INSERT INTO monev_bos_activities" in query for query in executed_queries)


def test_expense_type_recommendation_uses_account_context_and_amount():
    expense_types = [
        {"id": 1, "name": "Belanja barang  Rp 50Jt- 200 Jt kecuali makan & minum"},
        {"id": 3, "name": "Belanja barang dibawah Rp 50 Jt kecuali makan & minum"},
        {"id": 7, "name": "Belanja makan minum rapat"},
        {"id": 10, "name": "TALI"},
    ]

    assert bop_claims.recommend_expense_type(
        "Belanja Makanan dan Minuman Rapat", 2_000_000, expense_types
    )["id"] == 7
    assert bop_claims.recommend_expense_type(
        "Belanja Tagihan Listrik", 2_000_000, expense_types
    )["id"] == 10
    assert bop_claims.recommend_expense_type(
        "Belanja Bahan-Bahan Lainnya", 2_000_000, expense_types
    )["id"] == 3
    assert bop_claims.recommend_expense_type(
        "Belanja Modal Mebel", 75_000_000, expense_types
    )["id"] == 1
