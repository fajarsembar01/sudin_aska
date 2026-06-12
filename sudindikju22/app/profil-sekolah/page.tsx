'use client'

import React, { useEffect, useState } from 'react'

const GRADE_MAP: Record<string, number[]> = {
  'PAUD': [-2, -1, 0],
  'SPS': [-1, 0],
  'TPA': [-1, 0],
  'KB': [-1, 0],
  'TK': [-1, 0],
  'SD': [1, 2, 3, 4, 5, 6],
  'SMP': [7, 8, 9],
  'SMA': [10, 11, 12],
  'SMK': [10, 11, 12],
}

function getGradeLabel(grade: number, jenjang: string) {
  if (grade > 0) return `Kelas ${grade}`
  if (grade === -2) return 'KB'
  if (grade === -1) return jenjang?.toUpperCase() === 'TK' ? 'TK A' : 'Kelompok A'
  if (grade === 0) return jenjang?.toUpperCase() === 'TK' ? 'TK B' : 'Kelompok B'
  return `Kelas ${grade}`
}

export default function ProfilSekolahPage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [school, setSchool] = useState<any>(null)
  const [kecamatanList, setKecamatanList] = useState<any[]>([])
  const [kelurahanList, setKelurahanList] = useState<any[]>([])
  const [filteredKelurahan, setFilteredKelurahan] = useState<any[]>([])
  const [formData, setFormData] = useState<any>({ empty_seats_by_grade: {} })
  const [missingFields, setMissingFields] = useState<string[]>([])
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      const res = await fetch('http://127.0.0.1:5002/api/sekolah/profile', {
        credentials: 'include',
      })
      const data = await res.json()
      if (data.success) {
        setSchool(data.school)
        setKecamatanList(data.kecamatan_list || [])
        setKelurahanList(data.kelurahan_list || [])
        setMissingFields(data.missing_fields || [])
        
        // Initialize form data
        let emptyByGrade = {}
        try {
          if (data.meta.empty_seats_by_grade) {
            emptyByGrade = typeof data.meta.empty_seats_by_grade === 'string' 
              ? JSON.parse(data.meta.empty_seats_by_grade) 
              : data.meta.empty_seats_by_grade
          }
        } catch(e) {}

        setFormData({
          alamat: data.school.alamat || data.meta.alamat || '',
          kecamatan_id: data.school.kecamatan_id || '',
          kelurahan_id: data.school.kelurahan_id || '',
          rt: data.meta.rt || '',
          rw: data.meta.rw || '',
          postal_code: data.meta.postal_code || '',
          gmaps_url: data.meta.gmaps_url || '',
          student_count: data.meta.student_count ?? '',
          inclusion_student_count: data.meta.inclusion_student_count ?? '',
          empty_seats: data.meta.empty_seats ?? '',
          empty_seats_by_grade: emptyByGrade,
          teacher_count: data.meta.teacher_count ?? '',
          staff_count: data.meta.staff_count ?? '',
          rombel_count: data.meta.rombel_count ?? '',
          school_phone: data.meta.school_phone || '',
          fax: data.meta.fax || '',
          coordinator_phone: data.meta.coordinator_phone || '',
          cs_email: data.meta.cs_email || '',
          website: data.meta.website || '',
          telegram: data.meta.telegram || '',
          instagram: data.meta.instagram || '',
          tiktok: data.meta.tiktok || '',
          youtube: data.meta.youtube || '',
          wa_channel: data.meta.wa_channel || '',
        })

        if (data.school.kecamatan_id) {
          setFilteredKelurahan(data.kelurahan_list.filter((k: any) => String(k.kecamatan_id) === String(data.school.kecamatan_id)))
        }
      } else {
        setErrorMsg(data.message || 'Gagal memuat profil sekolah.')
      }
    } catch (err) {
      setErrorMsg('Koneksi terputus. Pastikan backend Flask berjalan dan CORS diizinkan.')
    } finally {
      setLoading(false)
    }
  }

  const handleKecamatanChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value
    setFormData({ ...formData, kecamatan_id: val, kelurahan_id: '' })
    if (val) {
      setFilteredKelurahan(kelurahanList.filter(k => String(k.kecamatan_id) === String(val)))
    } else {
      setFilteredKelurahan([])
    }
  }

  const handleEmptySeatChange = (grade: number, val: string) => {
    setFormData({
      ...formData,
      empty_seats_by_grade: {
        ...formData.empty_seats_by_grade,
        [grade]: val === '' ? '' : parseInt(val, 10)
      }
    })
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setErrorMsg(null)
    setSuccessMsg(null)

    // Calculate total empty seats if grades are used
    let payload = { ...formData }
    const jenjangUpper = school?.jenjang?.toUpperCase() || ''
    const grades = GRADE_MAP[jenjangUpper]
    if (grades && grades.length > 0) {
      let total = 0
      Object.values(payload.empty_seats_by_grade).forEach(v => {
        if (typeof v === 'number' && !isNaN(v)) total += v
      })
      payload.empty_seats = total
      payload.empty_seats_by_grade = JSON.stringify(payload.empty_seats_by_grade)
    } else {
      payload.empty_seats_by_grade = '{}'
    }

    try {
      const res = await fetch('http://127.0.0.1:5002/api/sekolah/profile', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: JSON.stringify(payload)
      })
      const data = await res.json()
      if (data.success) {
        setSuccessMsg(data.message)
        fetchData() // Refresh
      } else {
        if (data.errors) {
          setErrorMsg(data.errors.join(', '))
        } else {
          setErrorMsg(data.message || 'Gagal menyimpan profil.')
        }
      }
    } catch (err) {
      setErrorMsg('Gagal menyimpan. Periksa koneksi.')
    } finally {
      setSaving(false)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin"></div>
          <p className="text-slate-500 font-medium animate-pulse">Memuat data profil...</p>
        </div>
      </div>
    )
  }

  if (!school) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 p-6">
        <div className="bg-white p-8 rounded-3xl shadow-xl shadow-slate-200/50 max-w-md text-center border border-slate-100">
          <div className="w-20 h-20 bg-red-100 text-red-500 rounded-full flex items-center justify-center mx-auto mb-6">
            <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
          </div>
          <h2 className="text-xl font-bold text-slate-800 mb-2">Akses Ditolak</h2>
          <p className="text-slate-500">{errorMsg || 'Sesi Anda telah habis atau Anda tidak memiliki akses ke halaman ini.'}</p>
        </div>
      </div>
    )
  }

  const jenjangUpper = school.jenjang?.toUpperCase() || ''
  const gradeLevels = GRADE_MAP[jenjangUpper] || []

  return (
    <div className="min-h-screen bg-[#F8FAFC] py-8 sm:py-12 px-4 sm:px-6 lg:px-8 font-sans selection:bg-indigo-100 selection:text-indigo-900">
      <div className="max-w-[1280px] mx-auto">
        
        {/* Header Section */}
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-600 to-violet-700 shadow-2xl shadow-indigo-600/20 mb-8">
          <div className="absolute top-0 right-0 -mt-16 -mr-16 w-64 h-64 bg-white opacity-5 rounded-full blur-3xl"></div>
          <div className="absolute bottom-0 left-0 -mb-16 -ml-16 w-80 h-80 bg-white opacity-10 rounded-full blur-3xl"></div>
          
          <div className="relative px-8 py-10 sm:px-12 sm:py-14 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6">
            <div className="flex items-center gap-5">
              <div className="w-16 h-16 bg-white/20 backdrop-blur-md border border-white/30 rounded-2xl flex items-center justify-center text-white shadow-inner">
                <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>
              </div>
              <div>
                <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight drop-shadow-sm">Pengaturan Profil Sekolah</h1>
                <p className="text-indigo-100 font-medium mt-1 text-sm sm:text-base">Perbarui informasi, kontak, dan kanal sekolah Anda.</p>
              </div>
            </div>
            <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-xl px-4 py-2 text-white">
              <span className="text-xs uppercase tracking-wider font-bold text-indigo-200 block mb-0.5">Sekolah Saat Ini</span>
              <span className="font-bold">{school.name}</span>
            </div>
          </div>
        </div>

        {/* Alerts */}
        {errorMsg && (
          <div className="mb-6 p-4 rounded-2xl bg-red-50 border border-red-100 flex items-start gap-3 animate-in fade-in slide-in-from-top-4">
            <div className="mt-0.5 text-red-500">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            </div>
            <div>
              <h3 className="font-bold text-red-800">Gagal Menyimpan Data</h3>
              <p className="text-sm text-red-600 mt-1">{errorMsg}</p>
            </div>
          </div>
        )}

        {successMsg && (
          <div className="mb-6 p-4 rounded-2xl bg-emerald-50 border border-emerald-100 flex items-start gap-3 animate-in fade-in slide-in-from-top-4">
            <div className="mt-0.5 text-emerald-500">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            </div>
            <div>
              <h3 className="font-bold text-emerald-800">Berhasil</h3>
              <p className="text-sm text-emerald-600 mt-1">{successMsg}</p>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          
          {/* Main Form Area */}
          <div className="lg:col-span-8 space-y-8">
            <form onSubmit={handleSubmit} className="space-y-8">
              
              {/* Section 1: Identitas Sekolah */}
              <div className="bg-white rounded-3xl p-6 sm:p-8 shadow-sm border border-slate-200/60 relative overflow-hidden group hover:shadow-md transition-shadow">
                <div className="absolute top-0 left-0 w-1 h-full bg-indigo-500"></div>
                <h2 className="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2">
                  <div className="p-1.5 bg-indigo-50 text-indigo-600 rounded-lg"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg></div>
                  Identitas & Lokasi
                </h2>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-2">NPSN</label>
                    <div className="relative">
                      <input type="text" readOnly value={school.npsn || '-'} className="w-full bg-slate-50 border border-slate-200 text-slate-500 rounded-xl px-4 py-2.5 font-medium focus:outline-none" />
                      <button type="button" onClick={() => navigator.clipboard.writeText(school.npsn)} className="absolute right-2 top-1.5 p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3"/></svg>
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-2">Link Google Maps <span className="text-red-500">*</span></label>
                    <input type="url" required value={formData.gmaps_url} onChange={e => setFormData({...formData, gmaps_url: e.target.value})} placeholder="https://maps.app.goo.gl/..." className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-2.5 font-medium focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all outline-none" />
                  </div>

                  <div className="md:col-span-2">
                    <label className="block text-sm font-bold text-slate-700 mb-2">Alamat Lengkap <span className="text-red-500">*</span></label>
                    <textarea required value={formData.alamat} onChange={e => setFormData({...formData, alamat: e.target.value})} rows={2} className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-3 font-medium focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all outline-none resize-y"></textarea>
                  </div>

                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-2">Kecamatan <span className="text-red-500">*</span></label>
                    <select required value={formData.kecamatan_id} onChange={handleKecamatanChange} className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-2.5 font-medium focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all outline-none appearance-none">
                      <option value="">-- Pilih Kecamatan --</option>
                      {kecamatanList.map(k => <option key={k.id} value={k.id}>{k.name}</option>)}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-2">Kelurahan <span className="text-red-500">*</span></label>
                    <select required value={formData.kelurahan_id} onChange={e => setFormData({...formData, kelurahan_id: e.target.value})} className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-2.5 font-medium focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all outline-none appearance-none">
                      <option value="">-- Pilih Kelurahan --</option>
                      {filteredKelurahan.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                    </select>
                  </div>

                  <div className="grid grid-cols-3 gap-4 md:col-span-2">
                    <div>
                      <label className="block text-sm font-bold text-slate-700 mb-2">RT <span className="text-red-500">*</span></label>
                      <input type="text" required maxLength={3} pattern="[0-9]{3}" value={formData.rt} onChange={e => setFormData({...formData, rt: e.target.value})} placeholder="001" className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-2.5 font-medium focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all outline-none text-center" />
                    </div>
                    <div>
                      <label className="block text-sm font-bold text-slate-700 mb-2">RW <span className="text-red-500">*</span></label>
                      <input type="text" required maxLength={3} pattern="[0-9]{3}" value={formData.rw} onChange={e => setFormData({...formData, rw: e.target.value})} placeholder="001" className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-2.5 font-medium focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all outline-none text-center" />
                    </div>
                    <div>
                      <label className="block text-sm font-bold text-slate-700 mb-2">Kode Pos <span className="text-red-500">*</span></label>
                      <input type="text" required maxLength={5} pattern="[0-9]{5}" value={formData.postal_code} onChange={e => setFormData({...formData, postal_code: e.target.value})} placeholder="14xxx" className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-2.5 font-medium focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all outline-none text-center" />
                    </div>
                  </div>
                </div>
              </div>

              {/* Section 2: Data Pendidikan & Kapasitas */}
              <div className="bg-white rounded-3xl p-6 sm:p-8 shadow-sm border border-slate-200/60 relative overflow-hidden group hover:shadow-md transition-shadow">
                <div className="absolute top-0 left-0 w-1 h-full bg-emerald-500"></div>
                <h2 className="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2">
                  <div className="p-1.5 bg-emerald-50 text-emerald-600 rounded-lg"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"/></svg></div>
                  Data Siswa & Pendidik
                </h2>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-2">Jml. Siswa Keseluruhan <span className="text-red-500">*</span></label>
                    <input type="number" min="0" required value={formData.student_count} onChange={e => setFormData({...formData, student_count: e.target.value})} className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-2.5 font-medium focus:ring-4 focus:ring-emerald-500/20 focus:border-emerald-500 transition-all outline-none" />
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-2">Jml. Siswa Inklusi <span className="text-red-500">*</span></label>
                    <input type="number" min="0" required value={formData.inclusion_student_count} onChange={e => setFormData({...formData, inclusion_student_count: e.target.value})} className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-2.5 font-medium focus:ring-4 focus:ring-emerald-500/20 focus:border-emerald-500 transition-all outline-none" />
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-2">Jml. Guru <span className="text-red-500">*</span></label>
                    <input type="number" min="0" required value={formData.teacher_count} onChange={e => setFormData({...formData, teacher_count: e.target.value})} className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-2.5 font-medium focus:ring-4 focus:ring-emerald-500/20 focus:border-emerald-500 transition-all outline-none" />
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-2">Jml. Tenaga Kependidikan <span className="text-red-500">*</span></label>
                    <input type="number" min="0" required value={formData.staff_count} onChange={e => setFormData({...formData, staff_count: e.target.value})} className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-2.5 font-medium focus:ring-4 focus:ring-emerald-500/20 focus:border-emerald-500 transition-all outline-none" />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-sm font-bold text-slate-700 mb-2">Jml. Rombel (Rombongan Belajar) <span className="text-red-500">*</span></label>
                    <input type="number" min="0" required value={formData.rombel_count} onChange={e => setFormData({...formData, rombel_count: e.target.value})} className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-2.5 font-medium focus:ring-4 focus:ring-emerald-500/20 focus:border-emerald-500 transition-all outline-none md:w-1/2" />
                  </div>
                </div>

                <div className="bg-emerald-50/50 rounded-2xl p-5 border border-emerald-100/50">
                  <h3 className="font-bold text-slate-800 mb-4 flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
                    Jumlah Bangku Kosong
                  </h3>
                  {gradeLevels.length > 0 ? (
                    <>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                        {gradeLevels.map(g => (
                          <div key={g}>
                            <label className="block text-xs font-bold text-slate-600 mb-1">{getGradeLabel(g, jenjangUpper)} <span className="text-red-500">*</span></label>
                            <input type="number" min="0" required value={formData.empty_seats_by_grade[g] ?? ''} onChange={e => handleEmptySeatChange(g, e.target.value)} className="w-full bg-white border border-slate-300 text-slate-900 rounded-lg px-3 py-2 text-sm font-medium focus:ring-4 focus:ring-emerald-500/20 focus:border-emerald-500 transition-all outline-none text-center" />
                          </div>
                        ))}
                      </div>
                      <p className="text-xs text-slate-500 mt-4 italic">* Isi jumlah bangku kosong (kapasitas sisa) untuk setiap tingkatan kelas sesuai jenjang {school.jenjang}.</p>
                    </>
                  ) : (
                    <div>
                      <label className="block text-sm font-bold text-slate-700 mb-2">Total Bangku Kosong <span className="text-red-500">*</span></label>
                      <input type="number" min="0" required value={formData.empty_seats} onChange={e => setFormData({...formData, empty_seats: e.target.value})} className="w-full md:w-1/2 bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-2.5 font-medium focus:ring-4 focus:ring-emerald-500/20 focus:border-emerald-500 transition-all outline-none" />
                    </div>
                  )}
                </div>
              </div>

              {/* Section 3: Kontak & Medsos */}
              <div className="bg-white rounded-3xl p-6 sm:p-8 shadow-sm border border-slate-200/60 relative overflow-hidden group hover:shadow-md transition-shadow">
                <div className="absolute top-0 left-0 w-1 h-full bg-sky-500"></div>
                <h2 className="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2">
                  <div className="p-1.5 bg-sky-50 text-sky-600 rounded-lg"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 8h2a2 2 0 012 2v6a2 2 0 01-2 2h-2v4l-4-4H9a1.994 1.994 0 01-1.414-.586m0 0L11 14h4a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2v4l.586-.586z"/></svg></div>
                  Kontak & Sosial Media
                </h2>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8 border-b border-slate-100 pb-8">
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-2">No. Telp Sekolah <span className="text-red-500">*</span></label>
                    <input type="text" required pattern="^[0-9]+$" value={formData.school_phone} onChange={e => setFormData({...formData, school_phone: e.target.value})} placeholder="021..." className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-2.5 font-medium focus:ring-4 focus:ring-sky-500/20 focus:border-sky-500 transition-all outline-none" />
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-2">No. Telp Koordinator/Operator <span className="text-red-500">*</span></label>
                    <input type="text" required pattern="^[0-9]+$" value={formData.coordinator_phone} onChange={e => setFormData({...formData, coordinator_phone: e.target.value})} placeholder="08..." className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-2.5 font-medium focus:ring-4 focus:ring-sky-500/20 focus:border-sky-500 transition-all outline-none" />
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-2">Email CS Sekolah <span className="text-red-500">*</span></label>
                    <input type="email" required value={formData.cs_email} onChange={e => setFormData({...formData, cs_email: e.target.value})} placeholder="cs@sekolah.sch.id" className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-2.5 font-medium focus:ring-4 focus:ring-sky-500/20 focus:border-sky-500 transition-all outline-none" />
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-2">Fax (Opsional)</label>
                    <input type="text" value={formData.fax} onChange={e => setFormData({...formData, fax: e.target.value})} placeholder="021..." className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-2.5 font-medium focus:ring-4 focus:ring-sky-500/20 focus:border-sky-500 transition-all outline-none" />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-bold text-slate-600 mb-2">Website</label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"/></svg></div>
                      <input type="url" value={formData.website} onChange={e => setFormData({...formData, website: e.target.value})} placeholder="https://..." className="w-full bg-slate-50 border border-slate-300 text-slate-900 rounded-xl pl-10 pr-4 py-2.5 text-sm font-medium focus:ring-4 focus:ring-sky-500/20 focus:border-sky-500 focus:bg-white transition-all outline-none" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-slate-600 mb-2">Instagram</label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">@</div>
                      <input type="text" value={formData.instagram} onChange={e => setFormData({...formData, instagram: e.target.value})} placeholder="username" className="w-full bg-slate-50 border border-slate-300 text-slate-900 rounded-xl pl-10 pr-4 py-2.5 text-sm font-medium focus:ring-4 focus:ring-sky-500/20 focus:border-sky-500 focus:bg-white transition-all outline-none" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-slate-600 mb-2">YouTube</label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg></div>
                      <input type="text" value={formData.youtube} onChange={e => setFormData({...formData, youtube: e.target.value})} placeholder="URL Channel" className="w-full bg-slate-50 border border-slate-300 text-slate-900 rounded-xl pl-10 pr-4 py-2.5 text-sm font-medium focus:ring-4 focus:ring-sky-500/20 focus:border-sky-500 focus:bg-white transition-all outline-none" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-slate-600 mb-2">Telegram</label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/></svg></div>
                      <input type="text" value={formData.telegram} onChange={e => setFormData({...formData, telegram: e.target.value})} placeholder="username atau url" className="w-full bg-slate-50 border border-slate-300 text-slate-900 rounded-xl pl-10 pr-4 py-2.5 text-sm font-medium focus:ring-4 focus:ring-sky-500/20 focus:border-sky-500 focus:bg-white transition-all outline-none" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-slate-600 mb-2">TikTok</label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">@</div>
                      <input type="text" value={formData.tiktok} onChange={e => setFormData({...formData, tiktok: e.target.value})} placeholder="username" className="w-full bg-slate-50 border border-slate-300 text-slate-900 rounded-xl pl-10 pr-4 py-2.5 text-sm font-medium focus:ring-4 focus:ring-sky-500/20 focus:border-sky-500 focus:bg-white transition-all outline-none" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-slate-600 mb-2">WA Channel</label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 8h2a2 2 0 012 2v6a2 2 0 01-2 2h-2v4l-4-4H9a1.994 1.994 0 01-1.414-.586m0 0L11 14h4a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2v4l.586-.586z"/></svg></div>
                      <input type="text" value={formData.wa_channel} onChange={e => setFormData({...formData, wa_channel: e.target.value})} placeholder="URL WA Channel" className="w-full bg-slate-50 border border-slate-300 text-slate-900 rounded-xl pl-10 pr-4 py-2.5 text-sm font-medium focus:ring-4 focus:ring-sky-500/20 focus:border-sky-500 focus:bg-white transition-all outline-none" />
                    </div>
                  </div>
                </div>
              </div>

              {/* Submit Area */}
              <div className="flex items-center justify-end pt-4 pb-12">
                <button 
                  type="submit" 
                  disabled={saving}
                  className="px-8 py-3.5 bg-gradient-to-r from-indigo-600 to-violet-700 text-white rounded-xl font-bold text-lg hover:from-indigo-700 hover:to-violet-800 focus:ring-4 focus:ring-indigo-500/30 transition-all transform hover:-translate-y-0.5 active:translate-y-0 shadow-xl shadow-indigo-600/30 disabled:opacity-70 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {saving ? (
                    <>
                      <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                      Menyimpan...
                    </>
                  ) : (
                    <>
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"/></svg>
                      Simpan Profil Sekolah
                    </>
                  )}
                </button>
              </div>

            </form>
          </div>

          {/* Right Sidebar */}
          <div className="lg:col-span-4 space-y-6">
            <div className="bg-white rounded-3xl p-6 shadow-sm border border-slate-200/60 sticky top-8">
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white font-black text-xl shadow-md shadow-indigo-200 flex-shrink-0">
                  {school.name.charAt(0).toUpperCase()}
                </div>
                <div>
                  <h3 className="font-bold text-slate-800 leading-tight">{school.name}</h3>
                  <p className="text-xs text-slate-500 mt-1">{school.npsn} • {school.jenjang}</p>
                </div>
              </div>

              {missingFields.length > 0 && (
                <div className="mt-6 pt-6 border-t border-slate-100">
                  <div className="bg-amber-50 border border-amber-100 rounded-2xl p-4">
                    <h4 className="font-bold text-amber-800 text-sm flex items-center gap-2 mb-2">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
                      Data Wajib Belum Lengkap
                    </h4>
                    <ul className="text-xs text-amber-700 space-y-1 list-disc pl-5">
                      {missingFields.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                  </div>
                </div>
              )}
              
              <div className="mt-6 p-4 bg-slate-50 rounded-2xl border border-slate-100">
                <p className="text-xs text-slate-500 leading-relaxed">
                  Tanda <span className="text-red-500 font-bold">*</span> wajib diisi. Pastikan informasi sekolah Anda selalu *up-to-date* untuk memudahkan koordinasi dengan Sudin Pendidikan.
                </p>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}
