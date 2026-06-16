'use client'

import Link from 'next/link'
import { FormEvent, useEffect, useRef, useState } from 'react'

type Indikator = 'baik' | 'sedang' | 'buruk'
interface EvaluasiEntry {
  id: string | number
  pelayanan: string
  nomorMeja: string
  indikator: Indikator
  catatan: string
  createdAt: string
}

interface EvaluationSummary {
  today: number
  total: number
  date: string
}

interface QueueCounter {
  id: string | number
  serviceDate: string
  currentNumber: number
  updatedAt: string
}

const defaultPelayananOptions = [
  'Verifikasi Berkas',
  'Bantuan Akun',
  'Perubahan Data',
  'Pengaduan',
  'Lainnya'
]

const mejaOptions = Array.from({ length: 12 }, (_, index) => String(index + 1))

const LIVE_SUMMARY_REFRESH_MS = 60 * 1000
const QUEUE_REFRESH_MS = 10 * 1000

const kecamatanOrder = ['Cilincing', 'Koja', 'Kelapa Gading'] as const

type KecName = typeof kecamatanOrder[number]

interface SPMBSchool {
  nama: string
  npsn: string
  usiaTermuda: string
}

interface SPMBGroup {
  kecamatan: KecName
  sd: SPMBSchool[]
  smpSma: SPMBSmpSmaSchool[]
}

interface SPMBSmpSmaSchool extends SPMBSchool {
  jenjang: 'SMP' | 'SMA'
  nilaiAkademik: string
  nilaiNonAkademik: string
  labelNonAkademik: 'NON'
}

interface LiveSpmbSdResponse {
  sekolah?: Array<{
    sekolah_id?: string | number
    npsn?: string | number
    nama?: string
  }>
  statistik?: Record<string, { rekap?: unknown }> | { data?: Record<string, { rekap?: unknown }> }
  error?: string
}

interface LiveSpmbSmpResponse {
  smpSekolah?: Array<{
    sekolah_id?: string | number
    npsn?: string | number
    nama?: string
  }>
  smpAkademik?: { data?: Record<string, { rekap?: unknown }> }
  smpNonAkademik?: { data?: Record<string, { rekap?: unknown }> }
  smaSekolah?: Array<{
    sekolah_id?: string | number
    npsn?: string | number
    nama?: string
  }>
  smaAkademik?: { data?: Record<string, { rekap?: unknown }> }
  smaMpmAkademik?: { data?: Record<string, { rekap?: unknown }> }
  error?: string
}

const KECAMATAN_NPSN_MAP: Record<KecName, readonly string[]> = {
  Cilincing: [
    '20105076', '20101028', '20104847', '70009509', '20104844', '20104845', '20101026', '20104846', '20101010', '20104871',
    '20105011', '20101093', '20105075', '20105066', '20101003', '20104991', '20104848', '20101001', '20100997', '20101005',
    '20104983', '20105014', '20105017', '20105083', '69857156', '20104982', '20104873', '20110224', '20109372', '20104872',
    '69980873', '20104995', '20105027', '20104840', '20109315', '20100677', '20100679', '20104907', '20109047', '20104839',
    '20105045', '20100633', '20100682', '20100684', '20100686', '20100582', '20100584', '20100586', '20104911', '20104975',
    '20105025', '20105034', '20109083', '20105105', '20105118', '20105137', '20105047', '20105044', '20109629', '69984785',
    '20104914', '20100591', '20104915', '69952902', '69922219', '20104912', '69913134', '20105031', '20105071', '20105072',
    '20105106', '20100596', '20104984', '20104994', '20100593', '20104916', '20104917', '70010608', '20109937', '20105058'
  ],
  Koja: [
    '20105110', '20105003', '20105087', '20105112', '20105134', '20100884', '20105064', '20101061', '20104985', '20104869',
    '20101054', '20101057', '20101059', '20101062', '20105054', '20109343', '20105133', '69949704', '20100647', '20100648',
    '20100690', '20100691', '20105113', '20109525', '69988491', '20100645', '20100669', '20105131', '20104974', '20100699',
    '20100702', '20100693', '20100695', '20100697', '20100689', '20100671', '20100673', '20104906', '20104976', '20105001',
    '69912051', '20109251', '20105073', '20100568', '20100565', '69963071', '20104954', '20104956', '20100577', '20105108',
    '20104952', '20104958', '20100575', '20100598', '20100618', '20100619', '20104963', '20100622', '20100624', '20100625',
    '20105128', '20105129'
  ],
  'Kelapa Gading': [
    '69883487', '20109039', '69889102', '69856890', '20105033', '69892595', '69830128', '20104861', '20109346', '20104992',
    '20109172', '20109521', '20109312', '20109938', '20104863', '20104865', '20105120', '20105122', '69857086', '69888567',
    '20109384', '20105060', '20104886', '69938151', '20109528', '69879019', '20109397', '20105124', '20105125', '69964730',
    '20104978', '20104880', '20104882', '20104884', '20104885', '20104977', '20105024', '20105101', '20121012', '20105043'
  ]
}

const SMP_KECAMATAN_NPSN_MAP: Record<KecName, readonly string[]> = {
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

const SMA_KECAMATAN_NPSN_MAP: Record<KecName, readonly string[]> = {
  Cilincing: ['20100804', '20100805', '20100797', '20100795', '20100779', '20100781', '20100782', '70011683'],
  Koja: ['20100802', '20100806', '20107368', '20107369', '20100614', '20107385', '20107395', '20100801'],
  'Kelapa Gading': ['20100812', '20100796', '69977407', '20100600', '69968321', '69975652', '20100601', '20100604', '69889105', '69856892', '20177804', '69939320', '69879021', '20100616', '20109180', '20100608', '20107390', '20100799', '20100632', '20100778']
}

const getKecamatanFromMap = (npsn: string, map: Record<KecName, readonly string[]>): KecName | null => {
  const normalized = String(npsn || '')
  for (const kecamatan of kecamatanOrder) {
    if (map[kecamatan].includes(normalized)) {
      return kecamatan
    }
  }
  return null
}

const getKecamatanFromNpsn = (npsn: string): KecName | null => getKecamatanFromMap(npsn, KECAMATAN_NPSN_MAP)

const getSmpKecamatanFromNpsn = (npsn: string): KecName | null => getKecamatanFromMap(npsn, SMP_KECAMATAN_NPSN_MAP)

const getSmaKecamatanFromNpsn = (npsn: string): KecName | null => getKecamatanFromMap(npsn, SMA_KECAMATAN_NPSN_MAP)

const AutoScrollList = ({
  children,
  isScrollable,
  isPaused
}: {
  children: React.ReactNode
  isScrollable: boolean
  isPaused?: boolean
}) => {
  const containerRef = useRef<HTMLDivElement>(null)
  const isUserScrollingRef = useRef(false)
  const userScrollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const holdAutoScrollForManualScroll = () => {
    isUserScrollingRef.current = true
    if (userScrollTimeoutRef.current) {
      clearTimeout(userScrollTimeoutRef.current)
    }
    userScrollTimeoutRef.current = setTimeout(() => {
      isUserScrollingRef.current = false
    }, 2500)
  }

  useEffect(() => {
    if (!isScrollable || isPaused) return

    let animationFrameId: number
    let timeoutId: ReturnType<typeof setTimeout>
    let direction = 1
    let isEdgePaused = true

    const startScrolling = () => {
      if (!containerRef.current) return
      const el = containerRef.current
      const maxScroll = el.scrollHeight - el.clientHeight

      if (!isEdgePaused && !isUserScrollingRef.current) {
        el.scrollTop += 0.5 * direction

        if (direction === 1 && Math.ceil(el.scrollTop) >= maxScroll) {
          isEdgePaused = true
          direction = -1
          el.scrollTop = maxScroll
          timeoutId = setTimeout(() => {
            isEdgePaused = false
            animationFrameId = requestAnimationFrame(startScrolling)
          }, 2000)
          return
        }

        if (direction === -1 && el.scrollTop <= 0) {
          isEdgePaused = true
          direction = 1
          el.scrollTop = 0
          timeoutId = setTimeout(() => {
            isEdgePaused = false
            animationFrameId = requestAnimationFrame(startScrolling)
          }, 2000)
          return
        }
      }

      animationFrameId = requestAnimationFrame(startScrolling)
    }

    timeoutId = setTimeout(() => {
      isEdgePaused = false
      animationFrameId = requestAnimationFrame(startScrolling)
    }, 2000)

    return () => {
      cancelAnimationFrame(animationFrameId)
      clearTimeout(timeoutId)
      if (userScrollTimeoutRef.current) {
        clearTimeout(userScrollTimeoutRef.current)
      }
    }
  }, [isScrollable, isPaused])

  return (
    <div
      ref={containerRef}
      onWheel={holdAutoScrollForManualScroll}
      onTouchStart={holdAutoScrollForManualScroll}
      onPointerDown={holdAutoScrollForManualScroll}
      className={`min-h-0 flex-1 ${isScrollable ? 'overflow-y-auto overscroll-contain pr-1 touch-pan-y' : ''}`}
    >
      {children}
    </div>
  )
}

const readJsonResponse = async (response: Response) => {
  const text = await response.text()
  if (!text) return {}

  try {
    return JSON.parse(text)
  } catch {
    throw new Error('API evaluasi belum mengembalikan JSON. Cek DASHBOARD_BASE_URL dan pastikan dashboard sudah direstart.')
  }
}

const getJakartaDateKey = (value: Date | string) => {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Jakarta',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).format(date)
}

const countTodayEntries = (rows: EvaluasiEntry[]) => {
  const todayKey = getJakartaDateKey(new Date())
  return rows.filter(entry => getJakartaDateKey(entry.createdAt) === todayKey).length
}

const indikatorOptions: Array<{
  value: Indikator
  label: string
  emoji: string
  description: string
  className: string
}> = [
  {
    value: 'baik',
    label: 'Baik',
    emoji: '😀',
    description: 'Pelayanan cepat, jelas, dan membantu.',
    className: 'border-emerald-300 bg-emerald-100 text-emerald-950 peer-checked:border-emerald-700 peer-checked:bg-emerald-600 peer-checked:text-white peer-checked:ring-4 peer-checked:ring-emerald-200'
  },
  {
    value: 'sedang',
    label: 'Sedang',
    emoji: '😐',
    description: 'Pelayanan cukup, masih perlu diperbaiki.',
    className: 'border-amber-300 bg-amber-100 text-amber-950 peer-checked:border-amber-700 peer-checked:bg-amber-500 peer-checked:text-slate-950 peer-checked:ring-4 peer-checked:ring-amber-200'
  },
  {
    value: 'buruk',
    label: 'Buruk',
    emoji: '😟',
    description: 'Pelayanan belum sesuai harapan.',
    className: 'border-rose-300 bg-rose-100 text-rose-950 peer-checked:border-rose-700 peer-checked:bg-rose-600 peer-checked:text-white peer-checked:ring-4 peer-checked:ring-rose-200'
  }
]

export default function EvaluasiSPMB() {
  const [pelayanan, setPelayanan] = useState(defaultPelayananOptions[0])
  const [nomorMeja, setNomorMeja] = useState('')
  const [indikator, setIndikator] = useState<Indikator | ''>('')
  const [catatan, setCatatan] = useState('')
  const [entries, setEntries] = useState<EvaluasiEntry[]>([])
  const [evaluationSummary, setEvaluationSummary] = useState<EvaluationSummary>({
    today: 0,
    total: 0,
    date: ''
  })
  const [spmbSummary, setSpmbSummary] = useState<SPMBGroup[]>([])
  const [summaryPausedByKecamatan, setSummaryPausedByKecamatan] = useState<Record<KecName, boolean>>({
    Koja: false,
    Cilincing: false,
    'Kelapa Gading': false
  })
  const [savedMessage, setSavedMessage] = useState('')
  const [messageTone, setMessageTone] = useState<'success' | 'error'>('success')
  const [isSaving, setIsSaving] = useState(false)
  const [isSubmitted, setIsSubmitted] = useState(false)
  const [isHistoryLoading, setIsHistoryLoading] = useState(true)
  const [queueCounter, setQueueCounter] = useState<QueueCounter | null>(null)
  const [isQueueLoading, setIsQueueLoading] = useState(true)
  const [isQueueUpdating, setIsQueueUpdating] = useState(false)
  const stopSpmbSummaryFetchRef = useRef(false)

  const loadEntries = async () => {
    setIsHistoryLoading(true)
    try {
      const response = await fetch('/api/spmb-evaluations', { cache: 'no-store' })
      const payload = await readJsonResponse(response)
      const rows = Array.isArray(payload?.data) ? payload.data : []
      if (!response.ok) {
        throw new Error(payload?.error || payload?.message || 'Gagal memuat riwayat evaluasi.')
      }
      setEntries(rows)
      const summary = payload?.summary || {}
      const todayCount = Number(summary?.today)
      const totalCount = Number(summary?.total)
      const fallbackTodayCount = countTodayEntries(rows)
      setEvaluationSummary({
        today: Number.isFinite(todayCount) ? todayCount : fallbackTodayCount,
        total: Number.isFinite(totalCount) ? totalCount : rows.length,
        date: typeof summary?.date === 'string' ? summary.date : ''
      })
    } catch (error) {
      setMessageTone('error')
      setSavedMessage(error instanceof Error ? error.message : 'Gagal memuat riwayat evaluasi.')
    } finally {
      setIsHistoryLoading(false)
    }
  }

  const loadQueueCounter = async (silent = false) => {
    if (!silent) setIsQueueLoading(true)
    try {
      const response = await fetch('/api/spmb-queue', { cache: 'no-store' })
      const payload = await readJsonResponse(response)
      if (!response.ok || !payload?.success) {
        throw new Error(payload?.message || 'Gagal memuat nomor antrian.')
      }
      setQueueCounter(payload.item as QueueCounter)
    } catch (error) {
      if (!silent) {
        setMessageTone('error')
        setSavedMessage(error instanceof Error ? error.message : 'Gagal memuat nomor antrian.')
      }
    } finally {
      if (!silent) setIsQueueLoading(false)
    }
  }

  const updateQueueCounter = async (action: 'increment' | 'decrement') => {
    if (isQueueUpdating) return

    setIsQueueUpdating(true)
    try {
      const response = await fetch('/api/spmb-queue', {
        method: 'POST',
        headers: {
          'content-type': 'application/json'
        },
        body: JSON.stringify({ action })
      })
      const payload = await readJsonResponse(response)
      if (!response.ok || !payload?.success) {
        throw new Error(payload?.message || 'Gagal memperbarui nomor antrian.')
      }
      setQueueCounter(payload.item as QueueCounter)
    } catch (error) {
      setMessageTone('error')
      setSavedMessage(error instanceof Error ? error.message : 'Gagal memperbarui nomor antrian.')
    } finally {
      setIsQueueUpdating(false)
    }
  }

  const loadSpmbSummary = async () => {
    if (stopSpmbSummaryFetchRef.current) return

    try {
      const [sdResponse, smpResponse] = await Promise.all([
        fetch('/api/live-spmb-sd', { cache: 'no-store' }),
        fetch('/api/live-spmb-smp', { cache: 'no-store' })
      ])

      const [sdPayload, smpPayload] = await Promise.all([
        sdResponse.json().catch(() => ({})),
        smpResponse.json().catch(() => ({}))
      ]) as [LiveSpmbSdResponse, LiveSpmbSmpResponse]

      const sdOk = sdResponse.ok && !sdPayload?.error
      const smpOk = smpResponse.ok && !smpPayload?.error

      const sekolahData = sdOk && Array.isArray(sdPayload?.sekolah) ? sdPayload.sekolah : []
      const statistikResponse = sdPayload?.statistik || {}
      const statistikEntries = Object.entries(
        'data' in statistikResponse ? statistikResponse.data || {} : statistikResponse
      ) as Array<[string, { rekap?: unknown }]>
      const statistikMap = new Map<string, { rekap?: unknown }>(statistikEntries)

      const smpSekolahData = smpOk && Array.isArray(smpPayload?.smpSekolah) ? smpPayload.smpSekolah : []
      const smaSekolahData = smpOk && Array.isArray(smpPayload?.smaSekolah) ? smpPayload.smaSekolah : []
      const smpPrestasiMap = new Map<string, { rekap?: unknown }>(Object.entries(smpPayload?.smpAkademik?.data || {}))
      const smpNonPrestasiMap = new Map<string, { rekap?: unknown }>(Object.entries(smpPayload?.smpNonAkademik?.data || {}))
      const smaPrestasiMap = new Map<string, { rekap?: unknown }>(Object.entries(smpPayload?.smaAkademik?.data || {}))
      const smaNonPrestasiMap = new Map<string, { rekap?: unknown }>(Object.entries(smpPayload?.smaMpmAkademik?.data || {}))

      const extractUsiaTermuda = (rekap: unknown): string => {
        if (!rekap) return 'N/A'

        const parseStr = (str: string) => {
          let text = str.trim()
          if (!text) return 'N/A'
          text = text.replace(/\s*th/gi, 'T').replace(/\s*bl/gi, 'B').replace(/\s*hr/gi, 'H')
          return text
        }

        if (Array.isArray(rekap) && rekap.length > 0) {
          const ageArray = rekap[0]
          if (Array.isArray(ageArray) && ageArray.length > 0) {
            const firstAge = ageArray[0]
            if (typeof firstAge === 'string') return parseStr(firstAge)
            if (typeof firstAge === 'number') return String(firstAge)
          }
          if (typeof ageArray === 'string') return parseStr(ageArray)
          if (typeof ageArray === 'number') return String(ageArray)
        }

        return 'N/A'
      }

      const extractLowestScore = (rekap: unknown): string => {
        if (!Array.isArray(rekap) || rekap.length === 0) return 'N/A'

        const values = rekap
          .map(item => {
            const rawValue = Array.isArray(item) ? item[0] : item
            const value = Number(rawValue)
            return Number.isFinite(value) ? value : null
          })
          .filter((value): value is number => value !== null)

        if (values.length === 0) return 'N/A'
        return Math.min(...values).toFixed(2)
      }

      const kecamatanMap: Record<KecName, { sd: SPMBSchool[]; smpSma: SPMBSmpSmaSchool[] }> = {
        Cilincing: { sd: [], smpSma: [] },
        Koja: { sd: [], smpSma: [] },
        'Kelapa Gading': { sd: [], smpSma: [] }
      }

      sekolahData.forEach(sekolah => {
        const kecamatan = getKecamatanFromNpsn(String(sekolah.npsn))
        if (!kecamatan) return

        const stat = statistikMap.get(String(sekolah.sekolah_id))
        kecamatanMap[kecamatan].sd.push({
          nama: String(sekolah.nama || 'N/A').replace(/^SDN\s+/i, ''),
          npsn: String(sekolah.npsn || 'N/A'),
          usiaTermuda: extractUsiaTermuda(stat?.rekap)
        })
      })

      smpSekolahData.forEach(sekolah => {
        const kecamatan = getSmpKecamatanFromNpsn(String(sekolah.npsn))
        if (!kecamatan) return

        const statAkademik = smpPrestasiMap.get(String(sekolah.sekolah_id))
        const statNonAkademik = smpNonPrestasiMap.get(String(sekolah.sekolah_id))
        const nilaiAkademik = extractLowestScore(statAkademik?.rekap)
        const nilaiNonAkademik = extractLowestScore(statNonAkademik?.rekap)
        kecamatanMap[kecamatan].smpSma.push({
          nama: String(sekolah.nama || 'N/A').replace(/^SMP\s+NEGERI\s+/i, 'SMPN ').replace(/^SMP\s+/i, 'SMP '),
          npsn: String(sekolah.npsn || 'N/A'),
          usiaTermuda: nilaiAkademik !== 'N/A' ? nilaiAkademik : nilaiNonAkademik,
          jenjang: 'SMP',
          nilaiAkademik,
          nilaiNonAkademik,
          labelNonAkademik: 'NON'
        })
      })

      smaSekolahData.forEach(sekolah => {
        const kecamatan = getSmaKecamatanFromNpsn(String(sekolah.npsn))
        if (!kecamatan) return

        const statAkademik = smaPrestasiMap.get(String(sekolah.sekolah_id))
        const statNonAkademik = smaNonPrestasiMap.get(String(sekolah.sekolah_id))
        const nilaiAkademik = extractLowestScore(statAkademik?.rekap)
        const nilaiNonAkademik = extractLowestScore(statNonAkademik?.rekap)
        kecamatanMap[kecamatan].smpSma.push({
          nama: String(sekolah.nama || 'N/A').replace(/^SMA\s+NEGERI\s+/i, 'SMAN ').replace(/^SMA\s+/i, 'SMA '),
          npsn: String(sekolah.npsn || 'N/A'),
          usiaTermuda: nilaiAkademik !== 'N/A' ? nilaiAkademik : nilaiNonAkademik,
          jenjang: 'SMA',
          nilaiAkademik,
          nilaiNonAkademik,
          labelNonAkademik: 'NON'
        })
      })

      setSpmbSummary(kecamatanOrder.map(kecamatan => ({
        kecamatan,
        sd: kecamatanMap[kecamatan].sd.sort((a, b) => a.nama.localeCompare(b.nama)),
        smpSma: kecamatanMap[kecamatan].smpSma.sort((a, b) => {
          if (a.jenjang !== b.jenjang) return a.jenjang === 'SMP' ? -1 : 1
          return a.nama.localeCompare(b.nama)
        })
      })))
      if (!sdOk && !smpOk) {
        throw new Error('Gagal memuat ringkasan live SPMB.')
      }
    } catch {
      stopSpmbSummaryFetchRef.current = true
      setSpmbSummary([])
    }
  }

  useEffect(() => {
    let cancelled = false

    fetch('/api/spmb-service-types', { cache: 'no-store' })
      .then(response => response.ok ? readJsonResponse(response) : null)
      .then(payload => {
        if (cancelled) return
        const nextOptions = Array.isArray(payload?.data)
          ? payload.data
              .map((item: { name?: unknown }) => String(item.name || '').trim())
              .filter(Boolean)
          : []
        if (nextOptions.length === 0) return
        setPelayanan(current => nextOptions.includes(current) ? current : nextOptions[0])
      })
      .catch(() => undefined)

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(loadEntries, 0)
    const queueTimer = window.setTimeout(loadQueueCounter, 0)
    const queueInterval = window.setInterval(() => loadQueueCounter(true), QUEUE_REFRESH_MS)
    const summaryTimer = window.setTimeout(loadSpmbSummary, 0)
    const summaryInterval = window.setInterval(loadSpmbSummary, LIVE_SUMMARY_REFRESH_MS)

    const refreshSummaryOnVisible = () => {
      if (document.visibilityState === 'visible') {
        loadQueueCounter(true)
        loadSpmbSummary()
      }
    }

    document.addEventListener('visibilitychange', refreshSummaryOnVisible)

    return () => {
      window.clearTimeout(timer)
      window.clearTimeout(queueTimer)
      window.clearInterval(queueInterval)
      window.clearTimeout(summaryTimer)
      window.clearInterval(summaryInterval)
      document.removeEventListener('visibilitychange', refreshSummaryOnVisible)
    }
  }, [])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (isSaving || isSubmitted || !nomorMeja || !indikator) return

    setIsSaving(true)
    try {
      const response = await fetch('/api/spmb-evaluations', {
        method: 'POST',
        headers: {
          'content-type': 'application/json'
        },
        body: JSON.stringify({
          pelayanan,
          nomorMeja,
          indikator,
          catatan: catatan.trim()
        })
      })
      const payload = await readJsonResponse(response)
      if (!response.ok || !payload?.success) {
        throw new Error(payload?.message || 'Gagal menyimpan evaluasi.')
      }

      const savedEntry = payload.item as EvaluasiEntry
      setEntries(prev => [savedEntry, ...prev].slice(0, 100))
      setEvaluationSummary(prev => ({
        ...prev,
        today: prev.today + 1,
        total: prev.total + 1
      }))
      setNomorMeja('')
      setIndikator('')
      setCatatan('')
      setIsSubmitted(true)
      setMessageTone('success')
      setSavedMessage('Berhasil disimpan.')
    } catch (error) {
      setMessageTone('error')
      setSavedMessage(error instanceof Error ? error.message : 'Gagal menyimpan evaluasi.')
    } finally {
      setIsSaving(false)
    }
  }

  const resetForm = () => {
    setNomorMeja('')
    setIndikator('')
    setCatatan('')
    setSavedMessage('')
    setMessageTone('success')
    setIsSubmitted(false)
  }

  const isSubmitDisabled = isSaving || isSubmitted || !nomorMeja || !indikator
  const hasSpmbSummaryData = spmbSummary.some(item => item.sd.length > 0 || item.smpSma.length > 0)

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900 lg:h-screen lg:overflow-hidden">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-3 py-3 sm:px-5 lg:h-screen lg:min-h-0">
        <header className="mb-3">
          <h1 className="sr-only">Evaluasi Pelayanan SPMB</h1>
        </header>

        <div className={`grid min-h-0 flex-1 gap-3 lg:items-stretch ${hasSpmbSummaryData ? 'lg:grid-cols-[5fr_3fr_3fr]' : 'lg:grid-cols-[5fr_3fr]'}`}>
          <form onSubmit={handleSubmit} className="flex min-h-0 flex-col rounded-lg border border-slate-200 bg-white p-4 shadow-sm lg:h-full">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2">
                <Link
                  href="/live-spmb"
                  aria-label="Kembali"
                  title="Kembali"
                  className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:bg-slate-50 hover:text-slate-900"
                >
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                  </svg>
                </Link>
                <div className="flex min-w-0 items-center gap-2">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white">
                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6M7 4h10a2 2 0 012 2v14l-3-2-3 2-3-2-3 2V6a2 2 0 012-2z" />
                    </svg>
                  </span>
                  <div className="min-w-0">
                    <h2 className="truncate text-base font-extrabold">Input Evaluasi</h2>
                    <p className="truncate text-xs font-semibold text-slate-500">Isi data pelayanan dan indikator.</p>
                  </div>
                </div>
              </div>
              <button
                type="submit"
                disabled={isSubmitDisabled}
                className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-extrabold text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                </svg>
                {isSaving ? 'Menyimpan' : isSubmitted ? 'Tersimpan' : 'Simpan'}
              </button>
            </div>

            {savedMessage && (
              <div
                className={`mb-3 rounded-lg border px-3 py-2 text-sm font-bold ${
                  messageTone === 'success'
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                    : 'border-rose-200 bg-rose-50 text-rose-800'
                }`}
                role="status"
              >
                {savedMessage}
                {isSubmitted && (
                  <button
                    type="button"
                    onClick={resetForm}
                    className="ms-3 rounded-md border border-emerald-300 bg-white px-2 py-1 text-xs font-extrabold text-emerald-900 hover:bg-emerald-100"
                  >
                    Isi Baru
                  </button>
                )}
              </div>
            )}

            <div className="grid gap-3">
              <fieldset>
                <legend className="mb-1 text-xs font-bold uppercase text-slate-500">Operator</legend>
                <div className="grid grid-cols-4 gap-2">
                  {mejaOptions.map(option => {
                    const selected = nomorMeja === option
                    return (
                      <button
                        key={option}
                        type="button"
                        disabled={isSubmitted}
                        onClick={() => setNomorMeja(option)}
                        className={`flex h-10 items-center justify-center rounded-lg border text-sm font-extrabold transition ${
                          selected
                            ? 'border-slate-900 bg-slate-900 text-white shadow-sm'
                            : 'border-slate-200 bg-white text-slate-700 hover:border-slate-400 hover:bg-slate-50'
                        } disabled:cursor-not-allowed disabled:opacity-45`}
                        aria-pressed={selected}
                      >
                        {option}
                      </button>
                    )
                  })}
                </div>
              </fieldset>

              <fieldset>
                <legend className="mb-1 text-xs font-bold uppercase text-slate-500">Indikator</legend>
                <div className="grid grid-cols-3 gap-2">
                  {indikatorOptions.map(option => (
                    <label key={option.value} className="block cursor-pointer">
                      <input
                        type="radio"
                        name="indikator"
                        value={option.value}
                        checked={indikator === option.value}
                        disabled={isSubmitted}
                        onChange={() => setIndikator(option.value)}
                        className="peer sr-only"
                      />
                      <span className={`flex h-11 items-center justify-center gap-2 rounded-lg border px-2 text-sm font-extrabold transition peer-disabled:cursor-not-allowed peer-disabled:opacity-45 ${option.className}`}>
                        <span className="text-lg leading-none" aria-hidden="true">{option.emoji}</span>
                        <span>{option.label}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>

              <div>
                <label htmlFor="catatan" className="mb-1 block text-xs font-bold uppercase text-slate-500">Catatan</label>
                <textarea
                  id="catatan"
                  value={catatan}
                  disabled={isSubmitted}
                  onChange={event => setCatatan(event.target.value)}
                  rows={3}
                  placeholder="Opsional"
                  className="w-full resize-none rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-100 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:opacity-60"
                />
              </div>
            </div>

            <div className="mt-auto pt-3">
              <button
                type="submit"
                disabled={isSubmitDisabled}
                className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-extrabold text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                </svg>
                {isSaving ? 'Menyimpan...' : isSubmitted ? 'Evaluasi Tersimpan' : 'Simpan Evaluasi'}
              </button>
            </div>
          </form>

          <section className="flex min-h-0 flex-col rounded-lg border border-slate-200 bg-white p-4 shadow-sm lg:h-full">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-extrabold">Riwayat Evaluasi</h2>
                <div className="mt-1 flex flex-wrap gap-1.5 text-[11px] font-extrabold text-slate-600">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5">Hari ini {evaluationSummary.today}</span>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5">Seluruh {evaluationSummary.total}</span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  loadEntries()
                  loadQueueCounter()
                }}
                disabled={isHistoryLoading || isQueueLoading}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {isHistoryLoading || isQueueLoading ? 'Memuat' : 'Muat ulang'}
              </button>
            </div>

            <div className="flex min-h-0 flex-1 flex-col gap-3">
              <div className="flex flex-[1] flex-col justify-center rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="flex min-h-0 items-center justify-between gap-3">
                  <p className="max-w-[110px] text-[11px] font-black uppercase leading-tight tracking-wide text-slate-500">Nomor antrian ditangani</p>
                  <div className="text-right text-9xl font-black leading-none text-slate-950">
                    {isQueueLoading && !queueCounter ? '...' : queueCounter?.currentNumber ?? 0}
                  </div>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => updateQueueCounter('decrement')}
                    disabled={isQueueUpdating || isQueueLoading || (queueCounter?.currentNumber ?? 0) <= 0}
                    className="flex h-10 items-center justify-center rounded-lg border border-slate-300 bg-white text-2xl font-black text-slate-800 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                    aria-label="Kurangi nomor antrian"
                    title="Kurangi nomor antrian"
                  >
                    -
                  </button>
                  <button
                    type="button"
                    onClick={() => updateQueueCounter('increment')}
                    disabled={isQueueUpdating || isQueueLoading}
                    className="flex h-10 items-center justify-center rounded-lg bg-slate-900 text-2xl font-black text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                    aria-label="Tambah nomor antrian"
                    title="Tambah nomor antrian"
                  >
                    +
                  </button>
                </div>
              </div>

              <div className="min-h-0 flex-[4] space-y-2 overflow-y-auto pr-1">
                {isHistoryLoading ? (
                  <div className="flex h-full min-h-[180px] items-center justify-center rounded-lg border border-dashed border-slate-300 text-center">
                    <p className="text-sm font-semibold text-slate-500">Memuat riwayat evaluasi...</p>
                  </div>
                ) : entries.length > 0 ? (
                  entries.map(entry => (
                    <article key={entry.id} className="rounded-lg border border-slate-200 px-3 py-2">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-extrabold text-slate-900">Meja {entry.nomorMeja}</span>
                          </div>
                          <p className="mt-1 text-xs font-semibold text-slate-400">
                            {new Date(entry.createdAt).toLocaleString('id-ID')}
                          </p>
                        </div>
                        <span className={`rounded-full px-3 py-1 text-xs font-extrabold ${
                          entry.indikator === 'baik'
                            ? 'bg-emerald-100 text-emerald-800'
                            : entry.indikator === 'sedang'
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-rose-100 text-rose-800'
                        }`}>
                          {entry.indikator.toUpperCase()}
                        </span>
                      </div>
                    </article>
                  ))
                ) : (
                  <div className="flex h-full min-h-[180px] items-center justify-center rounded-lg border border-dashed border-slate-300 text-center">
                    <p className="text-sm font-semibold text-slate-500">Belum ada evaluasi yang tersimpan.</p>
                  </div>
                )}
              </div>
            </div>
          </section>

          {hasSpmbSummaryData && (
          <div className="flex min-h-0 flex-col gap-2 lg:h-full">
            {spmbSummary.map(item => {
              const schools = [
                ...item.sd.map(sekolah => ({ ...sekolah, jenjang: 'SD' as const })),
                ...item.smpSma
              ]
              const isSummaryPaused = summaryPausedByKecamatan[item.kecamatan]

              if (schools.length === 0) return null

              return (
                <section key={item.kecamatan} className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-orange-100 bg-[#fff8f0] p-2.5 shadow-sm">
                  <div className="mb-1.5 flex h-6 items-center justify-between gap-2">
                    <h3 className="truncate text-xs font-extrabold uppercase text-slate-900">{item.kecamatan}</h3>
                    <button
                      type="button"
                      onClick={() => {
                        setSummaryPausedByKecamatan(prev => ({
                          ...prev,
                          [item.kecamatan]: !prev[item.kecamatan]
                        }))
                      }}
                      className="inline-flex h-6 items-center gap-1 rounded-full border border-orange-200 bg-white px-2 text-[10px] font-extrabold text-orange-700 shadow-sm transition hover:bg-orange-50"
                    >
                      <span aria-hidden="true">{isSummaryPaused ? '▶' : 'Ⅱ'}</span>
                      {isSummaryPaused ? 'Lanjut' : 'Pause'}
                    </button>
                  </div>
                  <AutoScrollList isScrollable={schools.length > 5} isPaused={isSummaryPaused}>
                    <div className="divide-y divide-orange-100 overflow-hidden rounded-xl border border-orange-100 bg-white shadow-sm">
                      {schools.map(sekolah => (
                        <div key={`${item.kecamatan}-${sekolah.jenjang}-${sekolah.npsn}`} className="flex min-h-7 items-center justify-between gap-2 px-2.5 py-1">
                          <div className="min-w-0">
                            <div className="truncate text-xs font-bold text-slate-900">{sekolah.nama}</div>
                          </div>
                          <div className="flex shrink-0 items-center gap-1.5">
                            <span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] font-black uppercase text-slate-500">
                              {sekolah.jenjang}
                            </span>
                            {sekolah.jenjang === 'SD' ? (
                              <span className="min-w-[64px] rounded bg-[#fde7c6] px-1.5 py-0.5 text-center text-[11px] font-black text-[#d94a00]">
                                {sekolah.usiaTermuda}
                              </span>
                            ) : (
                              <div className="flex items-center gap-1">
                                <span className="flex min-w-[50px] items-center justify-center gap-1 rounded bg-[#fde7c6] px-1 py-0.5 text-[#d94a00]">
                                  <span className="text-[8px] font-black text-orange-500">AK</span>
                                  <span className="text-[11px] font-black">{sekolah.nilaiAkademik}</span>
                                </span>
                                <span className="flex min-w-[54px] items-center justify-center gap-1 rounded bg-[#fff1d8] px-1 py-0.5 text-[#b45309]">
                                  <span className="text-[8px] font-black text-amber-600">{sekolah.labelNonAkademik}</span>
                                  <span className="text-[11px] font-black">{sekolah.nilaiNonAkademik}</span>
                                </span>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </AutoScrollList>
                </section>
              )
            })}
          </div>
          )}
        </div>
      </div>
    </main>
  )
}
