from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

BASE_DIR = Path(__file__).resolve().parent
KECERDASAN_DIR = BASE_DIR / "kecerdasan"
GENERAL_FILE = KECERDASAN_DIR / "umum.md"
SPECIFIC_FILE = KECERDASAN_DIR / "profil_sudindikju2.md"
PLACEHOLDER = "<!-- {{ASKA_PROFIL_DAN_JADWAL}} -->"

DATA_SEKOLAH_FILE = KECERDASAN_DIR / "Data_Sekolah_Sudin_JU2.md"
DETAIL_SEKOLAH_FILE = KECERDASAN_DIR / "Detail_Sekolah.md"
STRUKTUR_ORG_FILE = KECERDASAN_DIR / "struktur_organisasi_sudindikju2.md"

GENERATED_DIR = KECERDASAN_DIR / ".generated"

FOLDER_ORDER_FILE = KECERDASAN_DIR / ".folder_order.json"
FILE_ORDER_FILE = KECERDASAN_DIR / ".file_order.json"

_PAGE_MARKER_RE = re.compile(r"^<!-- halaman:\d+(?:-\d+)? -->\n?", re.MULTILINE)

# Daftar berkas dasar yang sudah terstruktur. Berkas Markdown lain yang
# ditempatkan di folder `kecerdasan/` akan otomatis ikut dimuat sebagai lampiran
# tambahan di akhir konten utama.
_BUILT_IN_PATHS = {
    GENERAL_FILE.resolve(),
    SPECIFIC_FILE.resolve(),
    DATA_SEKOLAH_FILE.resolve(),
    DETAIL_SEKOLAH_FILE.resolve(),
    STRUKTUR_ORG_FILE.resolve(),
}

def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _read_clean(path: Path) -> str:
    """Read a file, preferring the .generated/ clean copy when available."""
    clean_path = GENERATED_DIR / path.relative_to(KECERDASAN_DIR)
    if clean_path.exists():
        return clean_path.read_text(encoding="utf-8")
    return _read(path)


def generate_clean_file(source_path: Path) -> Path:
    """Strip page markers from *source_path* and write a clean copy to .generated/."""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    raw = _read(source_path)
    clean = _PAGE_MARKER_RE.sub("", raw)
    rel = source_path.relative_to(KECERDASAN_DIR)
    dest = GENERATED_DIR / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(clean, encoding="utf-8")
    return dest


def generate_all_clean_files() -> None:
    """Generate clean copies for every .md file in KECERDASAN_DIR."""
    if not KECERDASAN_DIR.exists():
        return
    for md_path in KECERDASAN_DIR.rglob("*.md"):
        # Skip files already inside .generated/
        try:
            md_path.relative_to(GENERATED_DIR)
            continue
        except ValueError:
            pass
        generate_clean_file(md_path)


def _relative_path_str(path: Path) -> str:
    """
    Representasikan path relatif terhadap KECERDASAN_DIR sebagai string POSIX.
    Digunakan baik untuk folder_order lama maupun file_order baru.
    """
    try:
        rel = path.relative_to(KECERDASAN_DIR)
    except ValueError:
        return ""
    rel_text = rel.as_posix()
    return "" if rel_text in (".", "") else rel_text


def normalize_folder_order(raw: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for item in raw:
        if not item:
            continue
        segment = item.replace("\\", "/").strip().strip("/ ")
        if segment and segment not in seen:
            seen.append(segment)
    return seen


def load_folder_order() -> list[str]:
    if not FOLDER_ORDER_FILE.exists():
        return []
    try:
        payload = json.loads(FOLDER_ORDER_FILE.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return []
    except Exception:
        return []
    return normalize_folder_order(payload)


def save_folder_order(order: Iterable[str]) -> None:
    normalized = normalize_folder_order(order)
    KECERDASAN_DIR.mkdir(parents=True, exist_ok=True)
    FOLDER_ORDER_FILE.write_text(json.dumps(normalized, indent=2), encoding="utf-8")


def normalize_file_order(raw: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for item in raw:
        if not item:
            continue
        segment = (item or "").replace("\\", "/").strip().strip("/ ")
        if segment and segment not in seen:
            seen.append(segment)
    return seen


def load_file_order() -> list[str]:
    if not FILE_ORDER_FILE.exists():
        return []
    try:
        payload = json.loads(FILE_ORDER_FILE.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return []
    except Exception:
        return []
    return normalize_file_order(payload)


def save_file_order(order: Iterable[str]) -> None:
    normalized = normalize_file_order(order)
    KECERDASAN_DIR.mkdir(parents=True, exist_ok=True)
    FILE_ORDER_FILE.write_text(json.dumps(normalized, indent=2), encoding="utf-8")


def load_kecerdasan(*, ensure_output_file: bool = False) -> str:
    """
    Gabungkan potongan pengetahuan menjadi satu string markdown.

    Saat ensure_output_file=True, hasil gabungan juga dapat ditulis ke berkas
    gabungan (misalnya untuk keperluan debug/manual).
    """

    general_text = _read(GENERAL_FILE)
    specific_text = _read(SPECIFIC_FILE).strip()
    schools_text = _read(DATA_SEKOLAH_FILE).strip()
    detail_schools_text = _read(DETAIL_SEKOLAH_FILE).strip()
    struktur_org_text = _read(STRUKTUR_ORG_FILE).strip()

    # Gabungkan profil ke dalam umum
    insertion = f"{specific_text}\n\n" if specific_text else ""
    if PLACEHOLDER in general_text:
        combined = general_text.replace(PLACEHOLDER, insertion)
    else:
        combined = f"{general_text.rstrip()}\n\n{specific_text}\n"

    # Tambahkan struktur organisasi
    if struktur_org_text:
        combined = f"{combined.rstrip()}\n\n# Struktur Organisasi\n{struktur_org_text}\n"

    # Tambahkan data sekolah di akhir
    if schools_text:
        combined = f"{combined.rstrip()}\n\n# Data Sekolah\n{schools_text}\n"

    # Tambahkan detail sekolah (rekap lengkap)
    if detail_schools_text:
        combined = f"{combined.rstrip()}\n\n# Detail Sekolah\n{detail_schools_text}\n"

    # Sertakan berkas tambahan lain (mis. hasil unggahan admin)
    extra_files = []
    if KECERDASAN_DIR.exists():
        for path in KECERDASAN_DIR.rglob("*.md"):
            try:
                if path.resolve() in _BUILT_IN_PATHS:
                    continue
            except OSError:
                continue
            extra_files.append(path)
        file_order = load_file_order()
        order_index = {rel_path: idx for idx, rel_path in enumerate(file_order)}
        default_index = len(order_index)

        def _extra_sort_key(path: Path) -> tuple[int, str]:
            rel_path = _relative_path_str(path)
            rank = order_index.get(rel_path, default_index)
            # Berkas yang sudah diurutkan muncul lebih dulu (rank < default_index),
            # sisanya mengikuti urutan alfabetis berdasarkan path relatif.
            return rank, rel_path.lower()

        extra_files.sort(key=_extra_sort_key)

    for extra_path in extra_files:
        extra_text = _read_clean(extra_path).strip()
        if not extra_text:
            continue
        combined = f"{combined.rstrip()}\n\n{extra_text}\n"

    combined = combined.strip() + "\n"
    return combined


def build_kecerdasan_file() -> Path:
    """
    Utility opsional bila ingin menyimpan hasil gabungan ke berkas markdown.
    Secara default runtime bot TIDAK membutuhkan berkas ini.
    """
    generate_all_clean_files()
    output_file = BASE_DIR / "kecerdasan.build.md"
    content = load_kecerdasan(ensure_output_file=False)
    output_file.write_text(content, encoding="utf-8")
    return output_file


if __name__ == "__main__":
    path = build_kecerdasan_file()
    rel = path.relative_to(BASE_DIR)
    print(f"Sukses menyusun {rel}")
