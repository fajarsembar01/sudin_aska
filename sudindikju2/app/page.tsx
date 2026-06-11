// File: src/app/page.tsx
'use client'

import React from 'react'

export default function Page() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-gradient-to-b from-sky-50 via-white to-slate-100 px-4 py-10 md:px-6 md:py-12">
      <div className="w-full max-w-3xl bg-white/90 backdrop-blur-md rounded-2xl shadow-2xl border border-slate-100 overflow-hidden flex flex-col" style={{ minHeight: '600px' }}>
        <div className="p-6 md:p-12 grid gap-10 md:grid-cols-2 items-start flex-1" style={{ alignItems: 'stretch' }}>
          {/* LEFT | Informasi Utama */}
          <div className="flex flex-col h-full justify-between hidden md:block">
            <div>
              <h1 className="text-2xl md:text-3xl font-extrabold text-sky-900 leading-snug mb-2">
                Suku Dinas Pendidikan <br /> JU — Wilayah 2
              </h1>
              <p className="mt-3 text-slate-600 mb-6">
                Halaman resmi <strong>Suku Dinas Pendidikan</strong> sedang dalam pengembangan.<br />
                Kami sedang menyiapkan portal layanan, publikasi informasi, serta integrasi <strong>ASKA</strong> — Agen AI Sekolah Kita
              </p>
              <div className="rounded-xl bg-sky-50 border border-sky-100 p-4 mb-6">
                <p className="text-sm text-slate-700 font-medium mb-2">Fokus Pengembangan</p>
                <ul className="text-sm text-slate-600 list-disc list-inside space-y-1">
                  <li>Automasi layanan pendidikan </li>
                  <li>Informasi & pengumuman resmi</li>
                  <li>Layanan administrasi untuk sekolah</li>
                  <li>ASKA: Asisten AI untuk pelayanan</li>
                  <li>Dashboard data & koordinasi wilayah</li>
                </ul>
              </div>
            </div>
            
          </div>

          {/* RIGHT | Ilustrasi */}
          <div className="flex flex-col items-center gap-8">
            <div className="w-full max-w-sm">
              <div className="bg-gradient-to-tr from-white to-sky-50 rounded-xl p-6 border border-slate-100 shadow-sm">
                <svg viewBox="0 0 240 160" className="w-full h-40" xmlns="http://www.w3.org/2000/svg" fill="none">
                  <rect x="6" y="16" width="228" height="108" rx="12" fill="url(#g1)" />
                  <g opacity="0.95">
                    <rect x="18" y="28" width="76" height="38" rx="6" fill="#fff" />
                    <rect x="102" y="28" width="98" height="14" rx="6" fill="#fff" />
                    <rect x="102" y="54" width="60" height="14" rx="6" fill="#fff" />
                    <circle cx="46" cy="102" r="12" fill="#fff" />
                    <rect x="74" y="90" width="132" height="22" rx="6" fill="#fff" />
                  </g>
                  <defs>
                    <linearGradient id="g1" x1="0" x2="1" y1="0" y2="1">
                      <stop offset="0" stopColor="#E0F2FE" />
                      <stop offset="1" stopColor="#F8FAFC" />
                    </linearGradient>
                  </defs>
                </svg>
                <div className="mt-3 text-center">
                  <p className="text-sm font-medium text-sky-800">
                    Website Suku Dinas Pendidikan Jakarta Utara 2 — Coming Soon
                  </p>
                  <p className="text-xs text-slate-500">
                    Portal layanan, informasi, dan integrasi ASKA
                  </p>
                </div>
              </div>
            </div>
            {/* Progress */}
            <div className="w-full max-w-sm">
              <p className="text-xs text-slate-600 mb-2">Progress Pengembangan</p>
              <div className="space-y-3">
                <Progress label="Desain & Struktur Informasi" pct={80} />
                <Progress label="Frontend Website SUDINDIK JU2" pct={35} />
                <Progress label="Integrasi ASKA (backend)" pct={12} />
              </div>
            </div>
            
          </div>
        </div>
        <footer className="text-center text-xs text-slate-400 py-2 border-t border-slate-100" style={{ marginTop: 0 }}>
          © 2025 Suku Dinas Pendidikan Jakarta Utara — Wilayah 2
        </footer>
      </div>
    </main>
  )
}

/* Progress bar component */
function Progress({ label, pct }: { label: string; pct: number }) {
  const width = `${Math.min(Math.max(0, pct), 100)}%`
  return (
    <div>
      <div className="flex justify-between text-xs">
        <span className="text-slate-700">{label}</span>
        <span className="text-slate-500">{pct}%</span>
      </div>
      <div className="mt-1 h-2 bg-slate-200 rounded-full overflow-hidden">
        <div
          className="h-2 rounded-full"
          style={{
            width,
            background: 'linear-gradient(90deg,#0ea5e9 0%,#3b82f6 100%)',
          }}
        />
      </div>
    </div>
  )
}
