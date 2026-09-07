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
      message: 'Dashboard API mengembalikan HTML, bukan JSON. Cek DASHBOARD_BASE_URL dan pastikan kode dashboard terbaru sudah terdeploy.',
      upstreamStatus: response.status,
      upstreamContentType: response.headers.get('content-type') || '',
      upstreamPreview: text.slice(0, 180)
    }
  }
}

const proxyMutation = async (
  request: NextRequest,
  id: string,
  method: 'PUT' | 'DELETE'
) => {
  const attemptedUrls: string[] = []

  try {
    const body = method === 'PUT' ? await request.json() : null
    let lastPayload: Record<string, unknown> | null = null
    let lastStatus = 502

    for (const baseUrl of dashboardBaseUrls()) {
      const upstreamUrl = `${baseUrl}/api/spmb-evaluations/${id}`
      attemptedUrls.push(upstreamUrl)

      try {
        const response = await fetch(upstreamUrl, {
          method,
          cache: 'no-store',
          headers: {
            accept: 'application/json',
            ...(method === 'PUT' ? { 'content-type': 'application/json' } : {}),
            'user-agent': request.headers.get('user-agent') || 'sudindikju22-evaluasi-spmb'
          },
          ...(method === 'PUT' ? { body: JSON.stringify(body) } : {})
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
      message: String(lastPayload?.message || `Gagal ${method === 'PUT' ? 'memperbarui' : 'menghapus'} evaluasi.`),
      attemptedUrls
    }, { status: lastStatus })
  } catch (error) {
    console.error(`Gagal ${method === 'PUT' ? 'memperbarui' : 'menghapus'} evaluasi SPMB:`, error)
    return NextResponse.json({
      success: false,
      message: `Gagal ${method === 'PUT' ? 'memperbarui' : 'menghapus'} evaluasi.`,
      attemptedUrls
    }, { status: 502 })
  }
}

export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params
  return proxyMutation(request, id, 'PUT')
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params
  return proxyMutation(request, id, 'DELETE')
}
