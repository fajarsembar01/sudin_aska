import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const portalApiBase = (
  process.env.NEXT_PUBLIC_PORTAL_API_BASE ||
  (process.env.NODE_ENV === 'development'
    ? 'http://127.0.0.1:5002'
    : 'https://admin.sudindikju2.com')
).replace(/\/+$/, '')

export async function GET() {
  try {
    const response = await fetch(
      `${portalApiBase}/daftar-tamu/api/public/service-usage-stats`,
      { cache: 'no-store', headers: { accept: 'application/json' } }
    )
    const body = await response.text()
    return new NextResponse(body, {
      status: response.status,
      headers: {
        'content-type': response.headers.get('content-type') || 'application/json',
        'cache-control': 'no-store',
      },
    })
  } catch {
    return NextResponse.json(
      { success: false, data: null, message: 'Statistik layanan belum dapat dimuat.' },
      { status: 502 }
    )
  }
}
