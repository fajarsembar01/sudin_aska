'use client'

import Link from 'next/link'
import { FormEvent, useEffect, useState } from 'react'

type Indikator = 'baik' | 'sedang' | 'buruk'

interface EvaluasiEntry {
  id: string | number
  pelayanan: string
  nomorMeja: string
  indikator: Indikator
  catatan: string
  createdAt: string
}

const defaultPelayananOptions = [
  'Informasi SPMB',
  'Verifikasi Berkas',
  'Bantuan Akun',
  'Perubahan Data',
  'Pengaduan',
  'Lainnya'
]

const mejaOptions = Array.from({ length: 12 }, (_, index) => String(index + 1))

const indikatorOptions: Array<{
  value: Indikator
  label: string
  description: string
  className: string
}> = [
  {
    value: 'baik',
    label: 'Baik',
    description: 'Pelayanan cepat, jelas, dan membantu.',
    className: 'border-emerald-200 bg-emerald-50 text-emerald-800 peer-checked:border-emerald-500 peer-checked:bg-emerald-100 peer-checked:ring-2 peer-checked:ring-emerald-200'
  },
  {
    value: 'sedang',
    label: 'Sedang',
    description: 'Pelayanan cukup, masih perlu diperbaiki.',
    className: 'border-amber-200 bg-amber-50 text-amber-800 peer-checked:border-amber-500 peer-checked:bg-amber-100 peer-checked:ring-2 peer-checked:ring-amber-200'
  },
  {
    value: 'buruk',
    label: 'Buruk',
    description: 'Pelayanan belum sesuai harapan.',
    className: 'border-rose-200 bg-rose-50 text-rose-800 peer-checked:border-rose-500 peer-checked:bg-rose-100 peer-checked:ring-2 peer-checked:ring-rose-200'
  }
]

export default function EvaluasiSPMB() {
  const [pelayanan, setPelayanan] = useState(defaultPelayananOptions[0])
  const [nomorMeja, setNomorMeja] = useState(mejaOptions[0])
  const [indikator, setIndikator] = useState<Indikator>('baik')
  const [catatan, setCatatan] = useState('')
  const [entries, setEntries] = useState<EvaluasiEntry[]>([])
  const [savedMessage, setSavedMessage] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [isHistoryLoading, setIsHistoryLoading] = useState(true)

  const loadEntries = async () => {
    setIsHistoryLoading(true)
    try {
      const response = await fetch('/api/spmb-evaluations', { cache: 'no-store' })
      const payload = await response.json()
      const rows = Array.isArray(payload?.data) ? payload.data : []
      setEntries(rows)
    } catch {
      setSavedMessage('Gagal memuat riwayat evaluasi.')
    } finally {
      setIsHistoryLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false

    fetch('/api/spmb-service-types', { cache: 'no-store' })
      .then(response => response.ok ? response.json() : null)
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
    return () => window.clearTimeout(timer)
  }, [])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (isSaving) return

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
      const payload = await response.json()
      if (!response.ok || !payload?.success) {
        throw new Error(payload?.message || 'Gagal menyimpan evaluasi.')
      }

      const savedEntry = payload.item as EvaluasiEntry
      setEntries(prev => [savedEntry, ...prev].slice(0, 100))
      setCatatan('')
      setSavedMessage('Evaluasi tersimpan di database.')
    } catch (error) {
      setSavedMessage(error instanceof Error ? error.message : 'Gagal menyimpan evaluasi.')
    } finally {
      setIsSaving(false)
      window.setTimeout(() => setSavedMessage(''), 3000)
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900 lg:h-screen lg:overflow-hidden">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-3 py-3 sm:px-5 lg:h-screen lg:min-h-0">
        <header className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <Link href="/live-spmb" className="mb-1 inline-flex items-center gap-2 text-xs font-semibold text-slate-600 transition-opacity hover:opacity-70">
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              Kembali
            </Link>
            <h1 className="truncate text-2xl font-extrabold tracking-normal sm:text-3xl">Evaluasi Pelayanan SPMB</h1>
          </div>
        </header>

        <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[0.95fr_1.35fr]">
          <form onSubmit={handleSubmit} className="flex min-h-0 flex-col rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between gap-3">
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
              <button
                type="submit"
                disabled={isSaving}
                className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-extrabold text-white shadow-sm transition hover:bg-slate-800"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                </svg>
                {isSaving ? 'Menyimpan' : 'Simpan'}
              </button>
            </div>

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
                        onClick={() => setNomorMeja(option)}
                        className={`flex h-10 items-center justify-center rounded-lg border text-sm font-extrabold transition ${
                          selected
                            ? 'border-slate-900 bg-slate-900 text-white shadow-sm'
                            : 'border-slate-200 bg-white text-slate-700 hover:border-slate-400 hover:bg-slate-50'
                        }`}
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
                        onChange={() => setIndikator(option.value)}
                        className="peer sr-only"
                      />
                      <span className={`flex h-11 items-center justify-center rounded-lg border px-2 text-sm font-extrabold transition ${option.className}`}>
                        {option.label}
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
                  onChange={event => setCatatan(event.target.value)}
                  rows={3}
                  placeholder="Opsional"
                  className="w-full resize-none rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
                />
              </div>
            </div>

            <div className="mt-auto pt-3">
              <button
                type="submit"
                disabled={isSaving}
                className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-extrabold text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                </svg>
                {isSaving ? 'Menyimpan...' : 'Simpan Evaluasi'}
              </button>
              {savedMessage && (
                <p className="mt-2 rounded-lg bg-sky-50 px-3 py-2 text-xs font-semibold text-sky-800">{savedMessage}</p>
              )}
            </div>
          </form>

          <section className="flex min-h-0 flex-col rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-extrabold">Riwayat Evaluasi</h2>
                <p className="text-xs font-semibold text-slate-500">{entries.length} evaluasi tersimpan</p>
              </div>
              <button
                type="button"
                onClick={loadEntries}
                disabled={isHistoryLoading}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {isHistoryLoading ? 'Memuat' : 'Muat ulang'}
              </button>
            </div>

            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
              {isHistoryLoading ? (
                <div className="flex h-full min-h-[180px] items-center justify-center rounded-lg border border-dashed border-slate-300 text-center">
                  <p className="text-sm font-semibold text-slate-500">Memuat riwayat evaluasi...</p>
                </div>
              ) : entries.length > 0 ? (
                entries.map(entry => (
                  <article key={entry.id} className="rounded-lg border border-slate-200 px-3 py-2">
                    <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-start">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="truncate text-sm font-extrabold text-slate-900">{entry.pelayanan}</h3>
                          <span className="text-xs font-semibold text-slate-500">Meja {entry.nomorMeja}</span>
                        </div>
                        <p className="mt-0.5 text-xs font-semibold text-slate-400">
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
          </section>
        </div>
      </div>
    </main>
  )
}
