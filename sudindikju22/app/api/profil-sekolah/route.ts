import { NextRequest, NextResponse } from 'next/server'

const PORTAL_API_BASE = (
  process.env.PORTAL_API_BASE ||
  process.env.NEXT_PUBLIC_PORTAL_API_BASE ||
  'https://admin.sudindikju2.com'
).replace(/\/+$/, '')

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const schoolId = searchParams.get('school_id')
  const category = searchParams.get('category') || 'tanaman'

  if (!schoolId || !/^\d+$/.test(schoolId)) {
    return NextResponse.json(
      { success: false, message: 'Parameter sekolah tidak valid.' },
      { status: 400 }
    )
  }

  const url = `${PORTAL_API_BASE}/portal/api/public/sekolah/${schoolId}/adiwiyata/${encodeURIComponent(category)}`

  try {
    const response = await fetch(url, { cache: 'no-store' })
    const body = await response.text()

    return new NextResponse(body, {
      status: response.status,
      headers: {
        'content-type': response.headers.get('content-type') || 'application/json',
      },
    })
  } catch {
    return NextResponse.json(
      { success: false, message: 'Gagal memuat profil sekolah publik.' },
      { status: 502 }
    )
  }
}
