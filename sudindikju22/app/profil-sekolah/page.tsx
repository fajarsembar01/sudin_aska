'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import { InstagramEmbed, TikTokEmbed } from 'react-social-media-embed'

const CATEGORY_LABELS: Record<string, string> = {
  'pengelolaan-sampah': 'Pengelolaan Sampah',
  'konservasi-energi': 'Konservasi Energi',
  'konservasi-air': 'Konservasi Air',
  'kebersihan-sanitasi-drainase': 'Kebersihan & Sanitasi',
  kompos: 'Kompos',
  tanaman: 'Tanaman',
}

const PORTAL_API_BASE = (process.env.NEXT_PUBLIC_PORTAL_API_BASE || 'https://admin.sudindikju2.com').replace(/\/+$/, '')

const portalUrl = (path: string) => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${PORTAL_API_BASE}${normalizedPath}`
}

interface PublicStat {
  label: string
  value: string | number
}

interface PublicContact {
  label: string
  value: string
  href: string
}

interface PublicLink {
  label: string
  href: string
}

interface PublicSchool {
  id: number
  npsn?: string | null
  name: string
  jenjang?: string | null
  alamat?: string | null
  status?: string | null
  logo_url?: string | null
  public_location?: string | null
  public_stats?: PublicStat[]
  public_contacts?: PublicContact[]
  public_links?: PublicLink[]
  metadata?: {
    rt?: string
    rw?: string
    postal_code?: string
    empty_seats?: string | number
    empty_seats_by_grade?: string | Record<string, string | number>
  }
}

interface PublicPost {
  id: number
  media_type: 'image' | 'video_link' | string
  media_path?: string | null
  media_urls?: string[] | null
  description?: string | null
  created_at?: string | null
  thumbnail_path?: string | null
}

interface PublicProfileResponse {
  success: boolean
  message?: string
  school?: PublicSchool
  posts?: PublicPost[]
  category?: string
  title?: string
}

function getPlatformInfo(url: string) {
  if (!url) return { type: 'unknown', id: null };
  const ytMatch = url.match(/(?:youtube\.com\/(?:[^/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?/\s]{11})/i);
  if (ytMatch) return { type: 'youtube', id: ytMatch[1] };
  const ttMatch = url.match(/(?:tiktok\.com\/.*\/video\/|tiktok\.com\/v\/|vt\.tiktok\.com\/)([\w\d]+)/i);
  if (ttMatch) return { type: 'tiktok', id: ttMatch[1] };
  const igMatch = url.match(/instagram\.com\/(?:p|reel|tv)\/([A-Za-z0-9_-]+)/i);
  if (igMatch) return { type: 'instagram', id: igMatch[1] };
  const gdMatch = url.match(/drive\.google\.com\/(?:file\/d\/|open\?id=)([\w-]+)/i);
  if (gdMatch) return { type: 'gdrive', id: gdMatch[1] };
  return { type: 'unknown', id: null };
}

function getYoutubeId(url?: string | null) {
  if (!url) return null
  const match = url.match(/(?:youtube\.com\/(?:[^/]+\/.+\/|(?:v|e(?:mbed)?|shorts)\/|.*[?&]v=)|youtu\.be\/)([^"&?/\s]{11})/i)
  return match ? match[1] : null
}

function resolvePortalUrl(value?: string | null) {
  const clean = (value || '').trim()
  if (!clean) return ''
  if (/^https?:\/\//i.test(clean)) {
    try {
      const parsed = new URL(clean)
      if (['127.0.0.1', 'localhost'].includes(parsed.hostname) && parsed.pathname.startsWith('/portal/')) {
        return portalUrl(`${parsed.pathname}${parsed.search}${parsed.hash}`)
      }
    } catch {
      return clean
    }
    return clean
  }
  if (clean.startsWith('/portal/')) return portalUrl(clean)
  if (clean.startsWith('/uploads/')) return portalUrl(`/portal${clean}`)
  if (clean.startsWith('portal/')) return portalUrl(`/${clean}`)
  if (clean.startsWith('uploads/portal/')) return portalUrl(`/portal/uploads/${clean.slice('uploads/portal/'.length)}`)
  if (clean.startsWith('uploads/')) return portalUrl(`/portal/${clean}`)
  return portalUrl(`/portal/uploads/${clean}`)
}

function resolveMediaUrls(post: PublicPost) {
  const urls = Array.isArray(post.media_urls) && post.media_urls.length
    ? post.media_urls
    : post.media_path
      ? [post.media_path]
      : []

  return urls.map(resolvePortalUrl).filter(Boolean)
}

function formatDate(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' })
}

function ActionIcon({ label }: { label: string }) {
  const normalized = label.toLowerCase()
  const baseClass = 'w-3.5 h-3.5'

  if (normalized.includes('instagram')) {
    return (
      <svg className={baseClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="3" width="18" height="18" rx="5" />
        <circle cx="12" cy="12" r="4" />
        <circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none" />
      </svg>
    )
  }

  if (normalized.includes('youtube')) {
    return (
      <svg className={baseClass} viewBox="0 0 24 24" fill="currentColor">
        <path d="M21.6 7.2a3 3 0 0 0-2.1-2.1C17.7 4.6 12 4.6 12 4.6s-5.7 0-7.5.5a3 3 0 0 0-2.1 2.1A31 31 0 0 0 2 12a31 31 0 0 0 .4 4.8 3 3 0 0 0 2.1 2.1c1.8.5 7.5.5 7.5.5s5.7 0 7.5-.5a3 3 0 0 0 2.1-2.1A31 31 0 0 0 22 12a31 31 0 0 0-.4-4.8ZM10 15.3V8.7L15.8 12 10 15.3Z" />
      </svg>
    )
  }

  if (normalized.includes('tiktok')) {
    return (
      <svg className={baseClass} viewBox="0 0 24 24" fill="currentColor">
        <path d="M16.7 3c.3 2.2 1.5 3.7 3.7 3.9v3.2a7 7 0 0 1-3.7-1.1v5.5c0 3.6-2.3 6.1-5.8 6.1-3.1 0-5.4-2.1-5.4-5.1 0-3.4 2.7-5.5 6.2-5.2v3.4c-1.5-.2-2.8.4-2.8 1.8 0 1.1.9 1.8 2 1.8 1.4 0 2.1-.8 2.1-2.6V3h3.7Z" />
      </svg>
    )
  }

  if (normalized.includes('telegram')) {
    return (
      <svg className={baseClass} viewBox="0 0 24 24" fill="currentColor">
        <path d="M21.7 4.4 18.5 19c-.2 1-.8 1.2-1.6.8l-4.5-3.3-2.2 2.1c-.2.2-.4.4-.9.4l.3-4.6 8.4-7.6c.4-.3-.1-.5-.6-.2L7 13.1 2.5 11.7c-1-.3-1-1 .2-1.5L20.4 3.4c.8-.3 1.5.2 1.3 1Z" />
      </svg>
    )
  }

  if (normalized.includes('wa')) {
    return (
      <svg className={baseClass} viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2.5a9 9 0 0 0-7.7 13.6l-1 3.7 3.8-1A9 9 0 1 0 12 2.5Zm0 16.5a7.3 7.3 0 0 1-3.7-1l-.3-.2-2.2.6.6-2.1-.2-.3A7.4 7.4 0 1 1 12 19Zm4.1-5.5c-.2-.1-1.3-.7-1.5-.7s-.4-.1-.5.1-.6.7-.7.9-.3.2-.5.1a6 6 0 0 1-1.8-1.1 7 7 0 0 1-1.2-1.5c-.1-.2 0-.4.1-.5l.4-.5c.1-.2.2-.3.2-.5s0-.3-.1-.4l-.7-1.6c-.2-.4-.4-.3-.5-.3h-.4c-.2 0-.4.1-.6.3-.2.2-.8.8-.8 1.9s.8 2.2.9 2.3a8.7 8.7 0 0 0 3.4 3.1c1.3.6 1.8.7 2.4.6.7-.1 2-.8 2.2-1.5.3-.7.3-1.3.2-1.5l-.5-.2Z" />
      </svg>
    )
  }

  if (normalized.includes('telepon')) {
    return (
      <svg className={baseClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.4 19.4 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.3 1.7.6 2.5a2 2 0 0 1-.5 2.1L8 9.5a16 16 0 0 0 6.5 6.5l1.2-1.2a2 2 0 0 1 2.1-.5c.8.3 1.6.5 2.5.6A2 2 0 0 1 22 16.9Z" />
      </svg>
    )
  }

  if (normalized.includes('email')) {
    return (
      <svg className={baseClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 4h16v16H4z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="m4 7 8 6 8-6" />
      </svg>
    )
  }

  if (normalized.includes('maps')) {
    return (
      <svg className={baseClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 21s7-5.2 7-11a7 7 0 1 0-14 0c0 5.8 7 11 7 11Z" />
        <circle cx="12" cy="10" r="2.5" />
      </svg>
    )
  }

  return (
    <svg className={baseClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="9" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" />
    </svg>
  )
}

function buildLocation(school: PublicSchool) {
  const rtRw = [
    school.metadata?.rt ? `RT ${school.metadata.rt}` : '',
    school.metadata?.rw ? `RW ${school.metadata.rw}` : '',
  ].filter(Boolean).join(' / ')

  return [
    school.alamat,
    rtRw,
    school.public_location,
    school.metadata?.postal_code ? `Kode Pos ${school.metadata.postal_code}` : '',
  ].filter(Boolean).join(', ')
}

export default function ProfilSekolahPage() {
  const [loading, setLoading] = useState(true)
  const [school, setSchool] = useState<PublicSchool | null>(null)
  const [posts, setPosts] = useState<PublicPost[]>([])
  const [category, setCategory] = useState('')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const [lightboxIndex, setLightboxIndex] = useState(-1)
  const [lightboxUrls, setLightboxUrls] = useState<string[]>([])
  const [activePost, setActivePost] = useState<PublicPost | null>(null)

  const openLightbox = (urls: string[], idx = 0, post: PublicPost | null = null) => {
    setLightboxUrls(urls)
    setLightboxIndex(idx)
    setActivePost(post)
  }

  const closeLightbox = () => {
    setLightboxIndex(-1)
    setActivePost(null)
  }

  useEffect(() => {
    document.body.style.overflow = lightboxIndex >= 0 ? 'hidden' : ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [lightboxIndex])

  const fetchProfile = useCallback(async () => {
    const params = new URLSearchParams(window.location.search)
    const schoolId = params.get('school_id')
    const selectedCategory = params.get('category') || 'tanaman'

    if (!schoolId) {
      setErrorMsg('Pilih sekolah dari halaman Adiwiyata untuk melihat profil publik.')
      setLoading(false)
      return
    }

    try {
      const res = await fetch(`/api/profil-sekolah?school_id=${schoolId}&category=${encodeURIComponent(selectedCategory)}`)
      const data: PublicProfileResponse = await res.json()

      if (!data.success || !data.school) {
        setErrorMsg(data.message || 'Profil sekolah tidak ditemukan.')
        return
      }

      setSchool(data.school)
      setPosts(data.posts || [])
      setCategory(data.category || selectedCategory)
    } catch {
      setErrorMsg('Gagal memuat profil sekolah publik.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const initialFetch = window.setTimeout(fetchProfile, 0)
    return () => window.clearTimeout(initialFetch)
  }, [fetchProfile])

  if (loading) {
    return (
      <main className="min-h-screen bg-[#f0f2f5] flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-4 border-emerald-100 border-t-emerald-600 rounded-full animate-spin" />
          <p className="text-sm font-semibold text-slate-500">Memuat profil sekolah...</p>
        </div>
      </main>
    )
  }

  if (!school) {
    return (
      <main className="min-h-screen bg-[#f0f2f5] flex items-center justify-center p-6">
        <div className="max-w-md w-full rounded-[18px] border border-slate-200 bg-white p-7 text-center shadow-sm">
          <h1 className="text-lg font-extrabold text-slate-900">Profil Tidak Tersedia</h1>
          <p className="mt-2 text-sm text-slate-500">{errorMsg}</p>
          <Link href="/adiwiyata" className="mt-5 inline-flex items-center justify-center rounded-lg bg-emerald-600 px-4 py-2 text-sm font-bold text-white hover:bg-emerald-700">
            Buka Adiwiyata
          </Link>
        </div>
      </main>
    )
  }

  const location = buildLocation(school)
  const categoryLabel = CATEGORY_LABELS[category] || category

  return (
    <main className="min-h-screen bg-[#f0f2f5] text-slate-900">
      {lightboxIndex >= 0 && (
        <div className="fixed inset-0 z-[200] bg-black/95 backdrop-blur-md flex items-center justify-center p-3 sm:p-6" onClick={closeLightbox}>
          <button onClick={closeLightbox} className="absolute top-5 right-5 z-50 w-10 h-10 flex items-center justify-center rounded-full bg-white/10 hover:bg-white/20 text-white transition-all border border-white/20">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>

          <div className="bg-black rounded-3xl overflow-hidden flex flex-col lg:flex-row w-full max-w-4xl max-h-[92vh] shadow-[0_32px_80px_rgba(0,0,0,0.25)] relative border border-slate-800" onClick={e => e.stopPropagation()}>
            <div className="flex-1 relative flex items-center justify-center bg-black min-h-[40vh] lg:min-h-[500px]">
              {activePost?.media_type === 'video_link' ? (
                <div className="w-full h-full flex items-center justify-center">
                  {(() => {
                    const url = lightboxUrls[0];
                    const info = getPlatformInfo(url);
                    if (info.type === 'youtube') return <iframe className="w-full h-full border-0" src={`https://www.youtube.com/embed/${info.id}`} allowFullScreen />;
                    if (info.type === 'tiktok') {
                      return (
                        <div className="w-full h-full overflow-y-auto bg-black flex items-center justify-center custom-scroll p-4">
                          <div className="w-full max-w-[340px] rounded-xl overflow-hidden shadow-2xl">
                            <TikTokEmbed url={url} width="100%" />
                          </div>
                        </div>
                      )
                    }
                    if (info.type === 'instagram') {
                      return (
                        <div className="w-full h-full overflow-y-auto bg-black flex items-center justify-center custom-scroll p-4">
                          <div className="w-full max-w-[400px] rounded-xl overflow-hidden shadow-2xl bg-white">
                            <InstagramEmbed url={url} width="100%" captioned />
                          </div>
                        </div>
                      )
                    }
                    if (info.type === 'gdrive') return <iframe className="w-full h-full border-0" src={`https://drive.google.com/file/d/${info.id}/preview`} allowFullScreen />;
                    return (
                      <div className="text-white text-center p-6">
                        <p className="mb-4 text-lg font-semibold">Tautan video eksternal</p>
                        <a href={url} target="_blank" rel="noopener noreferrer" className="inline-block px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 rounded-xl text-white font-bold transition-colors">
                          Buka di Tab Baru
                        </a>
                      </div>
                    );
                  })()}
                </div>
              ) : (
                <img src={lightboxUrls[lightboxIndex]} alt="Gallery" className="max-w-full max-h-[60vh] lg:max-h-[92vh] object-contain select-none" />
              )}
              
              {lightboxUrls.length > 1 && (
                <>
                  <button onClick={e => { e.stopPropagation(); setLightboxIndex(p => p > 0 ? p - 1 : lightboxUrls.length - 1) }} className="absolute left-4 top-1/2 -translate-y-1/2 w-12 h-12 flex items-center justify-center rounded-full bg-black/60 hover:bg-black/80 text-white border border-white/20 backdrop-blur-md transition-all hover:scale-110">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
                  </button>
                  <button onClick={e => { e.stopPropagation(); setLightboxIndex(p => p < lightboxUrls.length - 1 ? p + 1 : 0) }} className="absolute right-4 top-1/2 -translate-y-1/2 w-12 h-12 flex items-center justify-center rounded-full bg-black/60 hover:bg-black/80 text-white border border-white/20 backdrop-blur-md transition-all hover:scale-110">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" /></svg>
                  </button>
                </>
              )}
            </div>
            {/* Deskripsi */}
            <div className="w-full lg:w-[320px] bg-white flex flex-col p-6 overflow-y-auto border-t lg:border-t-0 lg:border-l border-slate-100">
              <h3 className="font-black text-slate-900 text-sm mb-3">Deskripsi</h3>
              <p className="text-sm text-slate-600 whitespace-pre-wrap flex-1">{activePost?.description || <span className="italic text-slate-400">Tidak ada deskripsi.</span>}</p>
              {activePost?.created_at && (
                <p className="mt-6 text-xs text-emerald-600 font-bold border-t border-slate-100 pt-4">{formatDate(activePost.created_at)}</p>
              )}
            </div>
          </div>
        </div>
      )}

      <nav className="sticky top-0 z-30 h-14 border-b border-slate-200 bg-white/95 backdrop-blur-sm shadow-sm">
        <div className="mx-auto max-w-[980px] h-full px-4 flex items-center gap-3">
          <Link href="/adiwiyata" className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm font-semibold text-slate-500 hover:border-emerald-500 hover:bg-emerald-50 hover:text-emerald-700">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0 7-7m-7 7h18" />
            </svg>
            Kembali
          </Link>
          <div className="flex-1 min-w-0 flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-emerald-600 text-white flex items-center justify-center text-sm font-black">A</div>
            <p className="font-bold text-slate-900 truncate">Profil Sekolah Adiwiyata</p>
          </div>
          <span className="hidden sm:inline-flex rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700 max-w-[220px] truncate">
            {categoryLabel}
          </span>
        </div>
      </nav>

      <div className="mx-auto max-w-[980px] px-4 py-5">
        <section className="rounded-[18px] border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="grid grid-cols-[auto_1fr] gap-4 p-4 sm:p-5 items-center">
            <div className="w-[74px] h-[74px] rounded-[18px] overflow-hidden bg-gradient-to-br from-emerald-600 to-teal-700 text-white flex items-center justify-center text-2xl font-black shadow-sm">
              {school.logo_url ? (
                <img src={resolvePortalUrl(school.logo_url)} alt={`Logo ${school.name}`} className="w-full h-full object-contain bg-white p-1.5" />
              ) : (
                school.name.charAt(0)
              )}
            </div>

            <div className="min-w-0">
              <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-extrabold text-emerald-700 mb-2">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                {categoryLabel}
              </div>
              <h1 className="text-xl sm:text-2xl font-black leading-tight text-slate-900">{school.name}</h1>
              <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[12px] font-semibold text-slate-500">
                <span>NPSN {school.npsn || '-'}</span>
                {school.jenjang && <span>{school.jenjang}</span>}
                {school.status && <span>{school.status}</span>}
                {school.public_location && <span>{school.public_location}</span>}
              </div>
              {location && <p className="mt-2 text-[13px] leading-relaxed text-slate-500 line-clamp-2">{location}</p>}
            </div>
          </div>

          {school.public_stats && school.public_stats.length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-5 border-t border-slate-200 bg-slate-50/70">
              {school.public_stats.map(stat => (
                <div key={stat.label} className="px-4 py-3 border-r border-slate-200 last:border-r-0">
                  <strong className="block text-lg font-black text-slate-900 leading-none">{stat.value}</strong>
                  <span className="block mt-1 text-[11px] font-bold text-slate-500">{stat.label}</span>
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-wrap justify-center gap-2 p-4 border-t border-slate-200">
            {school.public_contacts?.map(contact => (
              <a key={contact.label} href={contact.href} title={contact.label} aria-label={contact.label} className="inline-flex min-h-8 items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-bold text-slate-700 hover:border-emerald-500 hover:bg-emerald-50 hover:text-emerald-700">
                <span className="leading-none"><ActionIcon label={contact.label} /></span>
                {contact.label}
              </a>
            ))}
            {school.public_links?.map(link => (
              <a key={link.label} href={link.href} target="_blank" rel="noopener noreferrer" title={link.label} aria-label={link.label} className="inline-flex min-h-8 items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-bold text-slate-700 hover:border-emerald-500 hover:bg-emerald-50 hover:text-emerald-700">
                <span className="leading-none"><ActionIcon label={link.label} /></span>
                {link.label}
              </a>
            ))}
          </div>
        </section>

        <section className="mt-5">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="text-base font-black text-slate-900">Galeri Dokumentasi</h2>
            <span className="rounded-full bg-emerald-600 px-3 py-1 text-xs font-bold text-white">{posts.length} Postingan</span>
          </div>

          {posts.length === 0 ? (
            <div className="rounded-[18px] border border-slate-200 bg-white p-10 text-center">
              <p className="text-sm font-semibold text-slate-500">Belum ada posting pada kategori ini.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-[3px] rounded-[14px] overflow-hidden bg-slate-200">
              {posts.map(post => {
                const mediaUrls = resolveMediaUrls(post)
                const firstMedia = mediaUrls[0]
                const youtubeId = getYoutubeId(post.media_path || firstMedia)
                
                let imageSrc = null;
                if (post.media_type === 'video_link') {
                  if (post.thumbnail_path) {
                    imageSrc = resolvePortalUrl(post.thumbnail_path)
                  } else if (youtubeId) {
                    imageSrc = `https://img.youtube.com/vi/${youtubeId}/hqdefault.jpg`
                  }
                } else {
                  imageSrc = firstMedia
                }

                return (
                  <div
                    key={post.id}
                    onClick={() => {
                      if (firstMedia) openLightbox(mediaUrls.length ? mediaUrls : [firstMedia], 0, post)
                    }}
                    className="group relative aspect-square overflow-hidden bg-slate-100 cursor-pointer"
                  >
                    {imageSrc ? (
                      <img src={imageSrc} alt={post.description || 'Dokumentasi Adiwiyata'} className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center bg-slate-200 text-xs font-bold text-slate-500">Media</div>
                    )}

                    {post.media_type === 'video_link' && (
                      <div className="absolute inset-0 flex items-center justify-center bg-black/25">
                        <span className="w-11 h-11 rounded-full bg-white/90 text-emerald-700 flex items-center justify-center text-lg font-black pl-0.5">▶</span>
                      </div>
                    )}

                    {mediaUrls.length > 1 && (
                      <div className="absolute top-2 right-2 rounded-full bg-black/60 px-2 py-0.5 text-[11px] font-black text-white">
                        {mediaUrls.length}
                      </div>
                    )}

                    <div className="absolute inset-x-0 bottom-0 translate-y-full bg-gradient-to-t from-black/75 to-transparent px-3 pb-3 pt-8 transition-transform duration-200 group-hover:translate-y-0">
                      {post.description && <p className="line-clamp-2 text-[11px] font-semibold leading-tight text-white/90">{post.description}</p>}
                      {post.created_at && <p className="mt-1 text-[10px] font-medium text-white/65">{formatDate(post.created_at)}</p>}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </div>
    </main>
  )
}
