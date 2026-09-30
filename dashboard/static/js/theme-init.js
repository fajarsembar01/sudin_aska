// Apply the saved dashboard theme before a standalone public page is painted.
(function () {
    let stored;
    try { stored = localStorage.getItem('theme'); } catch (error) {}
    const preference = window.matchMedia('(prefers-color-scheme: dark)');
    function apply() {
        const theme = stored === 'dark' || stored === 'light'
            ? stored : (preference.matches ? 'dark' : 'light');
        document.documentElement.dataset.theme = theme;
        document.documentElement.dataset.bsTheme = theme;
    }
    apply();
    preference.addEventListener('change', apply);
    window.addEventListener('storage', function (event) {
        if (event.key === 'theme' || event.key === null) {
            stored = event.newValue;
            apply();
        }
    });
})();
