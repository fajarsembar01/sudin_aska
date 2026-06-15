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

const readJsonResponse = async (response: Response) => {
  const text = await response.text()
  if (!text) return {}

  try {
    return JSON.parse(text)
  } catch {
    throw new Error('API evaluasi belum mengembalikan JSON. Cek DASHBOARD_BASE_URL dan pastikan dashboard sudah direstart.')
  }
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
  const [savedMessage, setSavedMessage] = useState('')
  const [messageTone, setMessageTone] = useState<'success' | 'error'>('success')
  const [isSaving, setIsSaving] = useState(false)
  const [isSubmitted, setIsSubmitted] = useState(false)
  const [isHistoryLoading, setIsHistoryLoading] = useState(true)

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
    } catch (error) {
      setMessageTone('error')
      setSavedMessage(error instanceof Error ? error.message : 'Gagal memuat riwayat evaluasi.')
    } finally {
      setIsHistoryLoading(false)
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
    return () => window.clearTimeout(timer)
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
