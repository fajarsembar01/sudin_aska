export const portalApiBase = (
  process.env.PORTAL_API_BASE ||
  process.env.NEXT_PUBLIC_PORTAL_API_BASE ||
  (process.env.NODE_ENV === 'development'
    ? 'http://127.0.0.1:5002'
    : 'https://admin.sudindikju2.com')
).replace(/\/+$/, '')

export interface CmsFile {
  id?: string | number
  name: string
  path?: string
  url: string | null
}

export interface CmsProfile {
  deskripsi_utama: string
  visi: string
  misi: string
  tugas_fungsi: string
  motto_pelayanan: string
  struktur_organisasi_url: string | null
  updated_at: string | null
}

export interface CmsPublicInformation {
  jaminan_pelayanan: string
  keamanan_keselamatan: string
  kompensasi_pelayanan: string
  updated_at: string | null
}

export interface CmsService {
  id: number
  nama: string
  deskripsi: string
  icon: string
  files: CmsFile[]
}

export interface CmsArticle {
  id: number
  judul: string
  kategori: string
  tanggal: string
  deskripsi: string
  thumbnail_url: string | null
  penulis: string
  files: CmsFile[]
}

export type CmsAnnouncement = CmsArticle

export interface CmsGallery {
  id: number
  nama_kegiatan: string
  tanggal: string
  thumbnail_url: string | null
  gambar_kegiatan: CmsFile[]
  penulis: string
}

export interface CmsContent {
  profil: CmsProfile
  informasi_publik: CmsPublicInformation
  layanan: CmsService[]
  artikel: CmsArticle[]
  pengumuman: CmsAnnouncement[]
  galeri: CmsGallery[]
}

interface CmsContentResponse {
  success: boolean
  data?: CmsContent
}

export async function getCmsContent(): Promise<CmsContent | null> {
  try {
    const response = await fetch(`${portalApiBase}/cms/api/public/content`, {
      cache: 'no-store',
      headers: { accept: 'application/json' },
    })
    if (!response.ok) return null
    const payload = (await response.json()) as CmsContentResponse
    return payload.success && payload.data ? payload.data : null
  } catch {
    return null
  }
}

export function resolveCmsUrl(path?: string | null) {
  if (!path) return null
  if (/^https?:\/\//i.test(path)) return path
  return `${portalApiBase}${path.startsWith('/') ? path : `/${path}`}`
}

export function formatCmsDate(value?: string | null) {
  if (!value) return ''
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('id-ID', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(date)
}
