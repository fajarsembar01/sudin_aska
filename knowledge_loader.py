from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
KECERDASAN_DIR = BASE_DIR / "kecerdasan"
GENERAL_FILE = KECERDASAN_DIR / "umum.md"
SPECIFIC_FILE = KECERDASAN_DIR / "profil_sudindikju2.md"
PLACEHOLDER = "<!-- {{ASKA_PROFIL_DAN_JADWAL}} -->"



DATA_SEKOLAH_FILE = KECERDASAN_DIR / "Data_Sekolah_Sudin_JU2.md"
DETAIL_SEKOLAH_FILE = KECERDASAN_DIR / "Detail_Sekolah.md"
STRUKTUR_ORG_FILE = KECERDASAN_DIR / "struktur_organisasi_sudindikju2.md"

def _read(path: Path) -> str:
    if not path.exists():
        # Optional: warn log? For now, just return empty if missing to avoid breaking if file moved
        return "" 
    return path.read_text(encoding="utf-8")


def load_kecerdasan(*, ensure_output_file: bool = False) -> str:
    """
    Gabungkan potongan pengetahuan menjadi satu string markdown.

    Saat ensure_output_file=True, hasil gabungan juga dapat ditulis ke berkas
    gabungan (misalnya untuk keperluan debug/manual).
    """

    general_text = _read(GENERAL_FILE)
    specific_text = _read(SPECIFIC_FILE).strip()
    # Prioritaskan file Detail_Sekolah.md (hasil rekap terbaru) bila tersedia.
    schools_text = _read(DETAIL_SEKOLAH_FILE).strip() or _read(DATA_SEKOLAH_FILE).strip()
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

    combined = combined.strip() + "\n"
    return combined


def build_kecerdasan_file() -> Path:
    """
    Utility opsional bila ingin menyimpan hasil gabungan ke berkas markdown.
    Secara default runtime bot TIDAK membutuhkan berkas ini.
    """
    output_file = BASE_DIR / "kecerdasan.build.md"
    content = load_kecerdasan(ensure_output_file=False)
    output_file.write_text(content, encoding="utf-8")
    return output_file


if __name__ == "__main__":
    path = build_kecerdasan_file()
    rel = path.relative_to(BASE_DIR)
    print(f"Sukses menyusun {rel}")
