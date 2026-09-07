import Link from 'next/link'
import {
  formatCmsDate,
  getCmsContent,
  resolveCmsUrl,
  type CmsArticle,
  type CmsFile,
} from '@/lib/cms'

function RichText({ html }: { html: string }) {
  if (!html.trim()) return <p className="text-sm italic text-slate-400">Informasi belum tersedia.</p>
  return <div className="cms-rich-text" dangerouslySetInnerHTML={{ __html: html }} />
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return <div className="rounded-2xl border border-dashed border-slate-300 bg-white/60 px-6 py-10 text-center text-sm text-slate-400">{children}</div>
}

function FileLinks({ files }: { files: CmsFile[] }) {
  if (!files.length) return null
  return (
    <div className="mt-5 flex flex-wrap gap-2">
      {files.map((file, index) => {
        const href = resolveCmsUrl(file.url)
        return href ? (
          <a key={file.id || `${file.name}-${index}`} href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs font-bold text-sky-700 transition hover:bg-sky-100">
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M12 3v12m0 0 4-4m-4 4-4-4M5 21h14" /></svg>
            {file.name}
          </a>
        ) : null
      })}
    </div>
  )
}

function PublicationCard({ item, accent = 'sky' }: { item: CmsArticle; accent?: 'sky' | 'amber' }) {
  const thumbnail = resolveCmsUrl(item.thumbnail_url)
  const accentClasses = accent === 'amber' ? 'bg-amber-100 text-amber-700' : 'bg-sky-100 text-sky-700'

  return (
    <details className="group overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm transition hover:shadow-md">
      {thumbnail && <img src={thumbnail} alt="" className="h-44 w-full object-cover" />}
      <summary className="cursor-pointer list-none p-6">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className={`rounded-full px-3 py-1 text-[11px] font-bold ${accentClasses}`}>{item.kategori}</span>
          <span className="text-xs text-slate-400">{formatCmsDate(item.tanggal)}</span>
        </div>
        <h3 className="text-lg font-extrabold leading-snug text-slate-900">{item.judul}</h3>
        <div className="mt-4 flex items-center justify-between text-xs text-slate-500">
          <span>{item.penulis}</span>
          <span className="font-bold text-sky-700 group-open:hidden">Baca selengkapnya</span>
          <span className="hidden font-bold text-sky-700 group-open:inline">Tutup</span>
        </div>
      </summary>
      <div className="border-t border-slate-100 px-6 pb-6 pt-5">
        <RichText html={item.deskripsi} />
        <FileLinks files={item.files || []} />
      </div>
    </details>
  )
}

export default async function InformasiPage() {
  const content = await getCmsContent()

  return (
    <main className="min-h-screen bg-slate-50 text-slate-800">
      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link href="/" className="flex min-w-0 items-center gap-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-sky-500">
            <img src="/logo.png" alt="Logo Sudin Pendidikan" className="h-10 w-10 shrink-0 object-contain" />
            <div className="min-w-0"><p className="truncate text-sm font-extrabold text-sky-900">Sudin Pendidikan</p><p className="truncate text-[11px] text-slate-500">Jakarta Utara — Wilayah 2</p></div>
          </Link>
          <nav className="hidden items-center gap-1 lg:flex">
            {[['informasi-publik', 'Informasi Publik'], ['layanan', 'Layanan'], ['pengumuman', 'Pengumuman'], ['artikel', 'Artikel'], ['galeri', 'Galeri']].map(([id, label]) => (
              <a key={id} href={`#${id}`} className="rounded-full px-3 py-2 text-xs font-bold text-slate-600 transition hover:bg-sky-50 hover:text-sky-700">{label}</a>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <Link href="/profil" className="hidden rounded-full border border-sky-200 bg-sky-50 px-4 py-2 text-xs font-bold text-sky-700 sm:inline-flex">Profil</Link>
            <Link href="/" className="rounded-full bg-sky-700 px-4 py-2 text-xs font-bold text-white">Beranda</Link>
          </div>
        </div>
      </header>

      <section className="relative overflow-hidden bg-gradient-to-br from-sky-900 via-blue-900 to-indigo-950 px-4 py-16 text-white sm:px-6 sm:py-20">
        <div className="absolute inset-0 opacity-10" style={{ backgroundImage: 'radial-gradient(circle, white 1px, transparent 1px)', backgroundSize: '24px 24px' }} />
        <div className="absolute -right-20 -top-20 h-80 w-80 rounded-full bg-cyan-400/25 blur-3xl" />
        <div className="relative mx-auto max-w-7xl">
          <p className="mb-3 text-xs font-bold uppercase tracking-[0.25em] text-sky-200">Pusat Informasi</p>
          <h1 className="max-w-3xl text-3xl font-black leading-tight sm:text-5xl">Informasi dan Layanan Publik</h1>
          <p className="mt-5 max-w-2xl text-sm leading-7 text-sky-100 sm:text-base">Akses informasi pelayanan, dokumen, pengumuman resmi, artikel, dan dokumentasi kegiatan dalam satu halaman.</p>
          {content && (
            <div className="mt-8 flex flex-wrap gap-3">
              {[['Layanan', content.layanan.length], ['Pengumuman', content.pengumuman.length], ['Artikel', content.artikel.length], ['Galeri', content.galeri.length]].map(([label, count]) => (
                <div key={String(label)} className="rounded-2xl border border-white/15 bg-white/10 px-4 py-3 backdrop-blur"><span className="block text-xl font-black">{count}</span><span className="text-[11px] text-sky-100">{label}</span></div>
              ))}
            </div>
          )}
        </div>
      </section>

      {!content ? (
        <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6"><div className="rounded-3xl border border-amber-200 bg-amber-50 p-8 text-center"><h2 className="font-bold text-amber-900">Konten belum dapat dimuat</h2><p className="mt-2 text-sm text-amber-700">Silakan coba kembali beberapa saat lagi.</p></div></section>
      ) : (
        <div className="mx-auto max-w-7xl space-y-20 px-4 py-14 sm:px-6 sm:py-20">
          <section id="informasi-publik" className="scroll-mt-24">
            <div className="mb-8"><p className="section-eyebrow">Standar Pelayanan</p><h2 className="section-title">Informasi Publik</h2></div>
            <div className="grid gap-6 lg:grid-cols-3">
              {[
                ['Jaminan Pelayanan', content.informasi_publik.jaminan_pelayanan, 'shield'],
                ['Keamanan & Keselamatan', content.informasi_publik.keamanan_keselamatan, 'lock'],
                ['Kompensasi Pelayanan', content.informasi_publik.kompensasi_pelayanan, 'coin'],
              ].map(([title, html, icon]) => (
                <article key={title} className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
                  <span className="mb-5 grid h-11 w-11 place-items-center rounded-xl bg-sky-100 font-black text-sky-700">{icon === 'shield' ? '✓' : icon === 'lock' ? '⌾' : '↺'}</span>
                  <h3 className="mb-4 text-lg font-extrabold text-slate-900">{title}</h3><RichText html={html} />
                </article>
              ))}
            </div>
          </section>

          <section id="layanan" className="scroll-mt-24">
            <div className="mb-8"><p className="section-eyebrow">Untuk Masyarakat</p><h2 className="section-title">Layanan Publik</h2></div>
            {content.layanan.length ? <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">{content.layanan.map(service => (
              <article key={service.id} className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
                <span className="mb-5 grid h-11 w-11 place-items-center rounded-xl bg-blue-100 text-xl font-black text-blue-700">{service.nama.charAt(0).toUpperCase()}</span>
                <h3 className="mb-3 text-lg font-extrabold text-slate-900">{service.nama}</h3><RichText html={service.deskripsi} /><FileLinks files={service.files} />
              </article>
            ))}</div> : <EmptyState>Belum ada layanan publik aktif.</EmptyState>}
          </section>

          <section id="pengumuman" className="scroll-mt-24">
            <div className="mb-8"><p className="section-eyebrow">Pemberitahuan Resmi</p><h2 className="section-title">Pengumuman</h2></div>
            {content.pengumuman.length ? <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">{content.pengumuman.map(item => <PublicationCard key={item.id} item={item} accent="amber" />)}</div> : <EmptyState>Belum ada pengumuman yang dipublikasikan.</EmptyState>}
          </section>

          <section id="artikel" className="scroll-mt-24">
            <div className="mb-8"><p className="section-eyebrow">Kabar Pendidikan</p><h2 className="section-title">Artikel</h2></div>
            {content.artikel.length ? <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">{content.artikel.map(item => <PublicationCard key={item.id} item={item} />)}</div> : <EmptyState>Belum ada artikel yang dipublikasikan.</EmptyState>}
          </section>

          <section id="galeri" className="scroll-mt-24">
            <div className="mb-8"><p className="section-eyebrow">Dokumentasi</p><h2 className="section-title">Galeri Kegiatan</h2></div>
            {content.galeri.length ? <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">{content.galeri.map(gallery => {
              const cover = resolveCmsUrl(gallery.thumbnail_url || gallery.gambar_kegiatan[0]?.url)
              return <details key={gallery.id} className="group overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">{cover && <img src={cover} alt={gallery.nama_kegiatan} className="h-56 w-full object-cover" />}<summary className="cursor-pointer list-none p-6"><p className="text-xs text-sky-600">{formatCmsDate(gallery.tanggal)}</p><h3 className="mt-2 text-lg font-extrabold text-slate-900">{gallery.nama_kegiatan}</h3><p className="mt-2 text-xs text-slate-500">{gallery.gambar_kegiatan.length} foto · {gallery.penulis}</p></summary><div className="grid grid-cols-2 gap-2 border-t border-slate-100 p-4">{gallery.gambar_kegiatan.map((photo, index) => { const url = resolveCmsUrl(photo.url); return url ? <a key={photo.id || index} href={url} target="_blank" rel="noopener noreferrer"><img src={url} alt={`${gallery.nama_kegiatan} ${index + 1}`} className="h-32 w-full rounded-xl object-cover transition hover:opacity-85" /></a> : null })}</div></details>
            })}</div> : <EmptyState>Belum ada galeri yang dipublikasikan.</EmptyState>}
          </section>
        </div>
      )}

      <footer className="border-t border-slate-200 bg-white px-4 py-7 text-center text-xs text-slate-500">© {new Date().getFullYear()} Sudin Pendidikan Jakarta Utara Wilayah II</footer>
    </main>
  )
}
