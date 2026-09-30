// Canvas labels do not inherit CSS when the dashboard theme changes.
(function () {
    function updateCharts() {
        if (!window.Chart || !Chart.instances) return;
        const style = getComputedStyle(document.documentElement);
        const text = style.getPropertyValue('--text-secondary').trim() || style.getPropertyValue('--bs-body-color').trim();
        const grid = style.getPropertyValue('--border-soft').trim() || style.getPropertyValue('--bs-border-color').trim();
        Object.values(Chart.instances).forEach(function (chart) {
            chart.options.color = text;
            const plugins = chart.options.plugins;
            if (plugins && plugins.legend && plugins.legend.labels) plugins.legend.labels.color = text;
            if (plugins && plugins.title) plugins.title.color = text;
            Object.values(chart.options.scales || {}).forEach(function (scale) {
                if (scale.ticks) scale.ticks.color = text;
                if (scale.grid) scale.grid.color = grid;
                if (scale.title) scale.title.color = text;
            });
            chart.update('none');
        });
    }
    let pending;
    function schedule() {
        cancelAnimationFrame(pending);
        pending = requestAnimationFrame(updateCharts);
    }
    new MutationObserver(schedule).observe(document.documentElement, {
        attributes: true, attributeFilter: ['data-theme', 'data-bs-theme']
    });
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', schedule);
    else schedule();
})();
