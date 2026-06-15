import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const dashboardBaseUrl = () => (
  process.env.DASHBOARD_BASE_URL ||
  process.env.NEXT_PUBLIC_DASHBOARD_BASE_URL ||
  'http://localhost:5002'
).trim().replace(/\/$/, '')

const readDashboardJson = async (response: Response) => {
  const text = await response.text()
  if (!text) return {}

  try {
    return JSON.parse(text)
  } catch {
    return {
      success: false,
      data: [],
      message: 'Dashboard API mengembalikan HTML, bukan JSON. Cek DASHBOARD_BASE_URL dan restart dashboard.',
      upstreamStatus: response.status
    }
  }
}

export async function GET() {
  try {
    const response = await fetch(`${dashboardBaseUrl()}/api/spmb-evaluations?limit=100`, {
      cache: 'no-store',
      headers: {
        accept: 'application/json'
      }
    })

    const payload = await readDashboardJson(response)
    return NextResponse.json(payload, { status: response.ok ? 200 : response.status })
  } catch (error) {
    console.error('Gagal mengambil riwayat evaluasi SPMB:', error)
    return NextResponse.json({ data: [], error: 'Gagal mengambil riwayat evaluasi dari server.' }, { status: 502 })
  }
}

export async function POST(request: NextRequest) {
  try {
    const payload = await request.json()
    const response = await fetch(`${dashboardBaseUrl()}/api/spmb-evaluations`, {
      method: 'POST',
      cache: 'no-store',
      headers: {
        accept: 'application/json',
        'content-type': 'application/json',
        'user-agent': request.headers.get('user-agent') || 'sudindikju22-evaluasi-spmb'
      },
      body: JSON.stringify(payload)
    })

    const responsePayload = await readDashboardJson(response)
    return NextResponse.json(responsePayload, { status: response.ok ? 200 : response.status })
  } catch (error) {
    console.error('Gagal menyimpan evaluasi SPMB:', error)
    return NextResponse.json({ success: false, message: 'Gagal menyimpan evaluasi ke server.' }, { status: 502 })
  }
}
