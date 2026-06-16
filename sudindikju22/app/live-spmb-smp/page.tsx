'use client'

import React, { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'

const MIX_DURATION = 3 * 60 * 1000

const readJsonResponse = async (response: Response) => {
  const text = await response.text()
  if (!text) return {}

  try {
    return JSON.parse(text)
  } catch {
    throw new Error('API live SPMB belum mengembalikan JSON. Cek build/restart aplikasi dan response /api/live-spmb-smp.')
  }
}

const AutoScrollList = ({ children, isScrollable, maxHeight = '260px' }: { children: React.ReactNode, isScrollable: boolean, maxHeight?: string }) => {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isScrollable) return

    let animationFrameId: number
    let timeoutId: NodeJS.Timeout
    let direction = 1
    let isPaused = true

    const startScrolling = () => {
      if (!containerRef.current) return
      const el = containerRef.current
      const maxScroll = el.scrollHeight - el.clientHeight

      if (!isPaused) {
        el.scrollTop += 0.5 * direction

        if (direction === 1 && Math.ceil(el.scrollTop) >= maxScroll) {
          isPaused = true
          direction = -1
          el.scrollTop = maxScroll

          timeoutId = setTimeout(() => {
            isPaused = false
            animationFrameId = requestAnimationFrame(startScrolling)
          }, 2000)
          return
        }

        if (direction === -1 && el.scrollTop <= 0) {
          isPaused = true
          direction = 1
          el.scrollTop = 0

          timeoutId = setTimeout(() => {
            isPaused = false
            animationFrameId = requestAnimationFrame(startScrolling)
          }, 2000)
          return
        }
      }

      animationFrameId = requestAnimationFrame(startScrolling)
    }

    timeoutId = setTimeout(() => {
      isPaused = false
      animationFrameId = requestAnimationFrame(startScrolling)
    }, 2000)

    return () => {
      cancelAnimationFrame(animationFrameId)
      clearTimeout(timeoutId)
    }
  }, [isScrollable])

  return (
    <div
      ref={containerRef}
      className={`space-y-1 ${isScrollable ? 'overflow-y-hidden' : ''}`}
      style={{ maxHeight: isScrollable ? maxHeight : 'none' }}
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
  rekap?: Array<Array<string | number>>
  [key: string]: unknown
}

interface StatistikResponse {
  data?: Record<string, Statistik>
  [key: string]: unknown
}

interface OfficialSPMBSmpResponse {
  smpSekolah?: Sekolah[]
  smpAkademik?: StatistikResponse
  smpNonAkademik?: StatistikResponse
  smaSekolah?: Sekolah[]
  smaAkademik?: StatistikResponse
  smaMpmAkademik?: StatistikResponse
  error?: string
}

interface SekolahNilai {
  nama: string
  npsn: string
  prestasi: string
  prestasiValue: number | null
  nonPrestasi: string
  nonPrestasiValue: number | null
  terbaikValue: number | null
}

interface KecamatanStats {
  [key: string]: {
    smp: SekolahNilai[]
    sma: SekolahNilai[]
  }
}

const KECAMATAN_NPSN_MAP: { [key: string]: string[] } = {
  Cilincing: [
    '20100749', '20100757', '20100759', '20100763', '20100766', '20100769', '20100773', '69800097'
  ],
  Koja: [
    '20100719', '20100740', '20100743', '20100744', '20100746', '20100752', '20100764', '20100768', '20106716'
  ],
  'Kelapa Gading': [
    '20100742', '20100760', '20100767'
  ]
}

const SMA_KECAMATAN_NPSN_MAP: { [key: string]: string[] } = {
  Cilincing: ['20100804', '20100805', '20100797', '20100795', '20100779', '20100781', '20100782', '70011683'],
  Koja: ['20100802', '20100806', '20107368', '20107369', '20100614', '20107385', '20107395', '20100801'],
  'Kelapa Gading': ['20100812', '20100796', '69977407', '20100600', '69968321', '69975652', '20100601', '20100604', '69889105', '69856892', '20177804', '69939320', '69879021', '20100616', '20109180', '20100608', '20107390', '20100799', '20100632', '20100778']
}

const getKecamatanFromNpsn = (npsn: string): string | null => {
  const normalizedNpsn = String(npsn)
  for (const [kecamatan, npsns] of Object.entries(KECAMATAN_NPSN_MAP)) {
    if (npsns.includes(normalizedNpsn)) return kecamatan
  }
  return null
}

const getSmaKecamatanFromNpsn = (npsn: string): string | null => {
  const normalizedNpsn = String(npsn)
  for (const [kecamatan, npsns] of Object.entries(SMA_KECAMATAN_NPSN_MAP)) {
    if (npsns.includes(normalizedNpsn)) return kecamatan
  }
  return null
}

const formatSchoolName = (nama: string) => (
  (nama || 'N/A')
    .replace(/^SMP\s+NEGERI\s+/i, 'SMPN ')
    .replace(/^SMA\s+NEGERI\s+/i, 'SMAN ')
    .replace(/^SMAS?\s+/i, '')
    .replace(/\s+JAKARTA$/i, '')
)

const getLowestScore = (statistik?: Statistik): { label: string, value: number | null } => {
  const rekap = statistik?.rekap
  if (!Array.isArray(rekap) || rekap.length === 0) return { label: 'N/A', value: null }

  const values = rekap
    .map(item => item?.[0])
    .map(item => {
      const value = Number(item)
      return Number.isFinite(value) ? value : null
    })
    .filter((value): value is number => value !== null)

  if (values.length === 0) return { label: 'N/A', value: null }

  const lowest = Math.min(...values)
  return { label: lowest.toFixed(2), value: lowest }
}

export default function LiveSPMBSMP() {
  const router = useRouter()
  const [kecamatanStats, setKecamatanStats] = useState<KecamatanStats>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [, setLastUpdate] = useState<Date>(new Date())
  const [isLoaded] = useState(true)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [countdown, setCountdown] = useState(60)
  const [mixEnabled, setMixEnabled] = useState(false)
  const [mixElapsed, setMixElapsed] = useState(0)

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen()
    } else {
      document.exitFullscreen()
    }
  }

  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [])

  const fetchData = async () => {
    try {
      setLoading(true)
      setError(null)

      const response = await fetch('/api/live-spmb-smp', { cache: 'no-store' })
      const officialData = await readJsonResponse(response) as OfficialSPMBSmpResponse

      if (!response.ok || officialData.error) {
        throw new Error(officialData.error || 'Gagal fetch data SPMB Jakarta SMP/SMA')
      }

      const sekolahData = Array.isArray(officialData.smpSekolah) ? officialData.smpSekolah : []
      const smaSekolahData = Array.isArray(officialData.smaSekolah) ? officialData.smaSekolah : []
      const prestasiMap = new Map<string, Statistik>(Object.entries(officialData.smpAkademik?.data || {}))
      const nonPrestasiMap = new Map<string, Statistik>(Object.entries(officialData.smpNonAkademik?.data || {}))
      const smaPrestasiMap = new Map<string, Statistik>(Object.entries(officialData.smaAkademik?.data || {}))
      const smaNonPrestasiMap = new Map<string, Statistik>(Object.entries(officialData.smaMpmAkademik?.data || {}))
      const kecamatanMap: { [key: string]: { smp: SekolahNilai[]; sma: SekolahNilai[] } } = {}

      sekolahData.forEach(sekolah => {
        const kecamatan = getKecamatanFromNpsn(String(sekolah.npsn))
        if (!kecamatan) return

        const sekolahId = String(sekolah.sekolah_id)
        const prestasi = getLowestScore(prestasiMap.get(sekolahId))
        const nonPrestasi = getLowestScore(nonPrestasiMap.get(sekolahId))
        const terbaikValues = [prestasi.value, nonPrestasi.value].filter((value): value is number => value !== null)

        if (!kecamatanMap[kecamatan]) kecamatanMap[kecamatan] = { smp: [], sma: [] }

        kecamatanMap[kecamatan].smp.push({
          nama: formatSchoolName(sekolah.nama),
          npsn: String(sekolah.npsn || 'N/A'),
          prestasi: prestasi.label,
          prestasiValue: prestasi.value,
          nonPrestasi: nonPrestasi.label,
          nonPrestasiValue: nonPrestasi.value,
          terbaikValue: terbaikValues.length ? Math.min(...terbaikValues) : null
        })
      })

      smaSekolahData.forEach(sekolah => {
        const kecamatan = getSmaKecamatanFromNpsn(String(sekolah.npsn))
        if (!kecamatan) return

        const sekolahId = String(sekolah.sekolah_id)
        const prestasi = getLowestScore(smaPrestasiMap.get(sekolahId))
        const nonPrestasi = getLowestScore(smaNonPrestasiMap.get(sekolahId))
        const terbaikValues = [prestasi.value, nonPrestasi.value].filter((value): value is number => value !== null)

        if (!kecamatanMap[kecamatan]) kecamatanMap[kecamatan] = { smp: [], sma: [] }

        kecamatanMap[kecamatan].sma.push({
          nama: formatSchoolName(sekolah.nama),
          npsn: String(sekolah.npsn || 'N/A'),
          prestasi: prestasi.label,
          prestasiValue: prestasi.value,
          nonPrestasi: nonPrestasi.label,
          nonPrestasiValue: nonPrestasi.value,
          terbaikValue: terbaikValues.length ? Math.min(...terbaikValues) : null
        })
      })

      const stats: KecamatanStats = {}
      ;['Cilincing', 'Koja', 'Kelapa Gading'].forEach(kecamatan => {
        stats[kecamatan] = {
          smp: (kecamatanMap[kecamatan]?.smp || []).sort((a, b) => {
            if (a.terbaikValue === null && b.terbaikValue === null) return a.nama.localeCompare(b.nama)
            if (a.terbaikValue === null) return 1
            if (b.terbaikValue === null) return -1
            return a.terbaikValue - b.terbaikValue
          }),
          sma: (kecamatanMap[kecamatan]?.sma || []).sort((a, b) => {
            if (a.terbaikValue === null && b.terbaikValue === null) return a.nama.localeCompare(b.nama)
            if (a.terbaikValue === null) return 1
            if (b.terbaikValue === null) return -1
            return a.terbaikValue - b.terbaikValue
          })
        }
      })

      setKecamatanStats(stats)
      setLastUpdate(new Date())
      setCountdown(60)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Terjadi kesalahan')
      console.error('Error fetching SPMB SMP data:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const initialFetch = setTimeout(() => {
      fetchData()
    }, 0)

    const interval = setInterval(fetchData, 60 * 1000)
    return () => {
      clearTimeout(initialFetch)
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
      router.replace('/live-spmb-sd?mix=1')
    }, MIX_DURATION)

    return () => {
      window.clearInterval(interval)
      window.clearTimeout(timeout)
    }
  }, [mixEnabled, router])

  const mixProgressPercent = mixEnabled ? Math.min(100, (mixElapsed / MIX_DURATION) * 100) : 0

  return (
    <main className="min-h-screen bg-gradient-to-br from-emerald-50 via-white to-cyan-50 relative">
      {mixEnabled && (
        <div className="fixed top-0 left-0 right-0 z-50 h-1 bg-emerald-100">
          <div
            className="h-full bg-gradient-to-r from-emerald-500 via-cyan-500 to-orange-500 transition-[width] duration-1000 ease-linear"
            style={{ width: `${mixProgressPercent}%` }}
          />
        </div>
      )}

      <Link
        href="/evaluasi-spmb"
        title="Evaluasi pelayanan SPMB"
        className="fixed bottom-5 left-5 z-50 inline-flex h-11 items-center gap-2 rounded-full border border-emerald-200/70 bg-white/90 px-4 text-sm font-extrabold text-slate-800 shadow-lg backdrop-blur-sm transition-all duration-200 hover:scale-105 hover:bg-white hover:shadow-xl"
      >
        <svg className="h-5 w-5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6M7 4h10a2 2 0 012 2v14l-3-2-3 2-3-2-3 2V6a2 2 0 012-2z" />
        </svg>
        Evaluasi
      </Link>

      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-[400px] h-[400px] bg-gradient-to-br from-emerald-200/30 to-cyan-300/20 rounded-full blur-3xl animate-float" />
        <div className="absolute bottom-0 right-1/4 w-[350px] h-[350px] bg-gradient-to-br from-cyan-200/25 to-sky-300/15 rounded-full blur-3xl animate-float-delayed" />
        <div
          className="absolute inset-0 opacity-[0.025]"
          style={{
            backgroundImage: 'radial-gradient(circle, #059669 1px, transparent 1px)',
            backgroundSize: '20px 20px'
          }}
        />
      </div>

      {/* Fullscreen Toggle Button */}
      <button
        onClick={toggleFullscreen}
        title={isFullscreen ? 'Keluar Fullscreen' : 'Fullscreen'}
        className="fixed bottom-5 right-5 z-50 w-10 h-10 flex items-center justify-center rounded-full bg-white/80 backdrop-blur-sm border border-emerald-200/60 shadow-lg hover:shadow-xl hover:bg-white hover:scale-110 transition-all duration-200"
      >
        {isFullscreen ? (
          // Compress icon
          <svg className="w-4 h-4 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
              d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M15 9h4.5M15 9V4.5M15 9l5.25-5.25M9 15H4.5M9 15v4.5M9 15l-5.25 5.25M15 15h4.5M15 15v4.5M15 15l5.25 5.25" />
          </svg>
        ) : (
          // Expand icon
          <svg className="w-4 h-4 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
              d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
          </svg>
        )}
      </button>

      <div className={`relative z-10 px-4 sm:px-6 py-6 transition-all duration-500 ${isLoaded ? 'opacity-100' : 'opacity-0'}`}>
        <div className="max-w-6xl mx-auto">
          <div className="relative flex flex-col lg:block items-center mb-8 gap-4 lg:min-h-[56px]">
            <div className="flex justify-start lg:absolute lg:left-0 lg:top-1/2 lg:-translate-y-1/2">
              <Link href="/live-spmb" className="inline-flex items-center gap-2 hover:opacity-70 transition-opacity">
                <svg className="w-5 h-5 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
                <span className="text-sm font-semibold text-slate-600">Kembali</span>
              </Link>
            </div>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-2 sm:gap-3 text-center sm:text-left">
              <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900 whitespace-nowrap">
                Live SPMB{' '}
                <span className="bg-gradient-to-r from-emerald-600 to-cyan-600 bg-clip-text text-transparent">
                  SMP SMA 2026
                </span>
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 leading-tight whitespace-nowrap">
                <span className="block">Nilai terendah</span>
                <span className="block">akademik, non akademik &amp; MPM</span>
              </p>
            </div>

            <div className="flex items-center justify-center lg:justify-end gap-2 lg:absolute lg:right-0 lg:top-1/2 lg:-translate-y-1/2">
              <div className="flex items-center gap-2 px-3 py-1.5 bg-white/80 rounded-full border border-emerald-200/50 shadow-sm">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-xs font-semibold text-emerald-700 whitespace-nowrap">Live</span>
              </div>
              <button
                onClick={() => { fetchData(); setCountdown(60) }}
                disabled={loading}
                title="Refresh sekarang"
                className="relative inline-flex items-center gap-2 px-3 py-1.5 bg-white/80 rounded-full border border-emerald-200/50 shadow-sm hover:bg-white transition-colors disabled:opacity-50 shrink-0"
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

          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-700 font-semibold">Error: {error}</p>
            </div>
          )}

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
                      <div key={j} className="h-16 bg-slate-100 rounded" />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {!loading && (
            <div className="flex flex-col gap-6">
              {/* Row 1: Header kecamatan + SMP */}
              <div className="grid md:grid-cols-3 gap-6">
                {Object.entries(kecamatanStats).map(([kecamatan, data], idx) => (
                  <div
                    key={`smp-${kecamatan}`}
                    className={`bg-white/60 backdrop-blur-sm rounded-xl p-6 border border-white/50 shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300 flex flex-col ${
                      isLoaded ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
                    }`}
                    style={{ transitionDelay: isLoaded ? `${300 + idx * 100}ms` : undefined }}
                  >
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                      <h3 className="text-lg font-bold text-slate-900 truncate">{kecamatan}</h3>
                    </div>
                    <div className="flex-1 flex flex-col rounded-xl border border-emerald-200/60 bg-gradient-to-br from-emerald-50/80 to-cyan-50/60 overflow-hidden">
                      <div className="flex-1 p-2">
                        <AutoScrollList isScrollable={data.smp.length > 9} maxHeight="248px">
                          {data.smp.length > 0 ? (
                            data.smp.map((sekolah, i) => (
                              <div
                                key={`smp-${sekolah.npsn}-${i}`}
                                className="px-2 py-0.5 bg-white/70 rounded-lg border border-emerald-100/60 hover:border-emerald-300 transition-colors flex items-center justify-between gap-2"
                              >
                                <p className="text-sm font-semibold text-slate-900 truncate flex-1 min-w-0">{sekolah.nama}</p>
                                <div className="flex items-center gap-1.5 shrink-0">
                                  <div className="rounded-md bg-white/75 border border-emerald-100 px-1.5 py-0.5 min-w-[74px] flex items-center justify-center gap-1">
                                    <span className="text-[15px] font-extrabold text-emerald-700 leading-none">{sekolah.prestasi}</span>
                                    <span className="text-[7px] font-semibold text-slate-500 uppercase leading-[0.55rem]">AKADE<br />MIK</span>
                                  </div>
                                  <div className="rounded-md bg-white/75 border border-cyan-100 px-1.5 py-0.5 min-w-[74px] flex items-center justify-center gap-1">
                                    <span className="text-[15px] font-extrabold text-cyan-700 leading-none">{sekolah.nonPrestasi}</span>
                                    <span className="text-[7px] font-semibold text-slate-500 uppercase leading-[0.55rem]">NON<br />AKAD</span>
                                  </div>
                                </div>
                              </div>
                            ))
                          ) : (
                            <p className="text-xs text-slate-500 italic">Tidak ada data</p>
                          )}
                        </AutoScrollList>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Row 2: SMA — top otomatis sejajar karena satu grid row */}
              <div className="grid md:grid-cols-3 gap-6 items-start">
                {Object.entries(kecamatanStats).map(([kecamatan, data], idx) => (
                  <div
                    key={`sma-${kecamatan}`}
                    className={`bg-white/60 backdrop-blur-sm rounded-xl p-6 border border-white/50 shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300 ${
                      isLoaded ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
                    }`}
                    style={{ transitionDelay: isLoaded ? `${500 + idx * 100}ms` : undefined }}
                  >
                    <div className="rounded-xl border border-violet-200/60 bg-gradient-to-br from-violet-50/80 to-sky-50/60 overflow-hidden">
                      <div className="p-2">
                        <AutoScrollList isScrollable={data.sma.length > 4} maxHeight="148px">
                          {data.sma.length > 0 ? (
                            data.sma.map((sekolah, i) => (
                              <div
                                key={`sma-${sekolah.npsn}-${i}`}
                                className="px-2 py-0.5 bg-white/70 rounded-lg border border-violet-100/60 hover:border-violet-300 transition-colors flex items-center justify-between gap-2"
                              >
                                <p className="text-sm font-semibold text-slate-900 truncate flex-1 min-w-0">{sekolah.nama}</p>
                                <div className="flex items-center gap-1.5 shrink-0">
                                  <div className="rounded-md bg-white/75 border border-violet-100 px-1.5 py-0.5 min-w-[74px] flex items-center justify-center gap-1">
                                    <span className="text-[15px] font-extrabold text-violet-700 leading-none">{sekolah.prestasi}</span>
                                    <span className="text-[7px] font-semibold text-slate-500 uppercase leading-[0.55rem]">AKADE<br />MIK</span>
                                  </div>
                                  <div className="rounded-md bg-white/75 border border-sky-100 px-1.5 py-0.5 min-w-[74px] flex items-center justify-center gap-1">
                                    <span className="text-[15px] font-extrabold text-sky-700 leading-none">{sekolah.nonPrestasi}</span>
                                    <span className="text-[7px] font-semibold text-slate-500 uppercase leading-[0.55rem]">MPM<br />AKAD</span>
                                  </div>
                                </div>
                              </div>
                            ))
                          ) : (
                            <p className="text-xs text-slate-500 italic">Tidak ada data</p>
                          )}
                        </AutoScrollList>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
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
