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


# ---- Layanan Publik CRUD ----

UPLOAD_LAYANAN = CMS_UPLOAD_ROOT / "layanan_publik"
UPLOAD_LAYANAN.mkdir(parents=True, exist_ok=True)
ALLOWED_DOC_EXTENSIONS = {'pdf', 'doc', 'docx'}


def _allowed_doc(filename):
    """Check if file extension is allowed for documents."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_DOC_EXTENSIONS


def _list_layanan_publik(limit=None, offset=None):
    """Ambil data layanan publik dengan pagination."""
    with get_cursor() as cur:
        sql = "SELECT * FROM cms_layanan_publik ORDER BY id ASC"
        params = []
        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)
        if offset is not None:
            sql += " OFFSET %s"
            params.append(offset)
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def _count_layanan_publik():
    """Hitung total data layanan publik."""
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cms_layanan_publik")
        res = cur.fetchone()
    return res[0] if res else 0


def _get_layanan_by_id(layanan_id):
    """Ambil satu layanan publik by ID."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM cms_layanan_publik WHERE id = %s", (layanan_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def _save_uploaded_files(files):
    """Save uploaded files and return metadata list."""
    import uuid
    file_entries = []
    for f in files:
        if f and f.filename and _allowed_doc(f.filename):
            file_id = uuid.uuid4().hex[:12]
            safe_name = secure_filename(f.filename)
            stored_name = f"{file_id}_{safe_name}"
            filepath = UPLOAD_LAYANAN / stored_name
            f.save(filepath)
            file_entries.append({
                'id': file_id,
                'name': safe_name,
                'path': f"uploads/portal/cms/layanan_publik/{stored_name}",
                'size': os.path.getsize(filepath),
            })
    return file_entries


@cms_bp.route("/layanan-publik")
@role_required("admin")
def layanan_publik():
    """Halaman untuk mengelola layanan publik."""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    
    total_items = _count_layanan_publik()
    data = _list_layanan_publik(limit=per_page, offset=offset)
    
    total_pages = (total_items + per_page - 1) // per_page
    
    # Parse cms_files JSON if it's a string
    for item in data:
        if isinstance(item.get('cms_files'), str):
            item['cms_files'] = json.loads(item['cms_files'])
            
    pagination = {
        'current_page': page,
        'total_pages': total_pages,
        'total_items': total_items,
        'per_page': per_page,
        'start_index': offset + 1 if total_items > 0 else 0,
        'end_index': min(offset + per_page, total_items)
    }
    
    return render_template("cms/layanan_publik.html", layanan=data, pagination=pagination)


@cms_bp.route("/layanan-publik/tambah", methods=['POST'])
@role_required("admin")
def layanan_publik_tambah():
    """Tambah layanan publik baru."""
    try:
        nama = request.form.get('cms_nama_layanan', '').strip()
        deskripsi = request.form.get('cms_deskripsi', '').strip()
        icon = request.form.get('cms_icon', 'bi-star').strip()
        status = request.form.get('cms_status', 'Aktif').strip()
        if not nama:
            return jsonify({'success': False, 'error': 'Nama layanan wajib diisi'}), 400

        # Handle file uploads
        uploaded = request.files.getlist('cms_files')
        file_entries = _save_uploaded_files(uploaded)

        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO cms_layanan_publik
                (cms_nama_layanan, cms_deskripsi, cms_icon, cms_status, cms_files, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, NOW(), NOW())
                """,
                (nama, deskripsi, icon, status, json.dumps(file_entries))
            )
        return jsonify({'success': True, 'message': 'Layanan publik berhasil ditambahkan'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@cms_bp.route("/layanan-publik/<int:layanan_id>/edit", methods=['POST'])
@role_required("admin")
def layanan_publik_edit(layanan_id):
    """Update layanan publik."""
    try:
        existing = _get_layanan_by_id(layanan_id)
        if not existing:
            return jsonify({'success': False, 'error': 'Layanan tidak ditemukan'}), 404

        nama = request.form.get('cms_nama_layanan', '').strip()
        deskripsi = request.form.get('cms_deskripsi', '').strip()
        icon = request.form.get('cms_icon', 'bi-star').strip()
        status = request.form.get('cms_status', 'Aktif').strip()
        if not nama:
            return jsonify({'success': False, 'error': 'Nama layanan wajib diisi'}), 400

        # Existing files — remove deleted ones
        existing_files = existing.get('cms_files', [])
        if isinstance(existing_files, str):
            existing_files = json.loads(existing_files)

        deleted_ids = request.form.getlist('deleted_file_ids')
        kept_files = []
        for f in existing_files:
            if f.get('id') in deleted_ids:
                # Delete physical file
                try:
                    phys = Path(__file__).parent.parent.parent / f.get('path', '')
                    if phys.exists():
                        phys.unlink()
                except Exception:
                    pass
            else:
                kept_files.append(f)

        # Handle new file uploads
        uploaded = request.files.getlist('cms_files')
        new_entries = _save_uploaded_files(uploaded)
        all_files = kept_files + new_entries

        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                UPDATE cms_layanan_publik
                SET cms_nama_layanan = %s, cms_deskripsi = %s, cms_icon = %s,
                    cms_status = %s, cms_files = %s::jsonb, updated_at = NOW()
                WHERE id = %s
                """,
                (nama, deskripsi, icon, status, json.dumps(all_files), layanan_id)
            )
        return jsonify({'success': True, 'message': 'Layanan publik berhasil diperbarui'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@cms_bp.route("/layanan-publik/<int:layanan_id>/hapus", methods=['POST'])
@role_required("admin")
def layanan_publik_hapus(layanan_id):
    """Hapus layanan publik."""
    try:
        existing = _get_layanan_by_id(layanan_id)
        if not existing:
            return jsonify({'success': False, 'error': 'Layanan tidak ditemukan'}), 404

        # Delete physical files
        files = existing.get('cms_files', [])
        if isinstance(files, str):
            files = json.loads(files)
        for f in files:
            try:
                phys = Path(__file__).parent.parent.parent / f.get('path', '')
                if phys.exists():
                    phys.unlink()
            except Exception:
                pass

        with get_cursor(commit=True) as cur:
            cur.execute("DELETE FROM cms_layanan_publik WHERE id = %s", (layanan_id,))
        return jsonify({'success': True, 'message': 'Layanan publik berhasil dihapus'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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
