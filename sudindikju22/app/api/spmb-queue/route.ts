import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const dashboardBaseUrls = () => {
  const configured = (
    process.env.DASHBOARD_BASE_URL ||
    process.env.NEXT_PUBLIC_DASHBOARD_BASE_URL ||
    ''
  ).trim().replace(/\/$/, '')

  if (configured) return [configured]

  return [
    'http://127.0.0.1:8000',
    'http://127.0.0.1:8001',
    'http://127.0.0.1:5001',
    'http://127.0.0.1:5002'
  ]
}

const readDashboardJson = async (response: Response) => {
  const text = await response.text()
  if (!text) return {}

  try {
    return JSON.parse(text)
  } catch {
    return {
      success: false,
      message: 'Dashboard API mengembalikan HTML, bukan JSON. Cek DASHBOARD_BASE_URL dan restart dashboard.',
      upstreamStatus: response.status,
      upstreamContentType: response.headers.get('content-type') || '',
      upstreamPreview: text.slice(0, 180)
    }
  }
}

export async function GET() {
  const attemptedUrls: string[] = []

  try {
    let lastPayload: Record<string, unknown> | null = null
    let lastStatus = 502

    for (const baseUrl of dashboardBaseUrls()) {
      const upstreamUrl = `${baseUrl}/api/spmb-queue`
      attemptedUrls.push(upstreamUrl)

      try {
        const response = await fetch(upstreamUrl, {
          cache: 'no-store',
          headers: { accept: 'application/json' }
        })
        const payload = await readDashboardJson(response)
        if (payload && typeof payload === 'object') {
          payload.upstreamUrl = upstreamUrl
          payload.attemptedUrls = attemptedUrls
        }
        if (response.ok) {
          return NextResponse.json(payload, { status: 200 })
        }
        lastPayload = payload
        lastStatus = response.status
      } catch (error) {
        lastPayload = {
          success: false,
          message: error instanceof Error ? error.message : 'Gagal menghubungi Dashboard API.'
        }
      }
    }

    return NextResponse.json({
      ...(lastPayload || {}),
      success: false,
      message: String(lastPayload?.message || 'Gagal mengambil nomor antrian dari server.'),
      attemptedUrls
    }, { status: lastStatus })
  } catch (error) {
    console.error('Gagal mengambil nomor antrian SPMB:', error)
    return NextResponse.json({
      success: false,
      message: 'Gagal mengambil nomor antrian dari server.',
      attemptedUrls
    }, { status: 502 })
  }
}

export async function POST(request: NextRequest) {
  const attemptedUrls: string[] = []

  try {
    const payload = await request.json()
    let lastPayload: Record<string, unknown> | null = null
    let lastStatus = 502

    for (const baseUrl of dashboardBaseUrls()) {
      const upstreamUrl = `${baseUrl}/api/spmb-queue`
      attemptedUrls.push(upstreamUrl)

      try {
        const response = await fetch(upstreamUrl, {
          method: 'POST',
          cache: 'no-store',
          headers: {
            accept: 'application/json',
            'content-type': 'application/json',
            'user-agent': request.headers.get('user-agent') || 'sudindikju22-spmb-queue'
          },
          body: JSON.stringify(payload)
        })

        const responsePayload = await readDashboardJson(response)
        if (responsePayload && typeof responsePayload === 'object') {
          responsePayload.upstreamUrl = upstreamUrl
          responsePayload.attemptedUrls = attemptedUrls
        }
        if (response.ok) {
          return NextResponse.json(responsePayload, { status: 200 })
        }
        lastPayload = responsePayload
        lastStatus = response.status
      } catch (error) {
        lastPayload = {
          success: false,
          message: error instanceof Error ? error.message : 'Gagal menghubungi Dashboard API.'
        }
      }
    }

    return NextResponse.json({
      ...(lastPayload || {}),
      success: false,
      message: String(lastPayload?.message || 'Gagal memperbarui nomor antrian.'),
      attemptedUrls
    }, { status: lastStatus })
  } catch (error) {
    console.error('Gagal memperbarui nomor antrian SPMB:', error)
    return NextResponse.json({
      success: false,
      message: 'Gagal memperbarui nomor antrian.',
      attemptedUrls
    }, { status: 502 })
  }
}
