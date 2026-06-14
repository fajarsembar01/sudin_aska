import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const OFFICIAL_BASE = 'https://spmb.jakarta.go.id'

const ENDPOINTS = {
  smpSekolah: '/sekolah/1-smp-presaka.json',
  smpAkademik: '/statistik/1-smp-presaka.json',
  smpNonAkademik: '/statistik/1-smp-presnonaka.json',
  smaSekolah: '/sekolah/1-sma-presaka.json',
  smaAkademik: '/statistik/1-sma-presaka.json',
  smaMpmAkademik: '/statistik/1-sma-presnonaka.json',
}

async function fetchJson(path: string) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 5000)

  try {
    const response = await fetch(`${OFFICIAL_BASE}${path}`, {
      cache: 'no-store',
      signal: controller.signal,
      headers: {
        accept: 'application/json',
        referer: `${OFFICIAL_BASE}/020201/hasil`,
        'user-agent': 'Mozilla/5.0 SUDINDIKJU2 live-spmb-smp',
      },
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const contentType = response.headers.get('content-type') || ''
    if (!contentType.includes('application/json')) {
      throw new Error(`Invalid content-type ${contentType}`)
    }

    return response.json()
  } finally {
    clearTimeout(timeout)
  }
}

export async function GET() {
  try {
    const [
      smpSekolah,
      smpAkademik,
      smpNonAkademik,
      smaSekolah,
      smaAkademik,
      smaMpmAkademik,
    ] = await Promise.all([
      fetchJson(ENDPOINTS.smpSekolah),
      fetchJson(ENDPOINTS.smpAkademik),
      fetchJson(ENDPOINTS.smpNonAkademik),
      fetchJson(ENDPOINTS.smaSekolah),
      fetchJson(ENDPOINTS.smaAkademik),
      fetchJson(ENDPOINTS.smaMpmAkademik),
    ])

    return NextResponse.json({
      source: {
        smpAkademik: `${OFFICIAL_BASE}/020201/hasil`,
        smpNonAkademik: `${OFFICIAL_BASE}/020301/sekilas`,
        smaAkademik: `${OFFICIAL_BASE}/030201/sekilas`,
        smaMpmAkademik: `${OFFICIAL_BASE}/030301/sekilas`,
      },
      smpSekolah,
      smpAkademik,
      smpNonAkademik,
      smaSekolah,
      smaAkademik,
      smaMpmAkademik,
    })
  } catch (error) {
    console.error('Gagal fetch data resmi SPMB SMP/SMA:', error)
    return NextResponse.json(
      { error: 'Gagal mengambil data resmi SPMB Jakarta untuk SMP/SMA' },
      { status: 502 }
    )
  }
}
