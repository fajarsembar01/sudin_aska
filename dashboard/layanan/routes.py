import csv
import io
from urllib.parse import quote
from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, url_for
from dashboard.auth import current_user
from . import queries
from .access import layanan_access_required

layanan_bp = Blueprint('layanan', __name__, url_prefix='/layanan', template_folder='templates')
layanan_legacy_bp = Blueprint('layanan_legacy', __name__, url_prefix='/portal/layanan')
TYPES = {
    'ijazah': 'Ijazah',
    'skpi': 'SKPI',
    'legalisasi': 'Legalisasi',
    'mutasi': 'Mutasi siswa',
    'kjp': 'KJP',
    'pip': 'PIP',
    'kjmu': 'KJMU',
}
STATUSES = {'dicatat': 'Baru dicatat', 'diproses': 'Sedang diproses', 'selesai': 'Selesai diproses', 'diserahkan': 'Sudah diserahkan'}
access = layanan_access_required


@layanan_legacy_bp.route('', defaults={'path': ''}, methods=['GET', 'POST'])
@layanan_legacy_bp.route('/', defaults={'path': ''}, methods=['GET', 'POST'])
@layanan_legacy_bp.route('/<path:path>', methods=['GET', 'POST'])
@access
def legacy_redirect(path):
    target = url_for('layanan.index') + quote(path, safe='/')
    if request.query_string:
        target += '?' + request.query_string.decode('utf-8', errors='replace')
    return redirect(target, code=308)


LABELS = {'service_date': 'Tanggal', 'student_name': 'Nama siswa / pemohon', 'school_origin': 'Sekolah asal',
          'diploma_number': 'Nomor ijazah', 'nisn': 'NISN', 'letter_code': 'Kode surat',
          'letter_number': 'Nomor surat', 'school_destination': 'Sekolah tujuan', 'grade': 'Kelas',
          'notes': 'Keterangan', 'recipient_name': 'Nama penerima', 'received_date': 'Tanggal penyerahan'}
LIMITS = {'student_name': 200, 'school_origin': 250, 'diploma_number': 150, 'nisn': 10,
          'letter_code': 100, 'letter_number': 150, 'school_destination': 250, 'grade': 30,
          'notes': 5000, 'recipient_name': 200}


def today():
    return datetime.now(ZoneInfo('Asia/Jakarta')).date()


def validate_record(form):
    data = {key: (form.get(key) or '').strip() for key in queries.FIELDS}
    errors = []
    school_choice = data['school_origin_id']
    school = None
    if school_choice.isascii() and school_choice.isdigit() and len(school_choice) <= 10 and 0 < int(school_choice) <= 2147483647:
        school = queries.get_origin_school(int(school_choice))
    if school:
        data['school_origin_id'] = school['id']
        data['school_origin'] = school['name']
    else:
        errors.append('Pilih sekolah asal yang terdaftar di database.')
        data['school_origin_id'] = None
        data['school_origin'] = ''
    if data['service_type'] not in TYPES:
        errors.append('Pilih jenis layanan yang valid.')
    if data['status'] not in STATUSES:
        errors.append('Pilih status yang valid.')
    if data['service_type'] == 'mutasi':
        destination_mode = (form.get('school_destination_mode') or '').strip()
        if not destination_mode:
            destination_mode = 'database' if data['school_destination_id'] else 'manual'
        data['_school_destination_mode'] = destination_mode
        if destination_mode == 'database':
            destination_choice = data['school_destination_id']
            destination = None
            if (destination_choice.isascii() and destination_choice.isdigit()
                    and len(destination_choice) <= 10
                    and 0 < int(destination_choice) <= 2147483647):
                destination = queries.get_origin_school(int(destination_choice))
            if destination:
                data['school_destination_id'] = destination['id']
                data['school_destination'] = destination['name']
            else:
                data['school_destination_id'] = None
                data['school_destination'] = ''
                errors.append('Pilih sekolah tujuan dari database.')
        elif destination_mode == 'manual':
            data['school_destination_id'] = None
            data['school_destination'] = (
                form.get('school_destination_manual')
                or form.get('school_destination')
                or ''
            ).strip()
        else:
            data['school_destination_id'] = None
            data['school_destination'] = ''
            errors.append('Pilih sumber sekolah tujuan yang valid.')
    else:
        data['school_destination_id'] = None
        data['school_destination'] = ''
        data['grade'] = ''
        data['transfer_direction'] = ''
    for key in ('service_date', 'student_name', 'school_origin'):
        if not data[key]:
            errors.append(f'{LABELS[key]} wajib diisi.')
    for key, limit in LIMITS.items():
        if len(data[key]) > limit:
            errors.append(f'{LABELS[key]} maksimal {limit} karakter.')
    if data['nisn'] and (not data['nisn'].isascii() or not data['nisn'].isdigit()):
        errors.append('NISN hanya boleh berisi angka.')
    parsed = {}
    for key in ('service_date', 'received_date'):
        if data[key]:
            try:
                parsed[key] = date.fromisoformat(data[key])
                if parsed[key] > today():
                    errors.append(f'{LABELS[key]} tidak boleh melewati hari ini.')
            except ValueError:
                errors.append(f'{LABELS[key]} tidak valid.')
    if len(parsed) == 2 and parsed['received_date'] < parsed['service_date']:
        errors.append('Tanggal penyerahan tidak boleh sebelum tanggal layanan.')
    if data['service_type'] == 'mutasi':
        for key in ('school_destination', 'grade'):
            if not data[key]:
                message = f'{LABELS[key]} wajib diisi untuk mutasi.'
                if message not in errors and not (
                    key == 'school_destination'
                    and any('sekolah tujuan' in error.lower() for error in errors)
                ):
                    errors.append(message)
        if data['transfer_direction'] not in ('masuk', 'keluar'):
            errors.append('Pilih mutasi masuk atau keluar.')
    if data['status'] == 'diserahkan' and not (data['recipient_name'] and data['received_date']):
        errors.append('Nama penerima dan tanggal penyerahan wajib diisi untuk status Diserahkan.')
    if data['status'] != 'diserahkan' and (data['recipient_name'] or data['received_date']):
        errors.append('Gunakan status Diserahkan jika mengisi bukti penyerahan.')
    return data, errors


def filters_from_request():
    filters = {key: request.args.get(key, '').strip() for key in ('q', 'service_type', 'status', 'start', 'end')}
    if filters['service_type'] and filters['service_type'] not in TYPES:
        abort(400)
    if filters['status'] and filters['status'] not in STATUSES:
        abort(400)
    for key in ('start', 'end'):
        if filters[key]:
            try:
                date.fromisoformat(filters[key])
            except ValueError:
                abort(400)
    if filters['start'] and filters['end'] and filters['start'] > filters['end']:
        abort(400, 'Tanggal awal harus sebelum tanggal akhir.')
    return filters


@layanan_bp.route('/')
@access
def index():
    # Keep old bookmarked search URLs useful after introducing the overview.
    if request.args:
        return redirect(url_for('layanan.register', **filters_from_request()))
    counts, totals = summary_counts({})
    rows, total = queries.list_records({})
    return render_template('layanan/overview.html', counts=counts, totals=totals,
                           total=total, rows=rows[:5], types=TYPES, statuses=STATUSES)


def summary_counts(filters):
    counts = {kind: {status: 0 for status in STATUSES} for kind in TYPES}
    totals = {status: 0 for status in STATUSES}
    for row in queries.summarize_records(filters):
        counts[row['service_type']][row['status']] = row['total']
        totals[row['status']] += row['total']
    return counts, totals


@layanan_bp.route('/register', defaults={'category': None})
@layanan_bp.route('/register/<category>')
@access
def register(category):
    if category and category not in TYPES:
        abort(404)
    filters = filters_from_request()
    if category:
        filters['service_type'] = category
    page = max(1, request.args.get('page', 1, type=int))
    rows, total = queries.list_records(filters, page)
    return render_template('layanan/index.html', rows=rows, total=total, page=page,
                           filters=filters, types=TYPES, statuses=STATUSES, user=current_user(),
                           category=category, page_title='Daftar layanan ' + TYPES[category] if category else 'Daftar layanan')


@layanan_bp.route('/laporan')
@access
def report():
    filters = filters_from_request()
    filters['q'] = ''
    filters['status'] = ''
    counts, totals = summary_counts(filters)
    return render_template('layanan/report.html', filters=filters, counts=counts,
                           totals=totals, total=sum(totals.values()), types=TYPES, statuses=STATUSES)


@layanan_bp.route('/baru', methods=['GET', 'POST'])
@layanan_bp.route('/<int:record_id>/edit', methods=['GET', 'POST'])
@access
def edit(record_id=None):
    record = queries.get_record(record_id) if record_id else None
    if record_id and not record:
        abort(404)
    user = current_user()
    if record and record['created_by'] != user['id'] and user['role'] != 'admin':
        abort(403)
    initial_type = request.args.get('service_type', 'ijazah')
    if initial_type not in TYPES:
        initial_type = 'ijazah'
    data = record or {'service_date': today().isoformat(), 'service_type': initial_type, 'status': 'dicatat'}
    version = record['version'] if record else None
    errors = []
    status_code = 200
    if request.method == 'POST':
        data, errors = validate_record(request.form)
        version = request.form.get('version', type=int)
        if not errors:
            saved = queries.save_record(data, user, record_id, version)
            if saved:
                flash('Catatan layanan berhasil disimpan.', 'success')
                return redirect(url_for('layanan.detail', record_id=saved))
            errors.append('Catatan telah diubah oleh petugas lain. Buka ulang halaman untuk melihat data terbaru sebelum menyimpan.')
            status_code = 409
        else:
            status_code = 400
    return render_template('layanan/form.html', data=data, record_id=record_id, version=version,
                           errors=errors, types=TYPES, statuses=STATUSES, labels=LABELS,
                           limits=LIMITS, today=today().isoformat(),
                           schools=queries.list_origin_schools()), status_code


@layanan_bp.route('/siswa/cari')
@access
def student_search():
    term = request.args.get('q', '').strip()
    if not (3 <= len(term) <= 10 and term.isascii() and term.isdigit()):
        response = jsonify(students=[])
    else:
        response = jsonify(students=queries.search_students_by_nisn(term))
    response.headers['Cache-Control'] = 'no-store'
    return response


@layanan_bp.route('/<int:record_id>', methods=['GET', 'POST'])
@access
def detail(record_id):
    record = queries.get_record(record_id)
    if not record:
        abort(404)
    user = current_user()
    status_data = {key: record.get(key) or '' for key in ('status', 'recipient_name', 'received_date')}
    errors = []
    version = record['version']
    response_status = 200
    if request.method == 'POST':
        if record['created_by'] != user['id'] and user['role'] != 'admin':
            abort(403)
        version = request.form.get('version', type=int)
        status_data = {key: request.form.get(key, '').strip() for key in status_data}
        if status_data['status'] not in STATUSES:
            errors.append('Pilih status layanan yang valid.')
        if status_data['status'] == 'diserahkan':
            if not status_data['recipient_name']:
                errors.append('Isi nama penerima dokumen.')
            elif len(status_data['recipient_name']) > LIMITS['recipient_name']:
                errors.append('Nama penerima maksimal 200 karakter.')
            try:
                received = date.fromisoformat(status_data['received_date'])
                if received < record['service_date'] or received > today():
                    errors.append('Tanggal penyerahan harus antara tanggal layanan dan hari ini.')
            except ValueError:
                errors.append('Isi tanggal penyerahan yang valid.')
        else:
            status_data['recipient_name'] = ''
            status_data['received_date'] = ''
        if errors:
            response_status = 400
        elif not queries.update_record_status(record_id, status_data, user, version):
            errors.append('Catatan sudah diubah oleh petugas lain. Muat ulang halaman sebelum menyimpan kembali.')
            response_status = 409
        else:
            flash('Status layanan berhasil diperbarui.', 'success')
            return redirect(url_for('layanan.detail', record_id=record_id))
    return render_template('layanan/detail.html', record=record, labels=LABELS,
                           types=TYPES, statuses=STATUSES, user=user, status_data=status_data,
                           status_errors=errors, status_version=version, today=today().isoformat()), response_status


def csv_safe(value):
    text = str(value) if value is not None else ''
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) or text.startswith(('\t', '\r', '\n')) else text


@layanan_bp.route('/ekspor.csv')
@access
def export():
    rows, _ = queries.list_records(filters_from_request(), export=True)
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    columns = ['id', 'service_type', *LABELS, 'transfer_direction', 'status', 'officer_name']
    writer.writerow(['Nomor register', 'Jenis layanan', *LABELS.values(), 'Arah mutasi', 'Status', 'Petugas pencatat'])
    for row in rows:
        row['service_type'] = TYPES[row['service_type']]
        row['status'] = STATUSES[row['status']]
        writer.writerow([csv_safe(row.get(key)) for key in columns])
    return Response('\ufeff' + output.getvalue(), mimetype='text/csv', headers={
        'Content-Disposition': f'attachment; filename="register-layanan-{today()}.csv"'})
