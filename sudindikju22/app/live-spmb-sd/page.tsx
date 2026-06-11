'use client'

import React, { useEffect, useState } from 'react'
import Link from 'next/link'

interface Sekolah {
  sekolah_id: string
  npsn: string
  nama: string
  [key: string]: any
}

interface Statistik {
  sekolah: string
  rekap: string
  [key: string]: any
}

interface KecamatanData {
  nama: string
  sekolah: Sekolah[]
  statistik: Map<string, Statistik>
}

interface KecamatanStats {
  [key: string]: {
    total_sekolah: number
    sekolah: Array<{
      nama: string
      npsn: string
      usia_termuda: number
    }>
  }
}

const KECAMATAN_NPSN_MAP: { [key: string]: string[] } = {
  'Cilincing': [
    "20105076", "20101028", "20104847", "70009509", "20104844", "20104845", "20101026", "20104846", "20101010", "20104871",
    "20105011", "20101093", "20105075", "20105066", "20101003", "20104991", "20104848", "20101001", "20100997", "20101005",
    "20104983", "20105014", "20105017", "20105083", "69857156", "20104982", "20104873", "20110224", "20109372", "20104872",
    "69980873", "20104995", "20105027", "20104840", "20109315", "20100677", "20100679", "20104907", "20109047", "20104839",
    "20105045", "20100633", "20100682", "20100684", "20100686", "20100582", "20100584", "20100586", "20104911", "20104975",
    "20105025", "20105034", "20109083", "20105105", "20105118", "20105137", "20105047", "20105044", "20109629", "69984785",
    "20104914", "20100591", "20104915", "69952902", "69922219", "20104912", "69913134", "20105031", "20105071", "20105072",
    "20105106", "20100596", "20104984", "20104994", "20100593", "20104916", "20104917", "70010608", "20109937", "20105058",
    "69883487", "20109039", "69889102", "69856890", "20105033", "69892595", "69830128", "20104861", "20109346", "20104992",
    "20109172", "20109521", "20109312", "20109938", "20104863", "20104865", "20105120", "20105122", "69857086", "69888567",
    "20109384", "20105060", "20104886", "69938151", "20109528", "69879019", "20109397", "20105124", "20105125", "69964730",
    "20104978", "20104880", "20104882", "20104884", "20104885", "20104977", "20105024", "20105101", "20121012", "20105043",
    "20105110", "20105003", "20105087", "20105112", "20105134", "20100884", "20105064", "20101061", "20104985", "20104869",
    "20101054", "20101057", "20101059", "20101062", "20105054", "20109343", "20105133", "69949704", "20100647", "20100648",
    "20100690", "20100691", "20105113", "20109525", "69988491", "20100645", "20100669", "20105131", "20104974", "20100699",
    "20100702", "20100693", "20100695", "20100697", "20100689", "20100671", "20100673", "20104906", "20104976", "20105001",
    "69912051", "20109251", "20105073", "20100568", "20100565", "69963071", "20104954", "20104956", "20100577", "20105108",
    "20104952", "20104958", "20100575", "20100598", "20100618", "20100619", "20104963", "20100622", "20100624", "20100625",
    "20105128", "20105129"
  ],
  'Koja': [
    "20105110", "20105003", "20105087", "20105112", "20105134", "20100884", "20105064", "20101061", "20104985", "20104869",
    "20101054", "20101057", "20101059", "20101062", "20105054", "20109343", "20105133", "69949704", "20100647", "20100648",
    "20100690", "20100691", "20105113", "20109525", "69988491", "20100645", "20100669", "20105131", "20104974", "20100699",
    "20100702", "20100693", "20100695", "20100697", "20100689", "20100671", "20100673", "20104906", "20104976", "20105001",
    "69912051", "20109251", "20105073", "20100568", "20100565", "69963071", "20104954", "20104956", "20100577", "20105108",
    "20104952", "20104958", "20100575", "20100598", "20100618", "20100619", "20104963", "20100622", "20100624", "20100625",
    "20105128", "20105129"
  ],
  'Kelapa Gading': [
    "69883487", "20109039", "69889102", "69856890", "20105033", "69892595", "69830128", "20104861", "20109346", "20104992",
    "20109172", "20109521", "20109312", "20109938", "20104863", "20104865", "20105120", "20105122", "69857086", "69888567",
    "20109384", "20105060", "20104886", "69938151", "20109528", "69879019", "20109397", "20105124", "20105125", "69964730",
    "20104978", "20104880", "20104882", "20104884", "20104885", "20104977", "20105024", "20105101", "20121012", "20105043"
  ]
}

// Helper function to get kecamatan from NPSN
const getKecamatanFromNpsn = (npsn: string): string | null => {
  for (const [kecamatan, npsns] of Object.entries(KECAMATAN_NPSN_MAP)) {
    if (npsns.includes(npsn)) {
      return kecamatan
    }
  }
  return null
}

export default function LiveSPMBSD() {
  const [kecamatanStats, setKecamatanStats] = useState<KecamatanStats>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date())
  const [isLoaded, setIsLoaded] = useState(false)

  const fetchData = async () => {
    try {
      setLoading(true)
      setError(null)

      // Fetch data sekolah
      const sekolahRes = await fetch(
        'https://arsip.spmb.id/2025/jakarta/sekolah/1-sd-zonasi.json'
      )
      if (!sekolahRes.ok) throw new Error('Gagal fetch data sekolah')
      const sekolahData: Sekolah[] = await sekolahRes.json()

      // Fetch data statistik
      const statistikRes = await fetch(
        'https://arsip.spmb.id/2025/jakarta/statistik/1-sd-zonasi.json'
      )
      if (!statistikRes.ok) throw new Error('Gagal fetch data statistik')
      const statistikResponse = await statistikRes.json()
      
      // Create statistik map for quick lookup
      const statistikMap = new Map(Object.entries(statistikResponse.data || {}))

      // Helper function to extract usia termuda from rekap array
      // Rekap format: [[" 6 th 9 bl 12 hr", "10 th 1 bl 30 hr", ...]] (nested array)
      const extractUsiaTermuda = (rekap: any): number => {
        if (!rekap) return 0
        
        // Handle nested array structure: rekap is array containing array of age strings
        if (Array.isArray(rekap) && rekap.length > 0) {
          let ageArray = rekap[0]
          
          // If rekap[0] is also an array, get its first element
          if (Array.isArray(ageArray) && ageArray.length > 0) {
            const firstAge = ageArray[0]
            if (typeof firstAge === 'string') {
              const match = firstAge.match(/(\d+)\s+th/)
              const usia = match ? parseInt(match[1], 10) : 0
              return usia
            }
          }
          
          // If rekap[0] is a string directly
          if (typeof ageArray === 'string') {
            const match = ageArray.match(/(\d+)\s+th/)
            const usia = match ? parseInt(match[1], 10) : 0
            return usia
          }
        }
        
        return 0
      }

      // Group sekolah by kecamatan using NPSN
      const kecamatanMap: { [key: string]: Array<Sekolah & { usia_termuda: number }> } = {}
      
      sekolahData.forEach(sekolah => {
        const kecamatan = getKecamatanFromNpsn(sekolah.npsn)
        if (kecamatan) {
          const stat = statistikMap.get(sekolah.sekolah_id) as any
          const usia_termuda = stat ? extractUsiaTermuda(stat.rekap) : 0
          
          if (!kecamatanMap[kecamatan]) {
            kecamatanMap[kecamatan] = []
          }
          kecamatanMap[kecamatan].push({
            ...sekolah,
            usia_termuda
          })
        }
      })

      // Process data untuk setiap kecamatan (ambil hanya 3 kecamatan tertentu)
      const stats: KecamatanStats = {}
      const kecamatanToShow = ['Cilincing', 'Koja', 'Kelapa Gading'].filter(k => kecamatanMap[k])

      kecamatanToShow.forEach(kecamatan => {
        const kecamatanSekolah = kecamatanMap[kecamatan]

        stats[kecamatan] = {
          total_sekolah: kecamatanSekolah.length,
          sekolah: kecamatanSekolah
            .map(s => ({
              nama: s.nama || 'N/A',
              npsn: s.npsn || 'N/A',
              usia_termuda: s.usia_termuda
            }))
            .sort((a, b) => a.usia_termuda - b.usia_termuda)
            .slice(0, 3) // Ambil 3 sekolah dengan usia termuda terkecil
        }
      })

      setKecamatanStats(stats)
      setLastUpdate(new Date())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Terjadi kesalahan')
      console.error('Error fetching SPMB data:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setIsLoaded(true)
    fetchData()

    // Set up auto-refresh setiap 5 menit
    const interval = setInterval(fetchData, 5 * 60 * 1000)

    return () => clearInterval(interval)
  }, [])

  return (
    <main className="min-h-screen bg-gradient-to-br from-orange-50 via-white to-red-50 relative">
      {/* Animated Background Pattern */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-[400px] h-[400px] bg-gradient-to-br from-orange-200/30 to-red-300/20 rounded-full blur-3xl animate-float" />
        <div className="absolute bottom-0 right-1/4 w-[350px] h-[350px] bg-gradient-to-br from-red-200/25 to-pink-300/15 rounded-full blur-3xl animate-float-delayed" />
        <div
          className="absolute inset-0 opacity-[0.02]"
          style={{
            backgroundImage: 'radial-gradient(circle, #f97316 1px, transparent 1px)',
            backgroundSize: '20px 20px'
          }}
        />
      </div>

      {/* Header */}
      <div className={`relative z-10 px-4 sm:px-6 py-6 transition-all duration-500 ${isLoaded ? 'opacity-100' : 'opacity-0'}`}>
        <div className="max-w-6xl mx-auto">
          <div className="flex items-center justify-between mb-8">
            <Link href="/" className="inline-flex items-center gap-2 hover:opacity-70 transition-opacity">
              <svg className="w-5 h-5 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              <span className="text-sm font-semibold text-slate-600">Kembali</span>
            </Link>
            <div className="text-center">
              <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900">
                Live SPMB{' '}
                <span className="bg-gradient-to-r from-orange-500 to-red-500 bg-clip-text text-transparent">
                  SD 2025
                </span>
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 mt-2">Zonasi Jakarta Utara</p>
            </div>
            <div className="w-20" /> {/* Spacer untuk alignment */}
          </div>

          {/* Update Info */}
          <div className="flex items-center justify-center gap-2 mb-6">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-white/80 rounded-full border border-orange-200/50 shadow-sm">
              <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-xs text-slate-600">
                Update terakhir: {lastUpdate.toLocaleTimeString('id-ID')}
              </span>
            </div>
            <button
              onClick={fetchData}
              disabled={loading}
              className="inline-flex items-center gap-2 px-3 py-1.5 bg-white/80 rounded-full border border-orange-200/50 shadow-sm hover:bg-white transition-colors disabled:opacity-50"
            >
              <svg
                className={`w-3.5 h-3.5 text-slate-600 ${loading ? 'animate-spin' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              <span className="text-xs font-semibold text-slate-600">Refresh</span>
            </button>
          </div>

          {/* Error Message */}
          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-700 font-semibold">⚠️ Error: {error}</p>
            </div>
          )}

          {/* Loading State */}
          {loading && Object.keys(kecamatanStats).length === 0 && (
            <div className="grid md:grid-cols-3 gap-6">
              {[1, 2, 3].map(i => (
                <div
                  key={i}
                  className="bg-white/60 backdrop-blur-sm rounded-xl p-6 border border-white/50 shadow-lg animate-pulse"
                >
                  <div className="h-6 bg-slate-200 rounded w-2/3 mb-4" />
                  <div className="space-y-3">
                    {[1, 2, 3].map(j => (
                      <div key={j} className="h-12 bg-slate-100 rounded" />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Kecamatan Cards */}
          {!loading && (
            <div className="grid md:grid-cols-3 gap-6">
              {Object.entries(kecamatanStats).map(([kecamatan, data], idx) => (
                <div
                  key={kecamatan}
                  className={`bg-white/60 backdrop-blur-sm rounded-xl p-6 border border-white/50 shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300 ${
                    isLoaded ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
                  }`}
                  style={{
                    transitionDelay: isLoaded ? `${300 + idx * 100}ms` : undefined
                  }}
                >
                  {/* Header */}
                  <div className="mb-4 pb-4 border-b border-slate-200/50">
                    <h3 className="text-lg font-bold text-slate-900">
                      {kecamatan}
                    </h3>
                    <p className="text-xs text-slate-500 mt-1">
                      {data.total_sekolah} sekolah terdaftar
                    </p>
                  </div>

                  {/* Sekolah List */}
                  <div className="space-y-3">
                    {data.sekolah.length > 0 ? (
                      data.sekolah.map((sekolah, i) => (
                        <div
                          key={i}
                          className="p-3 bg-gradient-to-br from-orange-50 to-red-50 rounded-lg border border-orange-100/50 hover:border-orange-300 transition-colors"
                        >
                          <p className="text-sm font-semibold text-slate-900 line-clamp-2">
                            {sekolah.nama}
                          </p>
                          <p className="text-xs text-slate-500 mt-1">NPSN: {sekolah.npsn}</p>
                          <div className="flex items-center gap-2 mt-2">
                            <span className="inline-flex items-center gap-1 px-2 py-1 bg-orange-100 rounded text-xs font-bold text-orange-700">
                              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                                <path d="M5.5 13a3.5 3.5 0 01-.369-6.98 4 4 0 117.753-1.3A4.5 4.5 0 1113.5 13H11V9.413l1.293 1.293a1 1 0 001.414-1.414l-3-3a1 1 0 00-1.414 0l-3 3a1 1 0 001.414 1.414L9 9.414V13H5.5z" />
                              </svg>
                              {sekolah.usia_termuda} thn
                            </span>
                          </div>
                        </div>
                      ))
                    ) : (
                      <p className="text-xs text-slate-500 italic">Tidak ada data</p>
                    )}
                  </div>

                  {/* Footer Stats */}
                  <div className="mt-4 pt-4 border-t border-slate-200/50">
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="p-2 bg-slate-50 rounded">
                        <p className="text-slate-500">Total Sekolah</p>
                        <p className="font-bold text-slate-900 text-lg">{data.total_sekolah}</p>
                      </div>
                      <div className="p-2 bg-slate-50 rounded">
                        <p className="text-slate-500">Rata-rata Usia</p>
                        <p className="font-bold text-slate-900 text-lg">
                          {data.sekolah.length > 0
                            ? (
                                data.sekolah.reduce((sum, s) => sum + s.usia_termuda, 0) /
                                data.sekolah.length
                              ).toFixed(1)
                            : 'N/A'}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <style jsx global>{`
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-15px); }
        }
        @keyframes float-delayed {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-10px); }
        }
        .animate-float { animation: float 6s ease-in-out infinite; }
        .animate-float-delayed { animation: float-delayed 8s ease-in-out infinite; animation-delay: -2s; }
      `}</style>
    </main>
  )
}
