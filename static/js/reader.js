/* ==========================================================================
   Online Text Reader Engine
   Controls: Font Size Zoom, Font Family, Theme (Light/Sepia/Dark), Reading Sync
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    const readerContainer = document.getElementById('reader-text-container');
    if (!readerContainer) return;

    let fontSize = 18; // default font size in px
    const minFontSize = 14;
    const maxFontSize = 32;

    const btnFontIncrease = document.getElementById('reader-font-plus');
    const btnFontDecrease = document.getElementById('reader-font-minus');
    const fontSelect = document.getElementById('reader-font-family');
    const themeSelect = document.getElementById('reader-theme-select');

    if (btnFontIncrease) {
        btnFontIncrease.addEventListener('click', () => {
            if (fontSize < maxFontSize) {
                fontSize += 2;
                readerContainer.style.fontSize = `${fontSize}px`;
            }
        });
    }

    if (btnFontDecrease) {
        btnFontDecrease.addEventListener('click', () => {
            if (fontSize > minFontSize) {
                fontSize -= 2;
                readerContainer.style.fontSize = `${fontSize}px`;
            }
        });
    }

    if (fontSelect) {
        fontSelect.addEventListener('change', (e) => {
            readerContainer.style.fontFamily = e.target.value;
        });
    }

    if (themeSelect) {
        themeSelect.addEventListener('change', (e) => {
            const theme = e.target.value;
            readerContainer.classList.remove('theme-sepia', 'theme-dark');
            if (theme === 'sepia') {
                readerContainer.classList.add('theme-sepia');
            } else if (theme === 'dark') {
                readerContainer.classList.add('theme-dark');
            }
        });
    }
});
