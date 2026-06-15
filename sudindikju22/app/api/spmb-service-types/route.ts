import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const fallbackServiceTypes = [
  'Informasi SPMB',
  'Verifikasi Berkas',
  'Bantuan Akun',
  'Perubahan Data',
  'Pengaduan',
  'Lainnya'
]

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
    'http://127.0.0.1:5001'
  ]
}

const readDashboardJson = async (response: Response) => {
  const text = await response.text()
  if (!text) return {}
  return JSON.parse(text)
}

export async function GET() {
  const attemptedUrls: string[] = []

  for (const baseUrl of dashboardBaseUrls()) {
    const upstreamUrl = `${baseUrl}/api/spmb-service-types`
    attemptedUrls.push(upstreamUrl)

    try {
      const response = await fetch(upstreamUrl, {
        cache: 'no-store',
        headers: {
          accept: 'application/json'
        }
      })

      if (!response.ok) {
        throw new Error(`Dashboard API returned ${response.status}`)
      }

      const payload = await readDashboardJson(response)
      const rows = Array.isArray(payload?.data) ? payload.data : []

      return NextResponse.json({
        data: rows
          .map((item: { id?: unknown; name?: unknown; description?: unknown; sort_order?: unknown }, index: number) => ({
            id: item.id ?? index + 1,
            name: String(item.name || '').trim(),
            description: item.description,
            sort_order: item.sort_order ?? (index + 1) * 10
          }))
          .filter((item: { name: string }) => item.name),
        source: 'dashboard',
        upstreamUrl
      })
    } catch (error) {
      console.error(`Gagal mengambil jenis pelayanan SPMB dari dashboard ${upstreamUrl}:`, error)
    }
  }

  return NextResponse.json({
    data: fallbackServiceTypes.map((name, index) => ({
      id: index + 1,
      name,
      sort_order: (index + 1) * 10
    })),
    source: 'fallback',
    attemptedUrls
  })
}
