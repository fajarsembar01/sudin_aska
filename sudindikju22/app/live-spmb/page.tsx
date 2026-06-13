'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'

export default function LiveSpmbPage() {
  const router = useRouter()

  return (
    <main className="min-h-screen bg-gradient-to-br from-sky-50 via-white to-slate-100 relative overflow-hidden">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-[400px] h-[400px] bg-gradient-to-br from-sky-200/30 to-blue-300/20 rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-1/4 w-[350px] h-[350px] bg-gradient-to-br from-emerald-200/25 to-cyan-300/15 rounded-full blur-3xl" />
        <div
          className="absolute inset-0 opacity-[0.02]"
          style={{
            backgroundImage: 'radial-gradient(circle, #0ea5e9 1px, transparent 1px)',
            backgroundSize: '20px 20px'
          }}
        />
      </div>

      <nav className="relative z-20 w-full px-4 sm:px-6 py-4 flex items-center justify-between border-b border-slate-200/70 bg-white/50 backdrop-blur-sm">
        <Link href="/" className="flex items-center gap-2 group">
          <img
            src="/logo.png"
            alt="Logo Sudin Pendidikan"
            className="w-8 h-8 object-contain"
          />
          <div className="hidden sm:block">
            <p className="text-sm font-bold text-sky-900">Sudin Pendidikan JU 2</p>
            <p className="text-xs text-slate-500">Live SPMB</p>
          </div>
        </Link>
        <Link href="/" className="text-sm font-medium text-slate-500 hover:text-slate-900 transition-colors">
          Kembali ke Beranda
        </Link>
      </nav>

      <div className="relative z-10 px-4 sm:px-6 py-8 sm:py-10">
        <div className="mx-auto max-w-5xl">
          <div className="text-center mb-6 sm:mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-emerald-100 mb-5 shadow-sm">
              <i className="bi bi-broadcast text-3xl text-emerald-600" />
            </div>
            <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900">
              Live SPMB
            </h1>
            <p className="mt-3 text-sm sm:text-base text-slate-600 max-w-2xl mx-auto">
              Pilih jalur langsung, atau aktifkan mode bergantian untuk melihat SD dan SMP SMA otomatis.
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-3 mb-6">
            <button
              onClick={() => router.push('/live-spmb-sd')}
              className="rounded-2xl border border-orange-200/70 bg-white/80 p-5 text-left shadow-lg transition-all duration-300 hover:bg-white hover:-translate-y-0.5"
            >
              <p className="text-xs font-bold uppercase tracking-wide text-orange-500">Opsi 1</p>
              <h2 className="mt-2 text-xl sm:text-2xl font-extrabold text-slate-900">Live SPMB SD</h2>
              <p className="mt-2 text-sm text-slate-600">Buka data SD langsung.</p>
            </button>

            <button
              onClick={() => router.push('/live-spmb-smp')}
              className="rounded-2xl border border-emerald-200/70 bg-white/80 p-5 text-left shadow-lg transition-all duration-300 hover:bg-white hover:-translate-y-0.5"
            >
              <p className="text-xs font-bold uppercase tracking-wide text-emerald-600">Opsi 2</p>
              <h2 className="mt-2 text-xl sm:text-2xl font-extrabold text-slate-900">Live SPMB SMP SMA</h2>
              <p className="mt-2 text-sm text-slate-600">Buka data SMP + SMA langsung.</p>
            </button>

            <button
              onClick={() => router.push('/live-spmb-sd?mix=1')}
              className="rounded-2xl border border-sky-200/70 bg-white/80 p-5 text-left shadow-lg transition-all duration-300 hover:bg-white hover:-translate-y-0.5"
            >
              <p className="text-xs font-bold uppercase tracking-wide text-sky-600">Opsi 3</p>
              <h2 className="mt-2 text-xl sm:text-2xl font-extrabold text-slate-900">Mix SD / SMP SMA</h2>
              <p className="mt-2 text-sm text-slate-600">Berganti otomatis tiap 3 menit.</p>
            </button>
          </div>
        </div>
      </div>
    </main>
  )
}
