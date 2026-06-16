import { NextResponse } from 'next/server'
import https from 'node:https'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

const OFFICIAL_BASE = 'https://spmb.jakarta.go.id'
const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36'

const ENDPOINTS = {
  smpSekolah: '/sekolah/1-smp-presaka.json',
  smpAkademik: '/statistik/1-smp-presaka.json',
  smpNonAkademik: '/statistik/1-smp-presnonaka.json',
  smaSekolah: '/sekolah/1-sma-presaka.json',
  smaAkademik: '/statistik/1-sma-presaka.json',
  smaMpmAkademik: '/statistik/1-sma-presnonaka.json',
}

async function fetchJson(path: string) {
  return new Promise<unknown>((resolve, reject) => {
    const request = https.request(
      `${OFFICIAL_BASE}${path}`,
      {
        method: 'GET',
        family: 4,
        timeout: 8000,
        headers: {
          accept: 'application/json',
          'accept-language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
          referer: `${OFFICIAL_BASE}/020201/hasil`,
          'user-agent': USER_AGENT,
        },
      },
      response => {
        if (!response.statusCode || response.statusCode < 200 || response.statusCode >= 300) {
          response.resume()
          reject(new Error(`HTTP ${response.statusCode || 0}`))
          return
        }

        const contentType = String(response.headers['content-type'] || '')
        if (!contentType.includes('application/json')) {
          response.resume()
          reject(new Error(`Invalid content-type ${contentType}`))
          return
        }

        const chunks: Buffer[] = []
        response.on('data', chunk => chunks.push(Buffer.from(chunk)))
        response.on('end', () => {
          try {
            resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')))
          } catch (error) {
            reject(error)
          }
        })
      }
    )

    request.on('timeout', () => request.destroy(new Error(`Timeout ${path}`)))
    request.on('error', reject)
    request.end()
  })
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
