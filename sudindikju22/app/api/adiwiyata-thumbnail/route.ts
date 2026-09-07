import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export async function GET(request: NextRequest) {
  const id = request.nextUrl.searchParams.get('id') || ''
  if (!/^[A-Za-z0-9_-]{5,30}$/.test(id)) {
    return NextResponse.json({ message: 'ID media tidak valid.' }, { status: 400 })
  }

  try {
    const response = await fetch(`https://www.instagram.com/p/${id}/media/?size=l`, {
      cache: 'no-store',
      redirect: 'follow',
      headers: {
        accept: 'image/avif,image/webp,image/apng,image/jpeg,*/*',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36',
      },
    })
    const contentType = response.headers.get('content-type') || ''
    if (!response.ok || !contentType.startsWith('image/')) {
      return NextResponse.json({ message: 'Thumbnail tidak tersedia.' }, { status: 404 })
    }
    return new NextResponse(response.body, {
      status: 200,
      headers: {
        'content-type': contentType,
        'cache-control': 'public, max-age=1800, stale-while-revalidate=86400',
      },
    })
  } catch {
    return NextResponse.json({ message: 'Thumbnail tidak dapat dimuat.' }, { status: 502 })
  }
}
