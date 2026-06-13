'use client'

import React, { useEffect, useState, useRef } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'

const MIX_DURATION = 3 * 60 * 1000

const AutoScrollList = ({ children, isScrollable }: { children: React.ReactNode, isScrollable: boolean }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    if (!isScrollable) return;
    
    let animationFrameId: number;
    let timeoutId: NodeJS.Timeout;
    let direction = 1;
    let isPaused = true;
    
    const startScrolling = () => {
      if (!containerRef.current) return;
      const el = containerRef.current;
      const maxScroll = el.scrollHeight - el.clientHeight;
      
      if (!isPaused) {
        el.scrollTop += 0.5 * direction; // kecepatan scroll
        
        // Cek apakah sudah sampai bawah atau atas
        if (direction === 1 && Math.ceil(el.scrollTop) >= maxScroll) {
          isPaused = true;
          direction = -1;
          el.scrollTop = maxScroll;
          
          timeoutId = setTimeout(() => {
            isPaused = false;
            animationFrameId = requestAnimationFrame(startScrolling);
          }, 2000); // stop 2 detik di bawah
          return;
        }

        if (direction === -1 && el.scrollTop <= 0) {
          isPaused = true;
          direction = 1;
          el.scrollTop = 0;

          timeoutId = setTimeout(() => {
            isPaused = false;
            animationFrameId = requestAnimationFrame(startScrolling);
          }, 2000); // stop 2 detik di atas
          return;
        }
      }
      
      animationFrameId = requestAnimationFrame(startScrolling);
    };
    
    // Stop awal selama 2 detik sebelum mulai
    timeoutId = setTimeout(() => {
      isPaused = false;
      animationFrameId = requestAnimationFrame(startScrolling);
    }, 2000);
    
    return () => {
      cancelAnimationFrame(animationFrameId);
      clearTimeout(timeoutId);
    };
  }, [isScrollable]);

  return (
    <div 
      ref={containerRef} 
      className={`space-y-3 ${isScrollable ? 'overflow-y-hidden' : ''}`}
      style={{ maxHeight: isScrollable ? '470px' : 'none' }}
    >
      {children}
    </div>
  )
}

interface Sekolah {
  sekolah_id: string
  npsn: string
  nama: string
  [key: string]: unknown
}

interface Statistik {
  sekolah?: string
  rekap?: unknown
  [key: string]: unknown
}

interface KecamatanStats {
  [key: string]: {
    total_sekolah: number
    sekolah: Array<{
      nama: string
      npsn: string
      usia_termuda: number
      usia_termuda_teks: string
      _sortHari: number
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
    "20105106", "20100596", "20104984", "20104994", "20100593", "20104916", "20104917", "70010608", "20109937", "20105058"
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
  const router = useRouter()
  const [kecamatanStats, setKecamatanStats] = useState<KecamatanStats>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [, setLastUpdate] = useState<Date>(new Date())
  const [isLoaded, setIsLoaded] = useState(false)
  const [countdown, setCountdown] = useState(60)
  const [mixEnabled, setMixEnabled] = useState(false)
  const [mixElapsed, setMixElapsed] = useState(0)

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
      const statistikResponse: { data?: Record<string, Statistik> } = await statistikRes.json()
      
      // Create statistik map for quick lookup
      const statistikMap = new Map(Object.entries(statistikResponse.data || {}))

      // Helper function to extract usia termuda from rekap array
      // Rekap format: [[" 6 th 9 bl 12 hr", "10 th 1 bl 30 hr", ...]] (nested array)
      const extractUsiaTermuda = (rekap: unknown): { totalHari: number, usiaTahun: number, teks: string } => {
        if (!rekap) return { totalHari: 0, usiaTahun: 0, teks: 'N/A' }
        
        const parseStr = (str: string) => {
          let totalHari = 0;
          let usiaTahun = 0;
          const matchTh = str.match(/(\d+)\s+th/);
          if (matchTh) {
            usiaTahun = parseInt(matchTh[1], 10);
            totalHari += usiaTahun * 365;
          }
          const matchBl = str.match(/(\d+)\s+bl/);
          if (matchBl) totalHari += parseInt(matchBl[1], 10) * 30;
          const matchHr = str.match(/(\d+)\s+hr/);
          if (matchHr) totalHari += parseInt(matchHr[1], 10);
          
          const formattedTeks = str.trim()
            .replace(/\s*th/gi, 'T')
            .replace(/\s*bl/gi, 'B')
            .replace(/\s*hr/gi, 'H');
            
          return { totalHari, usiaTahun, teks: formattedTeks }
        }

        // Handle nested array structure: rekap is array containing array of age strings
        if (Array.isArray(rekap) && rekap.length > 0) {
          const ageArray = rekap[0]
          
          // If rekap[0] is also an array, get its first element
          if (Array.isArray(ageArray) && ageArray.length > 0) {
            const firstAge = ageArray[0]
            if (typeof firstAge === 'string') {
              return parseStr(firstAge)
            }
          }
          
          // If rekap[0] is a string directly
          if (typeof ageArray === 'string') {
            return parseStr(ageArray)
          }
        }
        
        return { totalHari: 0, usiaTahun: 0, teks: 'N/A' }
      }

      // Group sekolah by kecamatan using NPSN
      const kecamatanMap: { [key: string]: Array<Sekolah & { totalHari: number, usiaTahun: number, teks: string }> } = {}
      
      sekolahData.forEach(sekolah => {
        const kecamatan = getKecamatanFromNpsn(sekolah.npsn)
        if (kecamatan) {
          const stat = statistikMap.get(sekolah.sekolah_id)
          const usiaData = stat ? extractUsiaTermuda(stat.rekap) : { totalHari: 0, usiaTahun: 0, teks: 'N/A' }
          
          if (!kecamatanMap[kecamatan]) {
            kecamatanMap[kecamatan] = []
          }
          kecamatanMap[kecamatan].push({
            ...sekolah,
            totalHari: usiaData.totalHari,
            usiaTahun: usiaData.usiaTahun,
            teks: usiaData.teks
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
              nama: (s.nama || 'N/A').replace(/^SDN\s+/i, ''),
              npsn: s.npsn || 'N/A',
              usia_termuda: s.usiaTahun,
              usia_termuda_teks: s.teks,
              _sortHari: s.totalHari
            }))
            .sort((a, b) => a._sortHari - b._sortHari)
        }
      })

      setKecamatanStats(stats)
      setLastUpdate(new Date())
      setCountdown(60)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Terjadi kesalahan')
      console.error('Error fetching SPMB data:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setIsLoaded(true)
    })
    const initialFetch = window.setTimeout(fetchData, 0)

    // Set up auto-refresh setiap 60 detik
    const interval = setInterval(fetchData, 60 * 1000)

    return () => {
      window.cancelAnimationFrame(frame)
      window.clearTimeout(initialFetch)
      clearInterval(interval)
    }
  }, [])

  useEffect(() => {
    if (loading) return
    const timer = setInterval(() => {
      setCountdown(prev => (prev <= 1 ? 60 : prev - 1))
    }, 1000)
    return () => clearInterval(timer)
  }, [loading])

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setMixEnabled(new URLSearchParams(window.location.search).get('mix') === '1')
    })
    return () => window.cancelAnimationFrame(frame)
  }, [])

  useEffect(() => {
    if (!mixEnabled) return

    const startedAt = Date.now()
    const interval = window.setInterval(() => {
      setMixElapsed(Math.min(Date.now() - startedAt, MIX_DURATION))
    }, 1000)
    const timeout = window.setTimeout(() => {
      router.replace('/live-spmb-smp?mix=1')
    }, MIX_DURATION)

    return () => {
      window.clearInterval(interval)
      window.clearTimeout(timeout)
    }
  }, [mixEnabled, router])

  const mixProgressPercent = mixEnabled ? Math.min(100, (mixElapsed / MIX_DURATION) * 100) : 0

  return (
    <main className="min-h-screen bg-gradient-to-br from-orange-50 via-white to-red-50 relative">
      {mixEnabled && (
        <div className="fixed top-0 left-0 right-0 z-50 h-1 bg-orange-100">
          <div
            className="h-full bg-gradient-to-r from-orange-500 via-red-500 to-emerald-500 transition-[width] duration-1000 ease-linear"
            style={{ width: `${mixProgressPercent}%` }}
          />
        </div>
      )}

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
          <div className="flex flex-col lg:flex-row items-center justify-between mb-8 gap-6 lg:gap-0">
            <div className="w-full lg:w-1/3 flex justify-start">
              <Link href="/live-spmb" className="inline-flex items-center gap-2 hover:opacity-70 transition-opacity">
                <svg className="w-5 h-5 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
                <span className="text-sm font-semibold text-slate-600">Kembali</span>
              </Link>
            </div>
            
            <div className="w-full lg:w-1/3 text-center">
              <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900 whitespace-nowrap">
                Live SPMB{' '}
                <span className="bg-gradient-to-r from-orange-500 to-red-500 bg-clip-text text-transparent">
                  SD 2026
                </span>
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 mt-2">Zonasi Jakarta Utara</p>
            </div>
            
            <div className="w-full lg:w-1/3 flex items-center justify-center lg:justify-end gap-2">
              <div className="flex items-center gap-2 px-3 py-1.5 bg-white/80 rounded-full border border-orange-200/50 shadow-sm">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-xs font-semibold text-emerald-700 whitespace-nowrap">Live</span>
              </div>
              <button
                onClick={() => { fetchData(); setCountdown(60) }}
                disabled={loading}
                title="Refresh sekarang"
                className="relative inline-flex items-center gap-2 px-3 py-1.5 bg-white/80 rounded-full border border-orange-200/50 shadow-sm hover:bg-white transition-colors disabled:opacity-50 shrink-0"
              >
                {/* Mini countdown ring */}
                <div className="relative w-5 h-5 shrink-0">
                  <svg className="absolute inset-0 w-full h-full -rotate-90" viewBox="0 0 36 36">
                    <circle cx="18" cy="18" r="14" fill="none" stroke="#d1fae5" strokeWidth="4" />
                    <circle
                      cx="18" cy="18" r="14"
                      fill="none"
                      stroke="#059669"
                      strokeWidth="4"
                      strokeDasharray={`${2 * Math.PI * 14}`}
                      strokeDashoffset={`${2 * Math.PI * 14 * (1 - countdown / 60)}`}
                      strokeLinecap="round"
                      style={{ transition: 'stroke-dashoffset 0.9s linear' }}
                    />
                  </svg>
                  {loading ? (
                    <svg className="absolute inset-0 w-full h-full text-slate-500 animate-spin p-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                  ) : (
                    <span className="absolute inset-0 flex items-center justify-center text-[9px] font-extrabold text-emerald-700 leading-none">{countdown}</span>
                  )}
                </div>
                <span className="text-xs font-semibold text-slate-600">Refresh</span>
              </button>
            </div>
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
                  <div className="mb-4 pb-4 border-b border-slate-200/50 flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-lg font-bold text-slate-900 truncate">
                      {kecamatan}
                    </h3>
                  </div>

                  {/* Sekolah List */}
                  <AutoScrollList isScrollable={data.sekolah.length > 8}>
                    {data.sekolah.length > 0 ? (
                      data.sekolah.map((sekolah, i) => (
                        <div
                          key={i}
                          className="px-3 py-2 bg-gradient-to-br from-orange-50 to-red-50 rounded-lg border border-orange-100/50 hover:border-orange-300 transition-colors flex items-center justify-between gap-3"
                        >
                          <p className="text-sm font-semibold text-slate-900 line-clamp-2 flex-1">
                            {sekolah.nama}
                          </p>
                          <span className="inline-flex items-center px-3 py-1 bg-orange-100 rounded text-sm font-bold text-orange-700 shrink-0 whitespace-nowrap">
                            {sekolah.usia_termuda_teks}
                          </span>
                        </div>
                      ))
                    ) : (
                      <p className="text-xs text-slate-500 italic">Tidak ada data</p>
                    )}
                  </AutoScrollList>


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
