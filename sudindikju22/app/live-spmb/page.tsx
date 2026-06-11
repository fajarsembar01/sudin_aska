import React from 'react';

export default function LiveSpmbPage() {
  return (
    <main className="min-h-screen bg-slate-50 flex flex-col items-center justify-center relative overflow-hidden">
      {/* Navbar Simple */}
      <nav className="absolute top-0 w-full px-6 py-4 flex items-center justify-between z-20 bg-white/50 backdrop-blur-sm border-b border-slate-200">
        <a href="/" className="flex items-center gap-2 group cursor-pointer">
          <img
            src="/logo.png"
            alt="Logo Sudin Pendidikan"
            className="w-8 h-8 object-contain"
          />
          <p className="text-sm font-bold text-sky-900 hidden sm:block">Sudin Pendidikan JU 2</p>
        </a>
        <a href="/" className="text-sm font-medium text-slate-500 hover:text-slate-900 transition-colors">
          Kembali ke Beranda
        </a>
      </nav>

      {/* Content */}
      <div className="text-center z-10 px-4">
        <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-emerald-100 mb-6 relative">
          <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-200 opacity-50 animate-ping"></span>
          <i className="bi bi-broadcast text-3xl text-emerald-600"></i>
        </div>
        <h1 className="text-4xl font-extrabold text-slate-900 mb-4">Live SPMB</h1>
        <p className="text-lg text-slate-600 max-w-md mx-auto mb-8">
          Sistem Penerimaan Murid Baru secara langsung sedang dalam tahap pengembangan. Pantau terus untuk pembaruan selanjutnya!
        </p>
        <a href="/" className="inline-flex items-center justify-center px-6 py-3 rounded-full bg-slate-900 text-white font-medium hover:bg-slate-800 transition-colors">
          Kembali ke Beranda
        </a>
      </div>

      {/* Decorative */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-emerald-200/20 rounded-full blur-3xl"></div>
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-sky-200/20 rounded-full blur-3xl"></div>
      </div>
    </main>
  );
}
