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

const readDashboardJson = async (response: Response) => {
  const text = await response.text()
  if (!text) return {}
  return JSON.parse(text)
}

export async function GET() {
  const dashboardBaseUrl = (process.env.DASHBOARD_BASE_URL || process.env.NEXT_PUBLIC_DASHBOARD_BASE_URL || '').trim().replace(/\/$/, '')

  if (!dashboardBaseUrl) {
    return NextResponse.json({
      data: fallbackServiceTypes.map((name, index) => ({
        id: index + 1,
        name,
        sort_order: (index + 1) * 10
      })),
      source: 'fallback'
    })
  }

  try {
    const response = await fetch(`${dashboardBaseUrl}/api/spmb-service-types`, {
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
      source: 'dashboard'
    })
  } catch (error) {
    console.error('Gagal mengambil jenis pelayanan SPMB dari dashboard:', error)
    return NextResponse.json({
      data: fallbackServiceTypes.map((name, index) => ({
        id: index + 1,
        name,
        sort_order: (index + 1) * 10
      })),
      source: 'fallback'
    })
  }
}
