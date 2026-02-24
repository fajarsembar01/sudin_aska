/**
 * ============================================
 * KONFIGURASI GRADASI WARNA PORTAL PANBERSS
 * ============================================
 * 
 * CARA MENGUBAH:
 * 1. Edit threshold (batas nilai) di bagian THRESHOLDS
 * 2. Edit kode warna di bagian COLORS
 * 3. Refresh halaman untuk melihat perubahan
 * 
 * ATAU gunakan popup edit di halaman statistik admin.
 */

const PANBERSS_COLORS = {
    // === THRESHOLD NILAI (dalam persen 0-100) ===
    // Nilai ini bisa diubah via localStorage untuk sesi pengguna
    THRESHOLDS: {
        EXCELLENT: 85,   // Nilai >= 85 = HIJAU (Sangat Baik)
        GOOD: 70,        // Nilai >= 70 = KUNING (Baik)
        POOR: 55,        // Nilai >= 55 = ORANYE (Kurang)
        // Nilai < 55 = MERAH GELAP (Kritis)
    },

    // === KODE WARNA (format hex) ===
    COLORS: {
        EXCELLENT: '#198754',  // Hijau Bootstrap
        GOOD: '#ffc107',       // Kuning Bootstrap
        POOR: '#fd7e14',       // Oranye Bootstrap
        CRITICAL: '#b02a37',   // Merah Gelap (lebih kontras dari oranye)
    },

    // === BOOTSTRAP CLASSES ===
    BOOTSTRAP_CLASSES: {
        EXCELLENT: 'bg-success',
        GOOD: 'bg-warning text-dark',
        POOR: 'bg-orange text-white',
        CRITICAL: 'bg-danger',
    },

    // === CSS CLASSES UNTUK BADGE GALERI ===
    BADGE_CLASSES: {
        EXCELLENT: 'badge-score-green',
        GOOD: 'badge-score-yellow',
        POOR: 'badge-score-orange',
        CRITICAL: 'badge-score-red',
    },

    // === CHART COLORS (untuk distribusi 9 bar) ===
    CHART_GRADIENT: [
        '#dc3545', // <60 (Merah)
        '#e75e4f', // 60-65
        '#f0825a', // 65-70  
        '#fd7e14', // 70-75 (Oranye)
        '#ffc107', // 75-80 (Kuning)
        '#d4e157', // 80-85
        '#9ccc65', // 85-90
        '#66bb6a', // 90-95
        '#198754', // 95-100 (Hijau)
    ],

    // === HEAT MAP GRADIENT ===
    HEATMAP: {
        0.4: 'rgba(255, 0, 0, 0.3)',
        0.7: 'rgba(139, 0, 0, 0.5)',
        1.0: 'rgba(0, 0, 0, 0.65)',
    }
};

const PANBERSS_THRESHOLD_DEFAULTS = Object.freeze({
    EXCELLENT: 85,
    GOOD: 70,
    POOR: 55,
});

const PANBERSS_THRESHOLD_LEGACY_DEFAULTS = Object.freeze({
    EXCELLENT: 80,
    GOOD: 60,
    POOR: 40,
});

function applyThresholds(excellent, good, poor) {
    PANBERSS_COLORS.THRESHOLDS.EXCELLENT = excellent;
    PANBERSS_COLORS.THRESHOLDS.GOOD = good;
    PANBERSS_COLORS.THRESHOLDS.POOR = poor;
}

/**
 * Load thresholds dari localStorage jika ada
 */
function loadStoredThresholds() {
    const defaults = PANBERSS_THRESHOLD_DEFAULTS;
    try {
        const stored = localStorage.getItem('panberss_thresholds');
        if (!stored) {
            applyThresholds(defaults.EXCELLENT, defaults.GOOD, defaults.POOR);
            return;
        }

        const parsed = JSON.parse(stored);
        const excellent = Number(parsed.excellent);
        const good = Number(parsed.good);
        const poor = Number(parsed.poor);

        const resolvedExcellent = Number.isFinite(excellent) ? excellent : defaults.EXCELLENT;
        const resolvedGood = Number.isFinite(good) ? good : defaults.GOOD;
        const resolvedPoor = Number.isFinite(poor) ? poor : defaults.POOR;

        const legacy = PANBERSS_THRESHOLD_LEGACY_DEFAULTS;
        const usesLegacyDefaults =
            resolvedExcellent === legacy.EXCELLENT &&
            resolvedGood === legacy.GOOD &&
            resolvedPoor === legacy.POOR;

        if (usesLegacyDefaults) {
            applyThresholds(defaults.EXCELLENT, defaults.GOOD, defaults.POOR);
            localStorage.setItem('panberss_thresholds', JSON.stringify({
                excellent: defaults.EXCELLENT,
                good: defaults.GOOD,
                poor: defaults.POOR,
            }));
            return;
        }

        applyThresholds(resolvedExcellent, resolvedGood, resolvedPoor);
    } catch (e) {
        console.warn('Failed to load stored thresholds:', e);
        applyThresholds(defaults.EXCELLENT, defaults.GOOD, defaults.POOR);
    }
}

/**
 * Simpan thresholds ke localStorage
 */
function saveThresholds(excellent, good, poor) {
    try {
        applyThresholds(excellent, good, poor);
        localStorage.setItem('panberss_thresholds', JSON.stringify({
            excellent: excellent,
            good: good,
            poor: poor
        }));
        return true;
    } catch (e) {
        console.error('Failed to save thresholds:', e);
        return false;
    }
}

/**
 * Reset thresholds ke default
 */
function resetThresholds() {
    localStorage.removeItem('panberss_thresholds');
    applyThresholds(
        PANBERSS_THRESHOLD_DEFAULTS.EXCELLENT,
        PANBERSS_THRESHOLD_DEFAULTS.GOOD,
        PANBERSS_THRESHOLD_DEFAULTS.POOR,
    );
}

/**
 * Fungsi untuk mendapatkan warna berdasarkan skor persen
 * @param {number} scorePct - Skor dalam persen (0-100)
 * @returns {object} - { color, className, badgeClass, level }
 */
function getScoreColor(scorePct) {
    const T = PANBERSS_COLORS.THRESHOLDS;
    const C = PANBERSS_COLORS.COLORS;
    const B = PANBERSS_COLORS.BOOTSTRAP_CLASSES;
    const D = PANBERSS_COLORS.BADGE_CLASSES;

    if (scorePct >= T.EXCELLENT) {
        return { color: C.EXCELLENT, className: B.EXCELLENT, badgeClass: D.EXCELLENT, level: 'excellent' };
    } else if (scorePct >= T.GOOD) {
        return { color: C.GOOD, className: B.GOOD, badgeClass: D.GOOD, level: 'good' };
    } else if (scorePct >= T.POOR) {
        return { color: C.POOR, className: B.POOR, badgeClass: D.POOR, level: 'poor' };
    } else {
        return { color: C.CRITICAL, className: B.CRITICAL, badgeClass: D.CRITICAL, level: 'critical' };
    }
}

/**
 * Fungsi untuk mendapatkan intensitas heatmap (0-1)
 * Semakin rendah skor, semakin tinggi intensitas
 */
function getHeatmapIntensity(scorePct) {
    const T = PANBERSS_COLORS.THRESHOLDS;
    if (scorePct >= T.EXCELLENT) return 0.0;
    if (scorePct >= T.GOOD) return 0.2;
    if (scorePct >= T.POOR) return 0.7;
    return 1.0;
}

/**
 * Get label for score level
 */
function getScoreLabel(scorePct) {
    const T = PANBERSS_COLORS.THRESHOLDS;
    if (scorePct >= T.EXCELLENT) return 'Sangat Baik';
    if (scorePct >= T.GOOD) return 'Baik';
    if (scorePct >= T.POOR) return 'Kurang';
    return 'Kritis';
}

// Load stored thresholds on script load
loadStoredThresholds();
