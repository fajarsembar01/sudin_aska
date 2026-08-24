'use client'

import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import { TikTokEmbed } from 'react-social-media-embed'
import type { CmsArticle, CmsContent, CmsFile } from '@/lib/cms'

function assetUrl(path?: string | null) {
  if (!path) return null
  if (/^https?:\/\//i.test(path)) return path
  return path.startsWith('/') ? path : `/${path}`
}

function formatDate(value?: string | null) {
  if (!value) return ''
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('id-ID', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(date)
}

interface AdiwiyataHighlight {
  id: number
  school_id: number
  school_name: string
  school_logo_url?: string | null
  category: string
  description: string
  created_at?: string | null
  url: string
  media_urls?: string[] | null
  media_type?: string
  media_path?: string
  thumbnail_url?: string | null
  likes?: number
}

interface HospitalitySchool {
  school_id: number
  school_name: string
  npsn: string
  jenjang: string
  logo_url?: string | null
  review_count: number
  avg_rating: number
}

interface GuestbookPhoto {
  transaction_id: number
  school_id: number
  school_name: string
  school_jenjang: string
  guest_names: string
  guest_count: number
  purpose: string
  captured_at?: string | null
  photo_url: string
}

interface PublicServiceStats {
  aska_unique_users: number
  guestbook_unique_users: number
  updated_at?: string | null
}

const adiwiyataCategories: Record<string, string> = {
  'pengelolaan-sampah': 'Pengelolaan Sampah',
  'konservasi-energi': 'Konservasi Energi',
  'konservasi-air': 'Konservasi Air',
  'kebersihan-sanitasi-drainase': 'Kebersihan & Sanitasi',
  kompos: 'Kompos',
  tanaman: 'Tanaman',
}

const publicPortalAssetBase = (
  process.env.NEXT_PUBLIC_PORTAL_ASSET_BASE || 'https://admin.sudindikju2.com'
).replace(/\/+$/, '')

function recoverPortalImage(event: React.SyntheticEvent<HTMLImageElement>) {
  const image = event.currentTarget
  try {
    const current = new URL(image.src)
    if (['127.0.0.1', 'localhost'].includes(current.hostname) && current.pathname.startsWith('/portal/uploads/')) {
      image.src = `${publicPortalAssetBase}${current.pathname}${current.search}`
      return
    }
  } catch {
    // Hide an invalid asset and reveal the visual fallback beneath it.
  }
  image.style.display = 'none'
}

function formatAdiwiyataDate(value?: string | null) {
  if (!value) return 'Baru saja'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Baru saja'
  return new Intl.DateTimeFormat('id-ID', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(date)
}

function formatCompactNumber(value?: number | null) {
  if (typeof value !== 'number') return '—'
  return new Intl.NumberFormat('id-ID').format(value)
}

function AnimatedNumber({
  value,
  decimals = 0,
  suffix = '',
}: {
  value?: number | null
  decimals?: number
  suffix?: string
}) {
  const elementRef = useRef<HTMLSpanElement>(null)
  const frameRef = useRef<number | null>(null)
  const [displayValue, setDisplayValue] = useState(0)

  useEffect(() => {
    const element = elementRef.current
    if (!element || typeof value !== 'number') return
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    const stopAnimation = () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
      frameRef.current = null
    }

    const animate = () => {
      stopAnimation()
      if (reduceMotion) {
        setDisplayValue(value)
        return
      }
      const startedAt = performance.now()
      const duration = 1450
      const tick = (now: number) => {
        const progress = Math.min((now - startedAt) / duration, 1)
        const eased = 1 - Math.pow(1 - progress, 4)
        setDisplayValue(value * eased)
        if (progress < 1) frameRef.current = requestAnimationFrame(tick)
      }
      setDisplayValue(0)
      frameRef.current = requestAnimationFrame(tick)
    }

    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) animate()
        else {
          stopAnimation()
          setDisplayValue(0)
        }
      })
    }, { threshold: 0.55 })

    observer.observe(element)
    return () => {
      observer.disconnect()
      stopAnimation()
    }
  }, [value])

  return (
    <span ref={elementRef} className="tabular-nums" aria-label={`${formatCompactNumber(value)}${suffix}`}>
      {typeof value === 'number'
        ? new Intl.NumberFormat('id-ID', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(displayValue)
        : '—'}{suffix}
    </span>
  )
}

function htmlToText(html: string) {
  return html
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/\s+/g, ' ')
    .trim()
}

function RichText({ html, className = '' }: { html: string; className?: string }) {
  if (!html.trim()) {
    return <p className="text-base italic text-slate-400">Informasi belum tersedia.</p>
  }
  return (
    <div
      className={`cms-rich-text ${className}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

function CompactDisclosure({
  id,
  number,
  eyebrow,
  title,
  children,
}: {
  id?: string
  number: string
  eyebrow: string
  title: string
  children: React.ReactNode
}) {
  return (
    <details id={id} data-reveal="up" className="group scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white/90 shadow-sm backdrop-blur transition duration-300 hover:-translate-y-0.5 hover:border-sky-200 hover:shadow-lg hover:shadow-sky-950/5 open:border-sky-200 open:bg-white open:shadow-lg open:shadow-sky-950/5">
      <summary className="flex min-h-20 cursor-pointer list-none items-center gap-4 px-5 py-4 marker:hidden sm:px-6 [&::-webkit-details-marker]:hidden">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-sky-50 text-xs font-black text-sky-700 transition duration-300 group-open:bg-sky-700 group-open:text-white">{number}</span>
        <span className="min-w-0 flex-1">
          <span className="block text-[10px] font-extrabold uppercase tracking-[.18em] text-sky-700">{eyebrow}</span>
          <span className="mt-0.5 block text-base font-black text-slate-950 sm:whitespace-nowrap sm:text-lg">{title}</span>
        </span>
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-slate-100 text-xl font-light text-slate-600 transition duration-300 group-open:rotate-45 group-open:bg-sky-100 group-open:text-sky-800" aria-hidden="true">+</span>
      </summary>
      <div className="border-t border-slate-100 px-5 py-5 sm:px-6 sm:py-6">
        {children}
      </div>
    </details>
  )
}

function SectionHeading({
  eyebrow,
  title,
  description,
  light = false,
}: {
  eyebrow: string
  title: string
  description?: string
  light?: boolean
}) {
  return (
    <div className="mb-12 max-w-3xl" data-reveal="up">
      <div className={`mb-5 inline-flex items-center gap-3 rounded-full border px-3.5 py-2 backdrop-blur ${light ? 'border-white/10 bg-white/[.06]' : 'border-sky-200/70 bg-white/70 shadow-sm shadow-sky-900/5'}`}>
        <span className={`h-2 w-2 rounded-full ${light ? 'bg-cyan-300 shadow-[0_0_16px_rgba(103,232,249,.8)]' : 'bg-sky-500 shadow-[0_0_14px_rgba(14,165,233,.45)]'}`} />
        <p className={`text-[10px] font-extrabold uppercase tracking-[0.22em] ${light ? 'text-cyan-100' : 'text-sky-800'}`}>
          {eyebrow}
        </p>
      </div>
      <h2 className={`text-4xl font-black leading-[1.04] tracking-[-.035em] sm:text-5xl ${light ? 'text-white' : 'text-slate-950'}`}>
        {title}
      </h2>
      {description && (
        <p className={`mt-5 max-w-2xl text-base leading-8 sm:text-lg ${light ? 'text-sky-100/80' : 'text-slate-600'}`}>
          {description}
        </p>
      )}
    </div>
  )
}

function EmptyState({ children, dark = false }: { children: React.ReactNode; dark?: boolean }) {
  return (
    <div className={`group relative overflow-hidden rounded-[2rem] border px-8 py-12 text-center text-base backdrop-blur ${dark ? 'border-white/10 bg-white/[0.045] text-sky-100/65' : 'border-slate-200/80 bg-white/75 text-slate-500 shadow-[0_20px_70px_-50px_rgba(15,23,42,.35)]'}`}>
      <div className={`absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent ${dark ? 'via-cyan-300/40' : 'via-sky-400/50'} to-transparent`} />
      <span className={`mx-auto mb-4 grid h-12 w-12 place-items-center rounded-2xl text-xl transition duration-500 group-hover:-translate-y-1 group-hover:rotate-3 ${dark ? 'bg-white/[.08] text-cyan-200' : 'bg-sky-50 text-sky-700'}`} aria-hidden="true">✦</span>
      <p className="font-semibold">{children}</p>
    </div>
  )
}

function FileLinks({ files, dark = false }: { files: CmsFile[]; dark?: boolean }) {
  if (!files?.length) return null
  return (
    <div className="mt-6 flex flex-wrap gap-2">
      {files.map((file, index) => {
        const href = assetUrl(file.url)
        if (!href) return null
        return (
          <a
            key={file.id || `${file.name}-${index}`}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className={`inline-flex items-center gap-2 rounded-xl border px-3.5 py-2.5 text-xs font-bold transition ${dark ? 'border-white/15 bg-white/10 text-white hover:bg-white/15' : 'border-sky-200 bg-sky-50 text-sky-800 hover:bg-sky-100'}`}
          >
            <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M12 3v12m0 0 4-4m-4 4-4-4M5 21h14" />
            </svg>
            <span className="max-w-56 truncate">{file.name}</span>
          </a>
        )
      })}
    </div>
  )
}

function PublicationCard({ item, announcement = false, delay = 0 }: { item: CmsArticle; announcement?: boolean; delay?: number }) {
  const image = assetUrl(item.thumbnail_url)
  const excerpt = htmlToText(item.deskripsi)
  const sectionHref = announcement ? '/informasi#pengumuman' : '/informasi#artikel'

  return (
    <article data-reveal="up" style={{ '--reveal-delay': `${delay}ms` } as React.CSSProperties} className="group flex h-full flex-col overflow-hidden rounded-[2rem] border border-slate-200/80 bg-gradient-to-b from-white to-slate-50/70 shadow-[0_18px_60px_-35px_rgba(15,23,42,.35)] transition duration-500 hover:-translate-y-2 hover:border-sky-200 hover:shadow-[0_28px_75px_-30px_rgba(14,116,144,.32)]">
      <div className="relative overflow-hidden">
        {image ? (
          <img src={image} alt={item.judul} className="h-56 w-full object-cover transition duration-700 group-hover:scale-105" />
        ) : (
          <div className={`grid h-56 place-items-center ${announcement ? 'bg-gradient-to-br from-amber-50 to-orange-100 text-amber-500' : 'bg-gradient-to-br from-sky-50 to-blue-100 text-sky-500'}`}>
            <svg className="h-12 w-12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5" />
            </svg>
          </div>
        )}
        <span className={`absolute left-5 top-5 rounded-full px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-wider shadow-sm backdrop-blur ${announcement ? 'bg-amber-500 text-white' : 'bg-sky-600 text-white'}`}>
          {item.kategori}
        </span>
      </div>
      <div className="flex flex-1 flex-col p-7">
        <p className="text-xs font-semibold text-slate-400">{formatDate(item.tanggal)}</p>
        <h3 className="mt-3 text-xl font-extrabold leading-snug text-slate-950">{item.judul}</h3>
        <p className="mt-4 line-clamp-3 text-[0.95rem] leading-7 text-slate-600">
          {excerpt || 'Baca informasi selengkapnya.'}
        </p>
        <FileLinks files={item.files || []} />
        <div className="mt-auto flex items-center justify-between gap-3 pt-7">
          <span className="truncate text-xs font-semibold text-slate-400">{item.penulis}</span>
          <Link href={sectionHref} className="shrink-0 rounded-full bg-sky-50 px-4 py-2 text-xs font-extrabold text-sky-800 transition duration-300 group-hover:translate-x-1 group-hover:bg-sky-700 group-hover:text-white">
            Baca lengkap →
          </Link>
        </div>
      </div>
    </article>
  )
}

function AdiwiyataColumn({
  title,
  eyebrow,
  items,
  onOpen,
  top = false,
}: {
  title: string
  eyebrow: string
  items: AdiwiyataHighlight[]
  onOpen: (item: AdiwiyataHighlight) => void
  top?: boolean
}) {
  return (
    <div data-reveal={top ? 'left' : 'right'} className="rounded-[2.5rem] border border-emerald-900/10 bg-white/90 p-5 shadow-[0_24px_80px_-45px_rgba(6,78,59,.35)] backdrop-blur sm:p-7">
      <div className="mb-6 flex items-center justify-between gap-4 px-1">
        <div>
          <p className={`text-[11px] font-extrabold uppercase tracking-[.2em] ${top ? 'text-rose-600' : 'text-emerald-700'}`}>{eyebrow}</p>
          <h3 className="mt-1.5 text-2xl font-black text-slate-950">{title}</h3>
        </div>
        <span className={`grid h-12 w-12 place-items-center rounded-2xl text-xl ${top ? 'bg-rose-50 text-rose-600' : 'bg-emerald-100 text-emerald-700'}`} aria-hidden="true">
          {top ? '♥' : '↗'}
        </span>
      </div>

      <div className="space-y-4">
        {items.map(item => {
          const category = adiwiyataCategories[item.category] || item.category || 'Adiwiyata'
          const image = assetUrl(item.thumbnail_url || item.url)
          const logo = assetUrl(item.school_logo_url)
          const isVideo = item.media_type === 'video_link'
          return (
            <button
              type="button"
              data-adiwiyata-card={item.id}
              key={item.id}
              onClick={() => onOpen(item)}
              className="group flex h-[410px] flex-col overflow-hidden rounded-[1.6rem] border border-slate-200/80 bg-white text-left transition duration-300 hover:-translate-y-1 hover:border-emerald-300 hover:shadow-xl hover:shadow-emerald-950/10 sm:grid sm:h-52 sm:grid-cols-[170px_minmax(0,1fr)]"
            >
              <div className="relative h-44 shrink-0 overflow-hidden bg-gradient-to-br from-emerald-100 to-lime-100 sm:h-full">
                <div className="absolute inset-0 grid place-items-center bg-gradient-to-br from-emerald-700 to-teal-950 text-white" aria-hidden="true">
                  {isVideo ? (
                    <span className="grid h-16 w-16 place-items-center rounded-full border border-white/30 bg-white/15 backdrop-blur">
                      <svg className="ml-1 h-7 w-7" viewBox="0 0 24 24" fill="currentColor"><path d="m8 5 11 7-11 7V5Z" /></svg>
                    </span>
                  ) : <span className="text-4xl">🌿</span>}
                </div>
                {image ? (
                  <img src={image} alt={item.description || `Dokumentasi ${category}`} onError={recoverPortalImage} className="relative h-full w-full object-cover transition duration-700 group-hover:scale-105" />
                ) : null}
                <span className="absolute left-3 top-3 rounded-full bg-slate-950/75 px-2.5 py-1 text-[9px] font-extrabold uppercase tracking-wider text-white backdrop-blur">{category}</span>
                {isVideo && <span className="absolute bottom-3 right-3 rounded-full bg-white/90 px-2.5 py-1 text-[9px] font-black uppercase tracking-wider text-emerald-800">Video</span>}
                {top && (
                  <span className="absolute bottom-3 left-3 inline-flex items-center gap-1 rounded-full bg-white/95 px-2.5 py-1 text-[10px] font-black text-rose-600 shadow-sm">
                    ♥ {item.likes || 0}
                  </span>
                )}
              </div>
              <div className="flex min-h-0 min-w-0 flex-1 flex-col p-5">
                <div className="flex items-center gap-2.5">
                  <span className="relative grid h-8 w-8 shrink-0 place-items-center overflow-hidden rounded-full bg-emerald-700 text-xs font-black text-white">
                    <span>{(item.school_name || 'S').charAt(0).toUpperCase()}</span>
                    {logo && <img src={logo} alt="" onError={recoverPortalImage} className="absolute inset-0 h-full w-full object-cover" />}
                  </span>
                  <p className="truncate text-xs font-extrabold text-slate-700">{item.school_name || 'Sekolah Adiwiyata'}</p>
                </div>
                <p className="mt-4 line-clamp-3 text-sm font-semibold leading-6 text-slate-700">{item.description || `Dokumentasi kegiatan ${category}.`}</p>
                <div className="mt-auto flex items-center justify-between gap-3 pt-4">
                  <time className="text-[11px] font-semibold text-slate-400">{formatAdiwiyataDate(item.created_at)}</time>
                  <span className="text-xs font-extrabold text-emerald-700 transition group-hover:translate-x-1">Lihat →</span>
                </div>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function AdiwiyataModal({ item, onClose }: { item: AdiwiyataHighlight; onClose: () => void }) {
  const mediaUrl = item.media_path || item.url
  const category = adiwiyataCategories[item.category] || item.category || 'Adiwiyata'
  const isInstagram = /instagram\.com\/(?:p|reel|tv)\//i.test(mediaUrl || '')
  const isTikTok = /tiktok\.com\//i.test(mediaUrl || '')
  const youtubeId = (mediaUrl || '').match(/(?:youtube\.com\/.*[?&]v=|youtu\.be\/)([^&?/]+)/i)?.[1]
  const instagramEmbedUrl = isInstagram
    ? `${(mediaUrl || '').split('?')[0].replace(/\/+$/, '')}/embed/`
    : ''

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/90 p-3 backdrop-blur-md sm:p-6" onClick={onClose} role="dialog" aria-modal="true" aria-label={`Detail Adiwiyata ${item.school_name}`}>
      <button type="button" onClick={onClose} className="absolute right-5 top-5 z-20 grid h-11 w-11 place-items-center rounded-full border border-white/20 bg-white/10 text-white transition hover:bg-white/20" aria-label="Tutup popup">
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="m6 6 12 12M18 6 6 18" /></svg>
      </button>
      <div className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-y-auto rounded-[2rem] bg-white shadow-2xl lg:flex-row lg:overflow-hidden" onClick={event => event.stopPropagation()}>
        <div className="flex min-h-[380px] min-w-0 flex-1 items-center justify-center overflow-hidden bg-black p-3 lg:min-h-[620px]">
          {item.media_type === 'video_link' && isInstagram ? (
            <div className="adiwiyata-instagram-frame w-full max-w-[470px] overflow-hidden rounded-xl bg-white" style={{ height: 'min(720px, calc(92vh - 48px))' }}>
              <iframe src={instagramEmbedUrl} title={`Video Instagram ${item.school_name}`} className="h-full w-full border-0" scrolling="no" allow="autoplay; encrypted-media; picture-in-picture" allowFullScreen />
            </div>
          ) : item.media_type === 'video_link' && isTikTok ? (
            <div className="w-full max-w-[360px] overflow-hidden rounded-xl"><TikTokEmbed url={mediaUrl} width="100%" /></div>
          ) : item.media_type === 'video_link' && youtubeId ? (
            <iframe className="aspect-video w-full" src={`https://www.youtube.com/embed/${youtubeId}`} allowFullScreen title="Video Adiwiyata" />
          ) : item.media_type === 'video_link' ? (
            <a href={mediaUrl} target="_blank" rel="noopener noreferrer" className="rounded-full bg-emerald-600 px-6 py-3 font-bold text-white">Buka video ↗</a>
          ) : (
            <img src={item.url} alt={item.description || `Dokumentasi ${category}`} onError={recoverPortalImage} className="max-h-[82vh] max-w-full object-contain" />
          )}
        </div>
        <aside className="w-full shrink-0 overflow-y-auto p-7 sm:p-9 lg:w-[390px]">
          <p className="text-[11px] font-extrabold uppercase tracking-[.2em] text-emerald-700">{category}</p>
          <h3 className="mt-3 text-2xl font-black leading-tight text-slate-950">{item.school_name}</h3>
          <div className="mt-4 flex items-center gap-3 text-xs font-bold text-slate-400">
            <span>{formatAdiwiyataDate(item.created_at)}</span>
            {(item.likes || 0) > 0 && <span className="rounded-full bg-rose-50 px-2.5 py-1 text-rose-600">♥ {item.likes} suka</span>}
          </div>
          <p className="mt-7 whitespace-pre-wrap text-sm leading-7 text-slate-600">{item.description || 'Tidak ada deskripsi.'}</p>
          <Link href={`/profil-sekolah?school_id=${item.school_id}&category=${encodeURIComponent(item.category)}`} className="mt-8 inline-flex items-center gap-2 text-sm font-extrabold text-emerald-700">
            Lihat profil Adiwiyata sekolah →
          </Link>
        </aside>
      </div>
    </div>
  )
}

function HospitalityRanking({ schools }: { schools: HospitalitySchool[] }) {
  const podium = schools.slice(0, 3)
  const remaining = schools.slice(3, 11)
  const rankStyles = [
    'from-amber-300 via-yellow-400 to-orange-500 text-amber-950',
    'from-slate-200 via-slate-300 to-slate-400 text-slate-800',
    'from-orange-300 via-amber-600 to-orange-700 text-white',
  ]

  const SchoolLogo = ({ school, large = false }: { school: HospitalitySchool; large?: boolean }) => {
    const logo = assetUrl(school.logo_url)
    return (
      <span className={`relative grid shrink-0 place-items-center overflow-hidden rounded-2xl border border-white/15 bg-white/10 font-black text-white ${large ? 'h-16 w-16 text-xl' : 'h-11 w-11 text-sm'}`}>
        {(school.school_name || 'S').charAt(0).toUpperCase()}
        {logo && <img src={logo} alt="" onError={recoverPortalImage} className="absolute inset-0 h-full w-full bg-white object-cover" />}
      </span>
    )
  }

  return (
    <div>
      <div className="grid gap-5 lg:grid-cols-3">
        {podium.map((school, index) => (
          <article key={school.school_id} data-reveal="up" style={{ '--reveal-delay': `${index * 100}ms` } as React.CSSProperties} className={`relative overflow-hidden rounded-[2rem] border p-7 backdrop-blur transition duration-500 hover:-translate-y-2 ${index === 0 ? 'border-amber-300/40 bg-amber-300/[.09] shadow-2xl shadow-amber-950/20' : 'border-white/10 bg-white/[.06]'}`}>
            <div className="absolute -right-12 -top-12 h-36 w-36 rounded-full bg-violet-400/10 blur-2xl" />
            <div className="relative flex items-start justify-between gap-4">
              <SchoolLogo school={school} large />
              <span className={`grid h-11 w-11 place-items-center rounded-2xl bg-gradient-to-br text-sm font-black shadow-lg ${rankStyles[index]}`}>#{index + 1}</span>
            </div>
            <p className="mt-7 text-[10px] font-extrabold uppercase tracking-[.2em] text-violet-300">{school.jenjang} · NPSN {school.npsn}</p>
            <h3 className="mt-2 min-h-14 text-xl font-black leading-snug text-white">{school.school_name}</h3>
            <div className="mt-6 flex items-end justify-between gap-4 border-t border-white/10 pt-5">
              <div><p className="text-3xl font-black text-white"><AnimatedNumber value={Number(school.avg_rating)} decimals={2} /></p><p className="mt-1 text-xs tracking-[.12em] text-amber-300" aria-label={`${school.avg_rating} dari 5 bintang`}>★★★★★</p></div>
              <div className="text-right"><p className="text-base font-black text-violet-100"><AnimatedNumber value={school.review_count} /></p><p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Review</p></div>
            </div>
          </article>
        ))}
      </div>

      {remaining.length > 0 && (
        <div className="mt-6 grid gap-3 lg:grid-cols-2">
          {remaining.map((school, index) => (
            <article key={school.school_id} data-reveal="up" style={{ '--reveal-delay': `${Math.min(index, 5) * 70}ms` } as React.CSSProperties} className="group flex items-center gap-4 rounded-2xl border border-white/10 bg-white/[.05] p-4 transition duration-300 hover:border-violet-300/30 hover:bg-white/[.09]">
              <span className="w-8 shrink-0 text-center text-lg font-black text-violet-300">{index + 4}</span>
              <SchoolLogo school={school} />
              <div className="min-w-0 flex-1"><h3 className="truncate text-sm font-extrabold text-white">{school.school_name}</h3><p className="mt-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">{school.jenjang} · <AnimatedNumber value={school.review_count} /> review</p></div>
              <div className="shrink-0 text-right"><p className="text-lg font-black text-amber-300"><AnimatedNumber value={Number(school.avg_rating)} decimals={2} /></p><p className="text-[9px] tracking-wider text-amber-300/70">★★★★★</p></div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

function GuestbookPhotoRow({
  title,
  subtitle,
  photos,
  onOpen,
}: {
  title: string
  subtitle: string
  photos: GuestbookPhoto[]
  onOpen: (photo: GuestbookPhoto) => void
}) {
  const loopItems = [...photos, ...photos]
  return (
    <div data-reveal="up" className="mt-10">
      <div className="mx-auto mb-4 flex max-w-7xl items-end justify-between gap-4 px-4 sm:px-6">
        <div><p className="text-xs font-extrabold uppercase tracking-[.2em] text-violet-700">{subtitle}</p><h3 className="mt-1 text-2xl font-black text-slate-950">{title}</h3></div>
        <span className="text-xs font-bold text-slate-400">{photos.length} dokumentasi</span>
      </div>
      <div className="guestbook-marquee overflow-hidden">
        <div className="guestbook-marquee-track flex w-max gap-4 px-2">
          {loopItems.map((photo, index) => (
            <button key={`${photo.transaction_id}-${index}`} type="button" onClick={() => onOpen(photo)} className="group relative h-56 w-72 shrink-0 overflow-hidden rounded-[1.6rem] bg-slate-200 text-left shadow-lg shadow-slate-900/10 sm:w-80">
              <img src={photo.photo_url} alt={`Kunjungan ${photo.guest_names} ke ${photo.school_name}`} onError={recoverPortalImage} className="h-full w-full object-cover transition duration-700 group-hover:scale-105" />
              <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/15 to-transparent" />
              <span className="absolute left-4 top-4 rounded-full bg-white/90 px-3 py-1 text-[9px] font-extrabold uppercase tracking-wider text-violet-800 backdrop-blur">{photo.school_jenjang || 'Sekolah'}</span>
              <div className="absolute inset-x-0 bottom-0 p-5 text-white">
                <p className="truncate text-xs font-bold text-violet-200">{photo.guest_names}</p>
                <h4 className="mt-1 truncate text-base font-black">{photo.school_name}</h4>
                <p className="mt-1 truncate text-[11px] text-white/65">{photo.purpose}</p>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function GuestbookPhotoModal({ photo, onClose }: { photo: GuestbookPhoto; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-slate-950/90 p-3 backdrop-blur-md sm:p-6" role="dialog" aria-modal="true" aria-label={`Foto kunjungan ke ${photo.school_name}`} onClick={onClose}>
      <button type="button" onClick={onClose} className="absolute right-5 top-5 z-20 grid h-11 w-11 place-items-center rounded-full border border-white/20 bg-white/10 text-white transition hover:bg-white/20" aria-label="Tutup foto">
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="m6 6 12 12M18 6 6 18" /></svg>
      </button>
      <div className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-[2rem] bg-white shadow-2xl lg:flex-row" onClick={event => event.stopPropagation()}>
        <div className="flex min-h-[48vh] flex-1 items-center justify-center bg-black"><img src={photo.photo_url} alt={`Dokumentasi kunjungan ${photo.guest_names}`} onError={recoverPortalImage} className="max-h-[88vh] max-w-full object-contain" /></div>
        <aside className="w-full shrink-0 overflow-y-auto p-7 sm:p-9 lg:w-[380px]">
          <p className="text-[11px] font-extrabold uppercase tracking-[.2em] text-violet-700">Dokumentasi Buku Tamu</p>
          <h3 className="mt-3 text-2xl font-black leading-tight text-slate-950">{photo.school_name}</h3>
          <p className="mt-2 text-xs font-bold text-slate-400">{photo.school_jenjang} · {formatAdiwiyataDate(photo.captured_at)}</p>
          <div className="mt-7 space-y-5 border-t border-slate-200 pt-6">
            <div><p className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">Staff yang berkunjung</p><p className="mt-1 font-bold text-slate-800">{photo.guest_names}</p></div>
            <div><p className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">Tujuan kunjungan</p><p className="mt-1 text-sm leading-6 text-slate-600">{photo.purpose}</p></div>
            <div><p className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">Jumlah tamu</p><p className="mt-1 font-bold text-slate-800">{photo.guest_count} orang</p></div>
          </div>
        </aside>
      </div>
    </div>
  )
}

const sectionNavigationLinks = [
  ['#tentang', 'Profil'],
  ['#informasi-publik', 'Informasi Publik'],
  ['#adiwiyata-highlight', 'Adiwiyata'],
  ['#hospitality', 'Hospitality'],
  ['#kunjungan-staff', 'Buku Tamu'],
  ['#layanan', 'Layanan'],
  ['#pengumuman', 'Pengumuman'],
  ['#artikel', 'Artikel'],
  ['#galeri', 'Galeri'],
] as const

function SectionNavigation() {
  const [activeSection, setActiveSection] = useState<string>('#tentang')
  const [progress, setProgress] = useState(0)
  const navigationRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let ticking = false
    const updateNavigation = () => {
      const scrollTop = window.scrollY
      const scrollable = document.documentElement.scrollHeight - window.innerHeight
      setProgress(scrollable > 0 ? Math.min(100, Math.max(0, (scrollTop / scrollable) * 100)) : 0)

      let current: string = sectionNavigationLinks[0][0]
      for (const [href] of sectionNavigationLinks) {
        const section = document.getElementById(href.slice(1))
        if (section && section.getBoundingClientRect().top <= 150) current = href
      }
      setActiveSection(current)
      ticking = false
    }
    const onScroll = () => {
      if (!ticking) {
        ticking = true
        requestAnimationFrame(updateNavigation)
      }
    }
    updateNavigation()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [])

  useEffect(() => {
    const container = navigationRef.current
    const activeLink = container?.querySelector<HTMLElement>(`[data-nav-section="${activeSection}"]`)
    if (!container || !activeLink) return
    const targetLeft = activeLink.offsetLeft - (container.clientWidth - activeLink.offsetWidth) / 2
    container.scrollTo({ left: Math.max(0, targetLeft), behavior: 'smooth' })
  }, [activeSection])

  return (
    <nav className="sticky top-0 z-40 border-y border-slate-200/70 bg-white/85 shadow-[0_10px_35px_-25px_rgba(15,23,42,.45)] backdrop-blur-2xl" aria-label="Navigasi konten">
      <span className="absolute inset-x-0 bottom-0 h-[2px] bg-slate-100" aria-hidden="true"><span className="block h-full bg-gradient-to-r from-sky-500 via-cyan-400 to-emerald-400 transition-[width] duration-150" style={{ width: `${progress}%` }} /></span>
      <div ref={navigationRef} className="landing-nav-scroll mx-auto flex max-w-7xl items-center gap-1 overflow-x-auto px-4 py-2.5 sm:px-6">
        <a href="#beranda" className="mr-2 grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-slate-950 text-white shadow-lg shadow-slate-950/15 transition duration-300 hover:-translate-y-0.5 hover:bg-sky-700" aria-label="Kembali ke atas">
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true"><path d="m18 15-6-6-6 6" /></svg>
        </a>
        {sectionNavigationLinks.map(([href, label]) => (
          <a key={href} href={href} data-nav-section={href} aria-current={activeSection === href ? 'location' : undefined} className={`shrink-0 rounded-xl px-4 py-2.5 text-xs font-extrabold transition duration-300 ${activeSection === href ? 'bg-sky-50 text-sky-800 shadow-inner ring-1 ring-sky-100' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-950'}`}>
            {label}
          </a>
        ))}
      </div>
    </nav>
  )
}

export default function LandingCmsSections({ content, loading }: { content: CmsContent | null; loading: boolean }) {
  const sectionRootRef = useRef<HTMLDivElement>(null)
  const [adiwiyata, setAdiwiyata] = useState<{ top: AdiwiyataHighlight[]; newest: AdiwiyataHighlight[] }>({ top: [], newest: [] })
  const [adiwiyataLoading, setAdiwiyataLoading] = useState(true)
  const [activeAdiwiyata, setActiveAdiwiyata] = useState<AdiwiyataHighlight | null>(null)
  const [hospitalitySchools, setHospitalitySchools] = useState<HospitalitySchool[]>([])
  const [hospitalityLoading, setHospitalityLoading] = useState(true)
  const [guestbookPhotos, setGuestbookPhotos] = useState<{ random: GuestbookPhoto[]; newest: GuestbookPhoto[] }>({ random: [], newest: [] })
  const [guestbookLoading, setGuestbookLoading] = useState(true)
  const [activeGuestbookPhoto, setActiveGuestbookPhoto] = useState<GuestbookPhoto | null>(null)
  const [serviceStats, setServiceStats] = useState<PublicServiceStats | null>(null)

  useEffect(() => {
    if (!activeAdiwiyata && !activeGuestbookPhoto) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setActiveAdiwiyata(null)
        setActiveGuestbookPhoto(null)
      }
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [activeAdiwiyata, activeGuestbookPhoto])

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/adiwiyata-highlights', { cache: 'no-store', signal: controller.signal })
      .then(response => response.ok ? response.json() : Promise.reject(new Error('Adiwiyata unavailable')))
      .then(payload => {
        if (payload?.success && payload?.data) {
          setAdiwiyata({
            top: Array.isArray(payload.data.top) ? payload.data.top : [],
            newest: Array.isArray(payload.data.newest) ? payload.data.newest : [],
          })
        }
      })
      .catch(error => {
        if (error.name !== 'AbortError') setAdiwiyata({ top: [], newest: [] })
      })
      .finally(() => {
        if (!controller.signal.aborted) setAdiwiyataLoading(false)
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/guestbook-photos', { cache: 'no-store', signal: controller.signal })
      .then(response => response.ok ? response.json() : Promise.reject(new Error('Guestbook gallery unavailable')))
      .then(payload => {
        const data = payload?.success ? payload.data : null
        setGuestbookPhotos({
          random: Array.isArray(data?.random) ? data.random : [],
          newest: Array.isArray(data?.newest) ? data.newest : [],
        })
      })
      .catch(error => {
        if (error.name !== 'AbortError') setGuestbookPhotos({ random: [], newest: [] })
      })
      .finally(() => {
        if (!controller.signal.aborted) setGuestbookLoading(false)
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/hospitality-top-schools', { cache: 'no-store', signal: controller.signal })
      .then(response => response.ok ? response.json() : Promise.reject(new Error('Hospitality unavailable')))
      .then(payload => setHospitalitySchools(payload?.success && Array.isArray(payload.data) ? payload.data : []))
      .catch(error => {
        if (error.name !== 'AbortError') setHospitalitySchools([])
      })
      .finally(() => {
        if (!controller.signal.aborted) setHospitalityLoading(false)
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/public-service-stats', { cache: 'no-store', signal: controller.signal })
      .then(response => response.ok ? response.json() : Promise.reject(new Error('Service stats unavailable')))
      .then(payload => setServiceStats(payload?.success && payload.data ? payload.data : null))
      .catch(error => {
        if (error.name !== 'AbortError') setServiceStats(null)
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (loading || !content || !sectionRootRef.current) return
    const elements = sectionRootRef.current.querySelectorAll<HTMLElement>('[data-reveal]')
    let lastScrollY = window.scrollY
    let scrollDirection: 'up' | 'down' = 'down'

    const handleScroll = () => {
      const currentScrollY = window.scrollY
      if (Math.abs(currentScrollY - lastScrollY) > 4) {
        scrollDirection = currentScrollY < lastScrollY ? 'up' : 'down'
        lastScrollY = currentScrollY
      }
    }

    window.addEventListener('scroll', handleScroll, { passive: true })
    const observer = new IntersectionObserver(
      entries => {
        entries.forEach(entry => {
          const element = entry.target as HTMLElement
          if (entry.isIntersecting) {
            element.classList.toggle('reveal-from-top', scrollDirection === 'up')
            requestAnimationFrame(() => element.classList.add('is-revealed'))
          } else {
            element.classList.remove('is-revealed')
          }
        })
      },
      { threshold: 0.08, rootMargin: '-3% 0px -6% 0px' }
    )
    elements.forEach(element => observer.observe(element))
    return () => {
      observer.disconnect()
      window.removeEventListener('scroll', handleScroll)
    }
  }, [adiwiyataLoading, content, guestbookLoading, hospitalityLoading, loading])

  if (loading) {
    return (
      <section id="tentang" className="bg-white px-4 py-28 sm:px-6">
        <div className="mx-auto max-w-7xl animate-pulse">
          <div className="mb-8 h-5 w-36 rounded-full bg-sky-100" />
          <div className="mb-12 h-12 max-w-xl rounded-2xl bg-slate-200" />
          <div className="grid gap-6 lg:grid-cols-3">
            {[0, 1, 2].map(item => <div key={item} className="h-72 rounded-[2rem] bg-slate-100" />)}
          </div>
        </div>
      </section>
    )
  }

  if (!content) {
    return (
      <section id="tentang" className="bg-white px-4 py-28 sm:px-6">
        <div className="mx-auto max-w-7xl"><EmptyState>Konten CMS belum dapat dimuat. Silakan coba kembali beberapa saat lagi.</EmptyState></div>
      </section>
    )
  }

  const profile = content.profil
  const structure = assetUrl(profile.struktur_organisasi_url)
  const askaService = content.layanan.find(service => service.nama.trim().toLowerCase() === 'aska')
  const guestbookService = content.layanan.find(service => service.nama.trim().toLowerCase().includes('buku tamu'))
  const featuredServiceIds = new Set([askaService?.id, guestbookService?.id].filter((id): id is number => typeof id === 'number'))
  const otherServices = content.layanan.filter(service => !featuredServiceIds.has(service.id))

  return (
    <div ref={sectionRootRef} className="contents">
      <SectionNavigation />
      {activeAdiwiyata && <AdiwiyataModal item={activeAdiwiyata} onClose={() => setActiveAdiwiyata(null)} />}
      {activeGuestbookPhoto && <GuestbookPhotoModal photo={activeGuestbookPhoto} onClose={() => setActiveGuestbookPhoto(null)} />}

      <section id="tentang" className="section-texture scroll-mt-16 overflow-hidden bg-gradient-to-br from-white via-sky-50/45 to-slate-50 px-4 py-14 sm:px-6 sm:py-16">
        <div className="relative mx-auto max-w-7xl">
          <div className="ambient-pulse absolute -right-64 -top-48 h-[520px] w-[520px] rounded-full bg-sky-200/50 blur-3xl" />
          <div className="relative grid gap-8 lg:grid-cols-[.72fr_1.28fr] lg:items-start">
            <div className="lg:sticky lg:top-28">
              <div className="mb-4 flex items-center gap-3">
                <span className="h-px w-9 bg-sky-500" />
                <p className="text-xs font-extrabold uppercase tracking-[.22em] text-sky-700">Profil & Pelayanan</p>
              </div>
              <h2 className="max-w-md text-3xl font-black leading-tight tracking-tight text-slate-950 sm:text-4xl">Kenali kami secara ringkas.</h2>
              <p className="mt-3 max-w-md text-sm leading-6 text-slate-600 sm:text-base">Pilih informasi yang ingin dibaca. Seluruh detail disembunyikan secara default agar akses menuju Adiwiyata lebih cepat.</p>
            </div>

            <div className="grid items-start gap-3 sm:grid-cols-2">
              <CompactDisclosure number="01" eyebrow="Sekilas Instansi" title="Sudin Pendidikan JU II">
                <RichText html={profile.deskripsi_utama} className="cms-rich-text-readable text-slate-700" />
              </CompactDisclosure>
              <CompactDisclosure number="02" eyebrow="Semangat Pelayanan" title="Motto Pelayanan">
                <RichText html={profile.motto_pelayanan} className="cms-rich-text-readable text-slate-700" />
              </CompactDisclosure>
              <CompactDisclosure number="03" eyebrow="Arah Utama" title="Visi">
                <RichText html={profile.visi} className="cms-rich-text-readable text-slate-700" />
              </CompactDisclosure>
              <CompactDisclosure number="04" eyebrow="Langkah Strategis" title="Misi">
                <RichText html={profile.misi} className="cms-rich-text-readable text-slate-700" />
              </CompactDisclosure>
              <CompactDisclosure number="05" eyebrow="Peran & Tanggung Jawab" title="Tugas dan Fungsi">
                <RichText html={profile.tugas_fungsi} className="cms-rich-text-readable text-slate-700" />
              </CompactDisclosure>
              {structure && (
                <CompactDisclosure number="06" eyebrow="Organisasi" title="Struktur Organisasi">
                  <a href={structure} target="_blank" rel="noopener noreferrer"><img src={structure} alt="Struktur Organisasi" className="mx-auto max-h-[560px] w-auto rounded-xl bg-slate-50 object-contain" /></a>
                  <Link href="/profil" className="mt-4 inline-flex text-sm font-extrabold text-sky-700">Buka profil lengkap →</Link>
                </CompactDisclosure>
              )}
              <CompactDisclosure id="informasi-publik" number={structure ? '07' : '06'} eyebrow="Komitmen Mutu" title="Jaminan Pelayanan">
                <RichText html={content.informasi_publik.jaminan_pelayanan} className="cms-rich-text-readable text-slate-700" />
              </CompactDisclosure>
              <CompactDisclosure number={structure ? '08' : '07'} eyebrow="Perlindungan" title="Keamanan & Keselamatan">
                <RichText html={content.informasi_publik.keamanan_keselamatan} className="cms-rich-text-readable text-slate-700" />
              </CompactDisclosure>
              <div className={structure ? 'sm:col-span-2' : ''}>
                <CompactDisclosure number={structure ? '09' : '08'} eyebrow="Tanggung Jawab" title="Kompensasi Pelayanan">
                  <RichText html={content.informasi_publik.kompensasi_pelayanan} className="cms-rich-text-readable text-slate-700" />
                </CompactDisclosure>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="adiwiyata-highlight" className="section-texture scroll-mt-16 overflow-hidden bg-gradient-to-br from-emerald-50 via-white to-lime-100/60 px-4 py-24 sm:px-6 sm:py-28">
        <div className="relative mx-auto max-w-7xl">
          <div className="ambient-pulse absolute -right-52 -top-56 h-[460px] w-[460px] rounded-full bg-lime-300/45 blur-3xl" />
          <div className="relative">
            <div className="mb-12 flex flex-col justify-between gap-7 lg:flex-row lg:items-end">
              <SectionHeading eyebrow="Sekolah Berbudaya Lingkungan" title="Inspirasi hijau dari sekolah kita." description="Karya dan aksi nyata warga sekolah dalam merawat lingkungan secara berkelanjutan." />
              <Link href="/adiwiyata" data-reveal="right" className="group inline-flex w-fit shrink-0 items-center gap-3 rounded-full bg-emerald-700 px-6 py-3.5 text-sm font-extrabold text-white shadow-lg shadow-emerald-800/20 transition duration-300 hover:-translate-y-1 hover:bg-emerald-800 hover:shadow-xl">
                Lihat semua Adiwiyata
                <svg className="h-4 w-4 transition group-hover:translate-x-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg>
              </Link>
            </div>

            {adiwiyataLoading ? (
              <div className="grid animate-pulse gap-7 lg:grid-cols-2">
                {[0, 1].map(column => <div key={column} className="h-[560px] rounded-[2.5rem] bg-emerald-100/70" />)}
              </div>
            ) : (adiwiyata.top.length || adiwiyata.newest.length) ? (
              <div className="grid gap-7 lg:grid-cols-2">
                <AdiwiyataColumn title="Paling Disukai" eyebrow="Top Like" items={adiwiyata.top} onOpen={setActiveAdiwiyata} top />
                <AdiwiyataColumn title="Postingan Terbaru" eyebrow="Terbaru" items={adiwiyata.newest} onOpen={setActiveAdiwiyata} />
              </div>
            ) : (
              <EmptyState>Belum ada dokumentasi Adiwiyata yang dapat ditampilkan.</EmptyState>
            )}
          </div>
        </div>
      </section>

      <section id="hospitality" className="section-texture section-texture-dark scroll-mt-16 overflow-hidden bg-gradient-to-br from-[#19102d] via-[#151126] to-[#090b1c] px-4 py-24 text-white sm:px-6 sm:py-28">
        <div className="relative mx-auto max-w-7xl">
          <div className="ambient-pulse absolute -left-60 -top-48 h-[520px] w-[520px] rounded-full bg-violet-600/25 blur-3xl" />
          <div className="absolute -bottom-56 -right-48 h-[500px] w-[500px] rounded-full bg-amber-400/10 blur-3xl" />
          <div className="relative">
            <div className="mb-12 flex flex-col justify-between gap-7 lg:flex-row lg:items-end">
              <SectionHeading eyebrow="Hospitality Sekolah" title="Pelayanan terbaik, dinilai langsung oleh pengunjung." description="Peringkat sekolah dengan nilai penilaian umum tertinggi dan minimal 300 review pelayanan yang telah selesai." light />
              <div data-reveal="right" className="inline-flex w-fit shrink-0 items-center gap-3 rounded-full border border-violet-300/20 bg-white/[.07] px-5 py-3 text-xs font-extrabold text-violet-100 backdrop-blur">
                <span className="grid h-8 w-8 place-items-center rounded-full bg-amber-300 font-black text-amber-950">300+</span>
                Minimum review selesai
              </div>
            </div>
            {hospitalityLoading ? (
              <div className="grid animate-pulse gap-5 lg:grid-cols-3">{[0, 1, 2].map(item => <div key={item} className="h-72 rounded-[2rem] bg-white/[.06]" />)}</div>
            ) : hospitalitySchools.length ? (
              <HospitalityRanking schools={hospitalitySchools} />
            ) : (
              <EmptyState dark>Data peringkat Hospitality belum dapat ditampilkan.</EmptyState>
            )}
          </div>
        </div>
      </section>

      <section id="kunjungan-staff" className="section-texture scroll-mt-16 overflow-hidden bg-gradient-to-br from-violet-50 via-white to-sky-50 py-24 sm:py-28">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <SectionHeading eyebrow="Dokumentasi Buku Tamu" title="Jejak kunjungan staff ke sekolah." description="Dokumentasi kunjungan yang telah disetujui dari Buku Tamu digital Suku Dinas Pendidikan Jakarta Utara Wilayah II." />
        </div>
        {guestbookLoading ? (
          <div className="mx-auto grid max-w-7xl animate-pulse gap-5 px-4 sm:grid-cols-2 sm:px-6 lg:grid-cols-4">{[0, 1, 2, 3].map(item => <div key={item} className="h-56 rounded-[1.6rem] bg-violet-100" />)}</div>
        ) : (guestbookPhotos.random.length || guestbookPhotos.newest.length) ? (
          <>
            <GuestbookPhotoRow title="Kunjungan Pilihan" subtitle="Foto Acak" photos={guestbookPhotos.random} onOpen={setActiveGuestbookPhoto} />
            <GuestbookPhotoRow title="Kunjungan Terkini" subtitle="Foto Terbaru" photos={guestbookPhotos.newest} onOpen={setActiveGuestbookPhoto} />
          </>
        ) : (
          <div className="mx-auto max-w-7xl px-4 sm:px-6"><EmptyState>Belum ada foto kunjungan staff yang dapat ditampilkan.</EmptyState></div>
        )}
      </section>

      <section id="layanan" className="section-texture section-texture-dark scroll-mt-16 overflow-hidden bg-gradient-to-br from-[#050816] via-slate-950 to-[#101843] px-4 py-24 sm:px-6 sm:py-28">
        <div className="relative mx-auto max-w-7xl">
          <div className="ambient-pulse absolute -left-60 -top-40 h-[500px] w-[500px] rounded-full bg-blue-600/25 blur-3xl" />
          <div className="relative">
            <SectionHeading eyebrow="Untuk Masyarakat" title="Layanan publik dalam satu akses." description="Gunakan layanan digital kami dan temukan informasi serta dokumen pelayanan yang dibutuhkan." light />

            {(askaService || guestbookService) && <div className="mb-12 grid gap-6 lg:grid-cols-2">
              {askaService && <article data-reveal="left" className="group relative overflow-hidden rounded-[2.25rem] border border-cyan-300/20 bg-gradient-to-br from-sky-600 via-blue-700 to-indigo-900 p-7 text-white shadow-2xl shadow-blue-950/25 sm:p-9">
                <div className="absolute -right-14 -top-14 h-48 w-48 rounded-full border-[30px] border-white/[.05] transition duration-700 group-hover:scale-110" />
                <div className="relative flex h-full flex-col">
                  <div className="flex items-start justify-between gap-5">
                    <span className="grid h-14 w-14 place-items-center rounded-2xl bg-cyan-300 text-2xl text-slate-950"><i className={`bi ${askaService.icon || 'bi-robot'}`} aria-hidden="true" /></span>
                    <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[.16em] text-cyan-100">Asisten Digital</span>
                  </div>
                  <p className="mt-9 text-xs font-extrabold uppercase tracking-[.2em] text-cyan-200">{askaService.nama}</p>
                  <h3 className="mt-2 text-3xl font-black">Tanya layanan pendidikan kapan saja.</h3>
                  <RichText html={askaService.deskripsi} className="cms-rich-text-readable cms-rich-text-dark mt-4 max-w-xl text-sm leading-7 text-sky-100/80" />
                  <FileLinks files={askaService.files} dark />
                  <div className="mt-8 flex flex-wrap items-end justify-between gap-5 border-t border-white/10 pt-6">
                    <div><strong className="block text-4xl font-black tabular-nums text-white"><AnimatedNumber value={serviceStats?.aska_unique_users} /></strong><span className="mt-1 block text-xs font-bold text-cyan-200">pengguna unik</span></div>
                    <a href="https://aska.sudindikju2.com" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-3 text-xs font-extrabold text-blue-800 transition hover:-translate-y-1 hover:bg-cyan-100">Buka ASKA <span aria-hidden="true">↗</span></a>
                  </div>
                </div>
              </article>}

              {guestbookService && <article data-reveal="right" className="group relative overflow-hidden rounded-[2.25rem] border border-violet-300/20 bg-gradient-to-br from-violet-700 via-purple-800 to-slate-950 p-7 text-white shadow-2xl shadow-violet-950/25 sm:p-9">
                <div className="absolute -bottom-16 -right-12 h-52 w-52 rounded-full bg-fuchsia-400/10 blur-2xl transition duration-700 group-hover:scale-125" />
                <div className="relative flex h-full flex-col">
                  <div className="flex items-start justify-between gap-5">
                    <span className="grid h-14 w-14 place-items-center rounded-2xl bg-violet-200 text-2xl text-violet-950"><i className={`bi ${guestbookService.icon || 'bi-journal-check'}`} aria-hidden="true" /></span>
                    <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[.16em] text-violet-100">Layanan Sekolah</span>
                  </div>
                  <p className="mt-9 text-xs font-extrabold uppercase tracking-[.2em] text-violet-200">{guestbookService.nama}</p>
                  <h3 className="mt-2 text-3xl font-black">Kunjungan sekolah tercatat lebih mudah.</h3>
                  <RichText html={guestbookService.deskripsi} className="cms-rich-text-readable cms-rich-text-dark mt-4 max-w-xl text-sm leading-7 text-violet-100/75" />
                  <FileLinks files={guestbookService.files} dark />
                  <div className="mt-8 flex flex-wrap items-end justify-between gap-5 border-t border-white/10 pt-6">
                    <div><strong className="block text-4xl font-black tabular-nums text-white"><AnimatedNumber value={serviceStats?.guestbook_unique_users} /></strong><span className="mt-1 block text-xs font-bold text-violet-200">pengguna unik</span></div>
                    <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-5 py-3 text-xs font-extrabold text-white">Akses melalui QR sekolah</span>
                  </div>
                </div>
              </article>}
            </div>}

            {otherServices.length ? (
              <div className="grid gap-7 border-t border-white/10 pt-12 md:grid-cols-2 xl:grid-cols-3">
                {otherServices.map((service, index) => (
                  <article key={service.id} data-reveal="up" style={{ '--reveal-delay': `${Math.min(index, 5) * 90}ms` } as React.CSSProperties} className="group rounded-[2rem] border border-white/10 bg-white/[0.07] p-8 text-white backdrop-blur transition duration-500 hover:-translate-y-2 hover:border-cyan-300/30 hover:bg-white/[0.1]">
                    <div className="mb-8 flex items-center justify-between"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-cyan-300 text-xl text-slate-950 transition duration-500 group-hover:rotate-6 group-hover:scale-110"><i className={`bi ${service.icon || 'bi-star'}`} aria-hidden="true" /></span><span className="text-4xl font-black text-white/5">{String(index + 1).padStart(2, '0')}</span></div>
                    <h3 className="mb-4 text-2xl font-black">{service.nama}</h3>
                    <RichText html={service.deskripsi} className="cms-rich-text-readable cms-rich-text-dark text-slate-200" />
                    <FileLinks files={service.files} dark />
                  </article>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </section>

      <section id="pengumuman" className="section-texture scroll-mt-16 overflow-hidden bg-gradient-to-br from-[#fffaf0] via-white to-amber-50 px-4 py-24 sm:px-6 sm:py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Pemberitahuan Resmi" title="Pengumuman terbaru." description="Informasi resmi untuk masyarakat dan satuan pendidikan." />
          {content.pengumuman.length ? <div className="grid gap-7 md:grid-cols-2 xl:grid-cols-3">{content.pengumuman.map((item, index) => <PublicationCard key={item.id} item={item} announcement delay={Math.min(index, 5) * 90} />)}</div> : <EmptyState>Belum ada pengumuman yang dipublikasikan.</EmptyState>}
        </div>
      </section>

      <section id="artikel" className="section-texture scroll-mt-16 overflow-hidden bg-gradient-to-b from-slate-50 to-white px-4 py-24 sm:px-6 sm:py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Kabar Pendidikan" title="Cerita, kegiatan, dan informasi terkini." description="Ikuti perkembangan pendidikan di Jakarta Utara Wilayah II." />
          {content.artikel.length ? <div className="grid gap-7 md:grid-cols-2 xl:grid-cols-3">{content.artikel.map((item, index) => <PublicationCard key={item.id} item={item} delay={Math.min(index, 5) * 90} />)}</div> : <EmptyState>Belum ada artikel yang dipublikasikan.</EmptyState>}
        </div>
      </section>

      <section id="galeri" className="section-texture section-texture-dark scroll-mt-16 overflow-hidden bg-gradient-to-br from-slate-950 via-[#101a32] to-blue-950 px-4 py-24 text-white sm:px-6 sm:py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Dokumentasi" title="Momen yang menggerakkan pendidikan." description="Rekam jejak kegiatan dan kolaborasi pendidikan di Jakarta Utara Wilayah II." light />
          {content.galeri.length ? (
            <div className="grid gap-7 sm:grid-cols-2 xl:grid-cols-3">
              {content.galeri.map(gallery => {
                const cover = assetUrl(gallery.thumbnail_url || gallery.gambar_kegiatan[0]?.url)
                return (
                  <article key={gallery.id} data-reveal="up" className="group overflow-hidden rounded-[2rem] border border-white/10 bg-white/[0.06] transition duration-500 hover:-translate-y-2 hover:border-cyan-300/30">
                    {cover ? <a href={cover} target="_blank" rel="noopener noreferrer"><img src={cover} alt={gallery.nama_kegiatan} className="h-72 w-full object-cover transition duration-700 group-hover:scale-105" /></a> : <div className="grid h-64 place-items-center bg-white/5 text-white/30">Belum ada foto</div>}
                    <div className="p-7"><p className="text-xs font-bold uppercase tracking-wider text-cyan-300">{formatDate(gallery.tanggal)}</p><h3 className="mt-3 text-2xl font-black leading-snug">{gallery.nama_kegiatan}</h3><p className="mt-3 text-sm text-slate-400">{gallery.gambar_kegiatan.length} foto · {gallery.penulis}</p><div className="mt-6 grid grid-cols-4 gap-2">{gallery.gambar_kegiatan.slice(0, 4).map((photo, index) => { const url = assetUrl(photo.url); return url ? <a key={photo.id || index} href={url} target="_blank" rel="noopener noreferrer"><img src={url} alt="" className="h-16 w-full rounded-xl object-cover opacity-70 transition hover:opacity-100" /></a> : null })}</div></div>
                  </article>
                )
              })}
            </div>
          ) : <EmptyState dark>Belum ada galeri yang dipublikasikan.</EmptyState>}
        </div>
      </section>

      <section data-reveal="up" className="section-texture section-texture-dark relative overflow-hidden bg-gradient-to-r from-sky-600 via-blue-600 to-indigo-700 px-4 py-20 text-white sm:px-6">
        <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full border-[48px] border-white/[0.06]" />
        <div className="relative mx-auto flex max-w-6xl flex-col items-start justify-between gap-8 md:flex-row md:items-center">
          <div><p className="text-xs font-extrabold uppercase tracking-[.2em] text-cyan-100">Layanan Internal</p><h2 className="mt-3 max-w-2xl text-3xl font-black leading-tight sm:text-4xl">Semua kebutuhan kepegawaian dalam satu portal.</h2></div>
          <a href={process.env.NEXT_PUBLIC_DASHBOARD_URL || 'https://admin.sudindikju2.com'} target="_blank" rel="noopener noreferrer" className="shrink-0 rounded-full bg-white px-7 py-4 text-sm font-extrabold text-blue-700 shadow-2xl transition hover:scale-105">Buka Portal →</a>
        </div>
      </section>

      <footer className="border-t border-slate-200 bg-white px-4 py-9 text-center text-sm text-slate-500">© {new Date().getFullYear()} Suku Dinas Pendidikan Jakarta Utara Wilayah II</footer>
    </div>
  )
}
