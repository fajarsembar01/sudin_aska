# Admin Stats Chart.js Structure

This file documents the **correct** Chart.js structure for admin_stats.html.
**DO NOT modify this structure** - it has caused repeated errors.

## Known Error: `jinja2.exceptions.TemplateSyntaxError: unexpected '}'`

This error occurs when the `tojson` filter is missing the closing double braces.

**Cause:** `{{ score_dist | tojson }` ← Only one closing brace
**Fix:** `{{ score_dist | tojson }}` ← Must have TWO closing braces `}}`

**Quick check command:**
```bash
grep -n "tojson" dashboard/portal/templates/portal/admin_stats.html | grep -v "}}"
```
If this returns any lines, those need fixing!

## Critical Rules

1. **Jinja2 syntax**: Always use `{{ score_dist | tojson }}` with DOUBLE closing braces `}}`
2. **datasets structure**: `backgroundColor` MUST be INSIDE the datasets object, NOT after it
3. **Object nesting**: Each nested object must close properly before the next property

## COMPLETE COPY-PASTE SOLUTION

If charts are broken, replace the ENTIRE script block (search for `scoreDistChart`) with this:

```html
<script>
    document.addEventListener('DOMContentLoaded', function () {
        // --- Score Distribution Chart ---
        const distEl = document.getElementById('scoreDistChart');
        if (distEl) {
            new Chart(distEl.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: ['<60', '60-65', '65-70', '70-75', '75-80', '80-85', '85-90', '90-95', '95-100'],
                    datasets: [{
                        label: 'Jumlah Sekolah',
                        data: {{ score_dist | tojson }},
                        backgroundColor: ['#dc3545', '#e75e4f', '#f0825a', '#f8a464', '#ffc107', '#d4e157', '#9ccc65', '#66bb6a', '#198754'],
                        borderRadius: 4,
                        barPercentage: 0.7
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, ticks: { precision: 0 }, grid: { borderDash: [2, 4] } },
                        x: { grid: { display: false } }
                    }
                }
            });
        }

        // --- Status Pie Chart ---
        const pieEl = document.getElementById('statusPieChart');
        if (pieEl) {
            new Chart(pieEl.getContext('2d'), {
                type: 'doughnut',
                data: {
                    labels: ['Draft', 'Submitted'],
                    datasets: [{
                        data: [{{ stats.assessments.drafts or 0 }}, {{ stats.assessments.submitted or 0 }}],
                        backgroundColor: ['#ffc107', '#198754'],
                        borderWidth: 0,
                        hoverOffset: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '70%',
                    plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, padding: 20 } } }
                }
            });
        }
    });
</script>
```

## Common Mistakes to Avoid

❌ **WRONG** - Extra closing brace before backgroundColor:
```javascript
datasets: [{
    data: {{ score_dist | tojson }},
},  // <-- This breaks the structure!
    backgroundColor: [...]
```

✅ **CORRECT** - All properties inside datasets:
```javascript
datasets: [{
    data: {{ score_dist | tojson }},
    backgroundColor: [...],  // Inside datasets object
    borderRadius: 4
}]
```

❌ **WRONG** - Missing closing brace in tojson:
```javascript
data: {{ score_dist | tojson }  // Missing second }
```

✅ **CORRECT**:
```javascript
data: {{ score_dist | tojson }},  // Proper closing }}
```
