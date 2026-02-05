from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.portal.school_directory_export import export_detail_sekolah_markdown


def main() -> int:
    output_path = PROJECT_ROOT / "kecerdasan" / "Detail_Sekolah.md"
    total = export_detail_sekolah_markdown(output_path)
    print(f"Berhasil memperbarui {output_path} dengan {total} sekolah.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
