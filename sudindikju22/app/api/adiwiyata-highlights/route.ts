import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const portalApiBase = (
  process.env.ADIWIYATA_API_BASE ||
  process.env.NEXT_PUBLIC_PORTAL_API_BASE ||
  (process.env.NODE_ENV === 'development'
    ? 'http://127.0.0.1:5002'
    : 'https://admin.sudindikju2.com')
).replace(/\/+$/, '')

async function getPhotos(sort: 'top' | 'newest') {
  const response = await fetch(
    `${portalApiBase}/portal/api/public/adiwiyata/top-photos?sort=${sort}&limit=3`,
    { cache: 'no-store', headers: { accept: 'application/json' } }
  )

  if (!response.ok) throw new Error(`Adiwiyata API returned ${response.status}`)
  const payload = await response.json()
  return Array.isArray(payload?.photos) ? payload.photos : []
}

function decodeHtmlAttribute(value: string) {
  return value
    .replace(/&amp;/g, '&')
    .replace(/&#x2F;/gi, '/')
    .replace(/&#47;/g, '/')
    .replace(/&quot;/g, '"')
}

async function getVideoThumbnail(url?: string) {
  if (!url || !/^https?:\/\//i.test(url)) return null
  const instagramId = url.match(/instagram\.com\/(?:p|reel|tv)\/([A-Za-z0-9_-]+)/i)?.[1]
  if (instagramId) return `/api/adiwiyata-thumbnail?id=${encodeURIComponent(instagramId)}`
  try {
    const response = await fetch(url, {
      next: { revalidate: 1800 },
      headers: {
        accept: 'text/html',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36',
      },
    })
    if (!response.ok) return null
    const html = await response.text()
    const match = html.match(/<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']/i)
      || html.match(/<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:image["']/i)
    return match?.[1] ? decodeHtmlAttribute(match[1]) : null
  } catch {
    return null
  }
}

async function enrichPhotos(items: Record<string, unknown>[]) {
  return Promise.all(items.map(async item => {
    if (item.media_type !== 'video_link' || typeof item.media_path !== 'string') return item
    return { ...item, thumbnail_url: await getVideoThumbnail(item.media_path) }
  }))
}

export async function GET() {
  try {
    const [topRows, newestRows] = await Promise.all([getPhotos('top'), getPhotos('newest')])
    const [top, newest] = await Promise.all([enrichPhotos(topRows), enrichPhotos(newestRows)])
    return NextResponse.json(
      { success: true, data: { top, newest } },
      { headers: { 'cache-control': 'no-store' } }
    )
  } catch {
    return NextResponse.json(
      { success: false, data: { top: [], newest: [] }, message: 'Sorotan Adiwiyata belum dapat dimuat.' },
      { status: 502 }
    )
  }
}
