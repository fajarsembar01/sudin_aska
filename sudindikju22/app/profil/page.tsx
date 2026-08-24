import Link from 'next/link'

const portalApiBase = (
  process.env.PORTAL_API_BASE ||
  process.env.NEXT_PUBLIC_PORTAL_API_BASE ||
  (process.env.NODE_ENV === 'development'
    ? 'http://127.0.0.1:5002'
    : 'https://admin.sudindikju2.com')
).replace(/\/+$/, '')

interface ProfilInstansi {
  deskripsi_utama: string
  visi: string
  misi: string
  tugas_fungsi: string
  motto_pelayanan: string
  struktur_organisasi_url: string | null
  updated_at: string | null
}

interface ProfilResponse {
  success: boolean
  data?: ProfilInstansi
}

async function getProfil(): Promise<ProfilInstansi | null> {
  try {
    const response = await fetch(`${portalApiBase}/cms/api/public/profil`, {
      cache: 'no-store',
      headers: { accept: 'application/json' },
    })

    if (!response.ok) return null
    const payload = (await response.json()) as ProfilResponse
    return payload.success && payload.data ? payload.data : null
  } catch {
    return null
  }
}

function resolvePortalUrl(path: string | null) {
  if (!path) return null
  if (/^https?:\/\//i.test(path)) return path
  return `${portalApiBase}${path.startsWith('/') ? path : `/${path}`}`
}

function RichText({ html }: { html: string }) {
  if (!html.trim()) {
    return <p className="text-slate-400 italic">Informasi belum tersedia.</p>
  }

  return <div className="cms-rich-text" dangerouslySetInnerHTML={{ __html: html }} />
}

function SectionIcon({ type }: { type: 'vision' | 'mission' | 'work' }) {
  const paths = {
    vision: <><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6S2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="2.5" /></>,
    mission: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="4" /><path d="m15 9 5-5m0 0v4m0-4h-4" /></>,
    work: <><path d="M9 6V4h6v2M4 8h16v11H4z" /><path d="M4 12h16M10 12v2h4v-2" /></>,
  }

  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[type]}
    </svg>
  )
}

export default async function ProfilPage() {
  const profil = await getProfil()
  const strukturUrl = resolvePortalUrl(profil?.struktur_organisasi_url || null)

  return (
    <main className="min-h-screen bg-slate-50 text-slate-800">
      <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <Link href="/" className="flex items-center gap-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-sky-500">
            <img src="/logo.png" alt="Logo Sudin Pendidikan" className="h-10 w-10 object-contain" />
            <div>
              <p className="text-sm font-extrabold text-sky-900">Sudin Pendidikan</p>
              <p className="text-[11px] text-slate-500">Jakarta Utara — Wilayah 2</p>
            </div>
          </Link>
          <div className="flex items-center gap-2">
            <Link href="/informasi" className="hidden rounded-full border border-sky-200 bg-sky-50 px-4 py-2 text-xs font-bold text-sky-700 transition hover:bg-sky-100 sm:inline-flex">Informasi</Link>
            <Link href="/" className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-4 py-2 text-xs font-bold text-sky-700 transition hover:bg-sky-100">
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg>
              Beranda
            </Link>
          </div>
        </div>
      </header>

      <section className="relative overflow-hidden bg-gradient-to-br from-sky-900 via-sky-800 to-blue-900 px-4 py-16 text-white sm:px-6 sm:py-20">
        <div className="absolute inset-0 opacity-10" style={{ backgroundImage: 'radial-gradient(circle, white 1px, transparent 1px)', backgroundSize: '24px 24px' }} />
        <div className="absolute -right-20 -top-24 h-72 w-72 rounded-full bg-cyan-400/25 blur-3xl" />
        <div className="relative mx-auto max-w-6xl">
          <p className="mb-3 text-xs font-bold uppercase tracking-[0.24em] text-sky-200">Tentang Instansi</p>
          <h1 className="max-w-3xl text-3xl font-black leading-tight sm:text-5xl">Profil Suku Dinas Pendidikan Jakarta Utara Wilayah II</h1>
          <p className="mt-5 max-w-2xl text-sm leading-7 text-sky-100 sm:text-base">Mengenal arah pelayanan, tanggung jawab, dan struktur organisasi kami dalam mendukung pendidikan di Jakarta Utara.</p>
        </div>
      </section>

      {!profil ? (
        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <div className="rounded-3xl border border-amber-200 bg-amber-50 p-8 text-center">
            <h2 className="text-lg font-bold text-amber-900">Profil belum dapat ditampilkan</h2>
            <p className="mt-2 text-sm text-amber-700">Silakan coba muat ulang halaman beberapa saat lagi.</p>
          </div>
        </section>
      ) : (
        <div className="mx-auto max-w-6xl space-y-8 px-4 py-10 sm:px-6 sm:py-14">
          <section className="grid gap-8 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-9 lg:grid-cols-[1fr_280px] lg:items-center">
            <div>
              <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-sky-600">Sekilas Tentang Kami</p>
              <RichText html={profil.deskripsi_utama} />
            </div>
            {profil.motto_pelayanan.trim() && (
              <aside className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-sky-600 to-blue-700 p-6 text-white shadow-lg shadow-sky-900/15">
                <svg className="absolute -right-2 -top-3 h-20 w-20 text-white/10" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 17h4V9H7v8Zm6 0h4V9h-4v8ZM6 5h5v2H8v2H5V8c0-1.7.3-3 1-3Zm7 0h5v2h-3v2h-3V8c0-1.7.3-3 1-3Z" /></svg>
                <p className="mb-3 text-[11px] font-bold uppercase tracking-[0.2em] text-sky-100">Motto Pelayanan</p>
                <RichText html={profil.motto_pelayanan} />
              </aside>
            )}
          </section>

          <section className="grid gap-6 lg:grid-cols-2">
            <article className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
              <div className="mb-5 flex items-center gap-3">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-sky-100 text-sky-700"><SectionIcon type="vision" /></span>
                <h2 className="text-xl font-extrabold text-slate-900">Visi</h2>
              </div>
              <RichText html={profil.visi} />
            </article>
            <article className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
              <div className="mb-5 flex items-center gap-3">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-blue-100 text-blue-700"><SectionIcon type="mission" /></span>
                <h2 className="text-xl font-extrabold text-slate-900">Misi</h2>
              </div>
              <RichText html={profil.misi} />
            </article>
          </section>

          <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-9">
            <div className="mb-5 flex items-center gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-indigo-100 text-indigo-700"><SectionIcon type="work" /></span>
              <h2 className="text-xl font-extrabold text-slate-900">Tugas &amp; Fungsi</h2>
            </div>
            <RichText html={profil.tugas_fungsi} />
          </section>

          <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-9">
            <div className="mb-6">
              <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-sky-600">Organisasi</p>
              <h2 className="text-2xl font-extrabold text-slate-900">Struktur Organisasi</h2>
            </div>
            {strukturUrl ? (
              <a href={strukturUrl} target="_blank" rel="noopener noreferrer" className="block overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 p-3 transition hover:border-sky-300 hover:shadow-md" title="Buka gambar ukuran penuh">
                <img src={strukturUrl} alt="Struktur Organisasi Sudin Pendidikan Jakarta Utara Wilayah II" className="mx-auto max-h-[720px] w-auto object-contain" />
              </a>
            ) : (
              <div className="grid min-h-48 place-items-center rounded-2xl border border-dashed border-slate-300 bg-slate-50 text-sm text-slate-400">Gambar struktur organisasi belum tersedia.</div>
            )}
          </section>
        </div>
      )}

      <footer className="border-t border-slate-200 bg-white px-4 py-6 text-center text-xs text-slate-500 sm:px-6">© {new Date().getFullYear()} Sudin Pendidikan Jakarta Utara Wilayah II</footer>
    </main>
  )
}
