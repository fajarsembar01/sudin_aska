"""Routes untuk Content Management System (CMS)."""

import json
import os
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, jsonify
from dashboard.auth import role_required
from dashboard.db_access import get_cursor

cms_bp = Blueprint("cms", __name__, url_prefix="/cms", template_folder="templates")

# Configuration
CMS_UPLOAD_ROOT = Path(__file__).parent.parent.parent / "uploads" / "portal" / "cms"
UPLOAD_PROFIL = CMS_UPLOAD_ROOT / "profil_instansi"
UPLOAD_PROFIL.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_profil_instansi():
    """Ambil profil instansi terbaru."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM cms_profil_instansi ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
    
    if not row:
        return None
    
    return dict(row)


def _save_profil_instansi(data):
    """Simpan atau update profil instansi."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO cms_profil_instansi 
            (cms_deskripsi_utama, cms_visi, cms_misi, cms_tugas_fungsi, cms_motto_pelayanan, cms_struktur_organisasi, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
            """,
            (
                data.get('cms_deskripsi_utama'),
                data.get('cms_visi'),
                data.get('cms_misi'),
                data.get('cms_tugas_fungsi'),
                data.get('cms_motto_pelayanan'),
                data.get('cms_struktur_organisasi'),
            )
        )


@cms_bp.route("/")
@role_required("admin")
def dashboard():
    """Halaman dashboard utama CMS."""
    
    # Dummy summary stats
    dummy_stats = {
        'total_layanan': 12,
        'layanan_aktif': 10,
        'total_artikel': 45,
        'pengumuman_aktif': 5,
        'total_galeri': 24,
        'visitor_today': 128,
        'visitor_month': 3450
    }
    
    # Dummy chart data (misal: statistik kunjungan bulanan)
    chart_kunjungan = {
        'labels': ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun'],
        'data': [2100, 2400, 2200, 2800, 3100, 3450]
    }
    
    # Dummy recent items
    recent_activities = [
        {'time': '10 menit yang lalu', 'user': 'Admin Server', 'action': 'Menambahkan artikel baru', 'item': 'Sosialisasi Program...'},
        {'time': '2 jam yang lalu', 'user': 'Humas Sudin RU2', 'action': 'Menyimpan draft pengumuman', 'item': 'Pendataan KJP Plus...'},
        {'time': 'Kemarin, 14:30', 'user': 'Admin Server', 'action': 'Mengupload galeri foto', 'item': 'Peringatan Hari Guru...'}
    ]
    
    # Dummy Draft Data
    drafts = {
        'artikel': [
            {'judul': 'Persiapan Ujian Nasional 2024', 'tanggal': 'Belum Dipublikasi'},
            {'judul': 'Kegiatan Pramuka Kwarcab', 'tanggal': 'Belum Dipublikasi'}
        ],
        'pengumuman': [
            {'judul': 'Revisi Jadwal Lomba OSN', 'tanggal': 'Belum Dipublikasi'}
        ],
        'galeri': [
            {'judul': 'Pelatihan Guru Penggerak', 'tanggal': 'Belum Dipublikasi'},
            {'judul': 'Rapat Kerja Tahunan 2024', 'tanggal': 'Belum Dipublikasi'}
        ]
    }
    
    return render_template("cms/index.html", 
                           stats=dummy_stats, 
                           chart_kunjungan=chart_kunjungan,
                           recent_activities=recent_activities,
                           drafts=drafts)


@cms_bp.route("/profil", methods=['GET', 'POST'])
@role_required("admin")
def profil():
    """Halaman untuk mengelola profil instansi."""
    
    if request.method == 'POST':
        try:
            # Get form data
            cms_deskripsi_utama = request.form.get('cms_deskripsi_utama', '')
            cms_visi = request.form.get('cms_visi', '')
            cms_misi = request.form.get('cms_misi', '')
            cms_motto_pelayanan = request.form.get('cms_motto_pelayanan', '')
            cms_tugas_fungsi = request.form.get('cms_tugas_fungsi', '')
            
            # Get existing profil for old file references
            existing_profil = _get_profil_instansi()
            
            # Handle gambar struktur organisasi
            cms_struktur_organisasi = None
            if 'cms_struktur_organisasi' in request.files:
                file = request.files['cms_struktur_organisasi']
                if file and file.filename and allowed_file(file.filename):
                    if file.content_length > MAX_FILE_SIZE:
                        return jsonify({'success': False, 'error': 'File struktur organisasi terlalu besar'}), 400
                    
                    filename = secure_filename(f"struktur_organisasi_{os.urandom(8).hex()}_{file.filename}")
                    filepath = UPLOAD_PROFIL / filename
                    file.save(filepath)
                    cms_struktur_organisasi = f"uploads/portal/cms/profil_instansi/{filename}"
                else:
                    cms_struktur_organisasi = existing_profil.get('cms_struktur_organisasi') if existing_profil else None
            else:
                cms_struktur_organisasi = existing_profil.get('cms_struktur_organisasi') if existing_profil else None
            
            # Save data
            data = {
                'cms_deskripsi_utama': cms_deskripsi_utama,
                'cms_visi': cms_visi,
                'cms_misi': cms_misi,
                'cms_motto_pelayanan': cms_motto_pelayanan,
                'cms_struktur_organisasi': cms_struktur_organisasi,
                'cms_tugas_fungsi': cms_tugas_fungsi,
            }
            
            _save_profil_instansi(data)
            
            return jsonify({
                'success': True,
                'message': 'Profil instansi berhasil disimpan'
            })
        
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    # GET request - load existing data
    profil_data = _get_profil_instansi()
    
    return render_template("cms/profil_instansi.html", profil=profil_data or {})


def _get_informasi_publik():
    """Ambil informasi publik terbaru."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM cms_informasi_publik ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
    
    if not row:
        return None
    
    return dict(row)


def _save_informasi_publik(data):
    """Simpan atau update informasi publik."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO cms_informasi_publik 
            (cms_jaminan_pelayanan, cms_keamanan_keselamatan, cms_kompensasi_pelayanan, created_at, updated_at)
            VALUES (%s, %s, %s, NOW(), NOW())
            """,
            (
                data.get('cms_jaminan_pelayanan'),
                data.get('cms_keamanan_keselamatan'),
                data.get('cms_kompensasi_pelayanan'),
            )
        )


@cms_bp.route("/informasi-publik", methods=['GET', 'POST'])
@role_required("admin")
def informasi_publik():
    """Halaman untuk mengelola informasi publik."""
    
    if request.method == 'POST':
        try:
            jaminan_pelayanan = request.form.get('cms_jaminan_pelayanan', '')
            keamanan_keselamatan = request.form.get('cms_keamanan_keselamatan', '')
            kompensasi_pelayanan = request.form.get('cms_kompensasi_pelayanan', '')
            
            data = {
                'cms_jaminan_pelayanan': jaminan_pelayanan,
                'cms_keamanan_keselamatan': keamanan_keselamatan,
                'cms_kompensasi_pelayanan': kompensasi_pelayanan,
            }
            
            _save_informasi_publik(data)
            
            return jsonify({
                'success': True,
                'message': 'Informasi publik berhasil disimpan'
            })
        
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    info_data = _get_informasi_publik()
    
    return render_template("cms/informasi_publik.html", info=info_data or {})


@cms_bp.route("/layanan-publik")
@role_required("admin")
def layanan_publik():
    """Halaman untuk mengelola layanan publik."""
    
    # Dummy data
    dummy_layanan = [
        {
            'id': 1,
            'nama': 'Pelayanan KJP Plus',
            'deskripsi': 'Informasi dan pendaftaran Kartu Jakarta Pintar (KJP) Plus untuk siswa.',
            'icon': 'bi-card-heading',
            'status': 'Aktif',
            'files': ['Syarat_KJP.pdf', 'Panduan_KJP.pdf']
        },
        {
            'id': 2,
            'nama': 'Mutasi Siswa',
            'deskripsi': 'Prosedur dan persyaratan untuk pindah sekolah/mutasi siswa antar wilayah.',
            'icon': 'bi-arrow-left-right',
            'status': 'Aktif',
            'files': ['Formulir_Mutasi.pdf']
        },
        {
            'id': 3,
            'nama': 'Legalisir Ijazah',
            'deskripsi': 'Pelayanan legalisir ijazah dan dokumen pendidikan lainnya.',
            'icon': 'bi-patch-check',
            'status': 'Tidak Aktif',
            'files': []
        }
    ]
    
    return render_template("cms/layanan_publik.html", layanan=dummy_layanan)


@cms_bp.route("/artikel")
@role_required("admin")
def artikel():
    """Halaman untuk mengelola artikel (media & publikasi)."""
    
    # Dummy data
    dummy_artikel = [
        {
            'id': 1,
            'judul': 'Sosialisasi Program Merdeka Belajar di Jakarta Utara',
            'kategori': 'Pendidikan',
            'tanggal': '2024-05-12',
            'deskripsi': '<p>Suku Dinas Pendidikan Jakarta Utara Wilayah II mengadakan sosialisasi terkait penerapan kurikulum Merdeka Belajar...</p>',
            'thumbnail': 'sosialisasi_merdeka.jpg',
            'penulis': 'Admin Sudin JU2',
            'status': 'Aktif',
            'status_publikasi': 'Published',
            'files': ['Materi_Sosialisasi.pdf']
        },
        {
            'id': 2,
            'judul': 'Prestasi Siswa SMAN 1 Jakarta di Kancah Internasional',
            'kategori': 'Berita Utama',
            'tanggal': '2024-05-10',
            'deskripsi': '<p>Siswa dari SMAN 1 Jakarta kembali mengharumkan nama bangsa dengan memenangkan medali emas...</p>',
            'thumbnail': 'prestasi_siswa.png',
            'penulis': 'Humas Sudin RU2',
            'status': 'Aktif',
            'status_publikasi': 'Published',
            'files': ['Daftar_Pemenang.pdf', 'Sertifikat_Juara.pdf']
        },
        {
            'id': 3,
            'judul': 'Panduan Penerimaan Peserta Didik Baru (PPDB) 2024',
            'kategori': 'Informasi',
            'tanggal': '2024-05-08',
            'deskripsi': '<p>Berikut ini adalah panduan lengkap mengenai tata cara pendaftaran PPDB tahun ajaran 2024/2025...</p>',
            'thumbnail': 'ppdb_2024.jpg',
            'penulis': 'Panitia PPDB',
            'status': 'Tidak Aktif',
            'status_publikasi': 'Draft',
            'files': []
        }
    ]
    
    return render_template("cms/artikel.html", artikel=dummy_artikel)


@cms_bp.route("/pengumuman")
@role_required("admin")
def pengumuman():
    """Halaman untuk mengelola pengumuman (media & publikasi)."""
    
    # Dummy data
    dummy_pengumuman = [
        {
            'id': 1,
            'judul': 'Pengumuman Libur Nasional Hari Raya 2024',
            'kategori': 'Pengumuman',
            'tanggal': '2024-03-20',
            'deskripsi': '<p>Diberitahukan kepada seluruh jajaran bahwa libur nasional akan dilaksanakan pada...</p>',
            'thumbnail': 'libur_nasional.jpg',
            'penulis': 'Admin Sudin JU2',
            'status': 'Aktif',
            'status_publikasi': 'Published',
            'files': ['Surat_Edaran_Libur.pdf']
        },
        {
            'id': 2,
            'judul': 'Hasil Seleksi OSN Tingkat Kota Jakarta Utara',
            'kategori': 'Kegiatan',
            'tanggal': '2024-02-15',
            'deskripsi': '<p>Selamat kepada para siswa yang telah lolos seleksi OSN. Berikut daftarnya:</p>',
            'thumbnail': 'hasil_osn.png',
            'penulis': 'Tim Kurikulum',
            'status': 'Aktif',
            'status_publikasi': 'Published',
            'files': ['Daftar_Lolos_OSN_2024.pdf']
        },
        {
            'id': 3,
            'judul': 'Pendaftaran Lomba Guru Berprestasi V',
            'kategori': 'Pendidikan',
            'tanggal': '2024-01-10',
            'deskripsi': '<p>Pendaftaran telah resmi dibatalkan untuk sementara waktu karena <em>force majeure</em>.</p>',
            'thumbnail': 'lomba_guru.jpg',
            'penulis': 'Humas Sudin JU2',
            'status': 'Tidak Aktif',
            'status_publikasi': 'Draft',
            'files': ['Revisi_Jadwal.pdf']
        }
    ]
    
    return render_template("cms/pengumuman.html", pengumuman=dummy_pengumuman)


@cms_bp.route("/galeri-kegiatan")
@role_required("admin")
def galeri_kegiatan():
    """Halaman untuk mengelola galeri kegiatan (media & publikasi)."""
    
    # Dummy data
    dummy_galeri = [
        {
            'id': 1,
            'nama_kegiatan': 'Peringatan Hari Guru Nasional 2023',
            'tanggal': '2023-11-25',
            'thumbnail': 'hari_guru.jpg',
            'gambar_kegiatan': ['kegiatan_1.jpg', 'kegiatan_2.jpg', 'kegiatan_3.jpg'],
            'penulis': 'Humas Sudin JU2',
            'status': 'Aktif',
            'status_publikasi': 'Published'
        },
        {
            'id': 2,
            'nama_kegiatan': 'Pusdiklat Kepemimpinan Kepala Sekolah',
            'tanggal': '2023-10-10',
            'thumbnail': 'pusdiklat_kepsek.png',
            'gambar_kegiatan': ['diklat_a.jpg', 'diklat_b.jpg'],
            'penulis': 'Admin Sudin JU2',
            'status': 'Aktif',
            'status_publikasi': 'Published'
        },
        {
            'id': 3,
            'nama_kegiatan': 'Lomba Paduan Suara Tingkat SD',
            'tanggal': '2023-08-17',
            'thumbnail': 'paduan_suara.jpg',
            'gambar_kegiatan': ['padus_1.jpg'],
            'penulis': 'Tim Kurikulum',
            'status': 'Tidak Aktif',
            'status_publikasi': 'Draft'
        }
    ]
    
    return render_template("cms/galeri_kegiatan.html", galeri=dummy_galeri)
