import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const OFFICIAL_BASE = 'https://spmb.jakarta.go.id'

const ROUTE_CANDIDATES = [
  '1-sd-dom',
  '1-sd-zonasi',
  '1-sd-domisili',
  '1-sd-reg',
  '1-sd-umum',
  '01-01-01',
  '1-01-01',
]

async function fetchJson(path: string) {
  const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 5000)

  try {
    const response = await fetch(`${OFFICIAL_BASE}${path}`, {
      cache: 'no-store',
      signal: controller.signal,
      headers: {
        accept: 'application/json',
        referer: `${OFFICIAL_BASE}/010101/sekilas`,
        'user-agent': 'Mozilla/5.0 SUDINDIKJU2 live-spmb-sd',
      },
    })

    if (!response.ok) {
      return null
    }

    const contentType = response.headers.get('content-type') || ''
    if (!contentType.includes('application/json')) {
      return null
    }

    return response.json()
  } catch (error) {
    console.error(`Gagal fetch ${path}:`, error)
    return null
  } finally {
    clearTimeout(timeout)
  }
}

export async function GET() {
  for (const routeKey of ROUTE_CANDIDATES) {
    const [sekolah, statistik] = await Promise.all([
      fetchJson(`/sekolah/${routeKey}.json`),
      fetchJson(`/statistik/${routeKey}.json`),
    ])

    if (sekolah && statistik) {
      return NextResponse.json({
        source: `${OFFICIAL_BASE}/010101/sekilas`,
        routeKey,
        sekolah,
        statistik,
      })
    }
  }

  return NextResponse.json(
    {
      error: 'Gagal mengambil data resmi SPMB Jakarta untuk /010101/sekilas',
      source: `${OFFICIAL_BASE}/010101/sekilas`,
    },
    { status: 502 }
  )
}
