/* ==========================================================================
   Pustika Standalone Online Text & PDF Reader Engine
   Features: Sequential 1:1 Page Reading, 3D Realistic Page Flip Animation,
             Zoom, Font Families, Themes, Jump-to-page & Arrow Key Navigation
   ========================================================================== */

let standaloneReaderState = {
    bookId: null,
    currentPage: 1,
    totalPages: 1,
    pages: [],
    fontSize: 18,
    theme: 'light',
    fontFamily: 'serif'
};

document.addEventListener('DOMContentLoaded', () => {
    initStandaloneReader();
});

async function initStandaloneReader() {
    const rootEl = document.getElementById('reader-root');
    if (!rootEl) return;

    standaloneReaderState.bookId = parseInt(rootEl.getAttribute('data-book-id'), 10);
    standaloneReaderState.currentPage = parseInt(rootEl.getAttribute('data-current-page'), 10) || 1;
    standaloneReaderState.totalPages = parseInt(rootEl.getAttribute('data-total-pages'), 10) || 1;

    // Fetch full pages list for instant animated turns
    try {
        const res = await fetch(`/api/book/${standaloneReaderState.bookId}/pages`);
        if (res.ok) {
            const data = await res.json();
            standaloneReaderState.pages = data.pages || [];
            standaloneReaderState.totalPages = data.total_pages || standaloneReaderState.totalPages;
        }
    } catch (e) {
        console.warn('Could not preload full pages list:', e);
    }

    // Keyboard Arrow navigation
    document.addEventListener('keydown', (e) => {
        if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;
        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            changeStandalonePage(-1);
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            changeStandalonePage(1);
        }
    });

    // Restore saved settings
    const savedTheme = localStorage.getItem('pustika_reader_theme') || 'light';
    const savedFont = localStorage.getItem('pustika_reader_font') || 'serif';
    const savedSize = parseInt(localStorage.getItem('pustika_reader_size'), 10) || 18;

    setReaderTheme(savedTheme);
    changeReaderFont(savedFont);
    standaloneReaderState.fontSize = savedSize;
    applyFontSize();
}

function changeStandalonePage(delta) {
    const target = standaloneReaderState.currentPage + delta;
    if (target >= 1 && target <= standaloneReaderState.totalPages) {
        switchStandalonePage(target);
    }
}

function jumpStandalonePage() {
    const input = document.getElementById('reader-jump-input');
    if (!input) return;
    const target = parseInt(input.value, 10);
    if (!isNaN(target) && target >= 1 && target <= standaloneReaderState.totalPages) {
        switchStandalonePage(target);
    } else {
        alert(`Please enter a page between 1 and ${standaloneReaderState.totalPages}`);
    }
}

function switchStandalonePage(targetPage) {
    if (targetPage < 1 || targetPage > standaloneReaderState.totalPages) return;
    const direction = targetPage >= standaloneReaderState.currentPage ? 'next' : 'prev';
    standaloneReaderState.currentPage = targetPage;

    // Check if we have preloaded page object
    if (standaloneReaderState.pages && standaloneReaderState.pages.length > 0) {
        const pageObj = standaloneReaderState.pages.find(p => p.page_number === targetPage) || standaloneReaderState.pages[targetPage - 1];
        if (pageObj) {
            renderStandalonePage(pageObj, direction);
            // Update URL without full page reload
            try {
                const newUrl = new URL(window.location.href);
                newUrl.searchParams.set('page', targetPage);
                window.history.replaceState({ page: targetPage }, '', newUrl.toString());
            } catch (err) {}
            return;
        }
    }

    // Fallback: navigate via URL
    window.location.href = `/read/${standaloneReaderState.bookId}?page=${targetPage}`;
}

function renderStandalonePage(pageObj, direction = 'next') {
    const textEl = document.getElementById('reader-text');
    const badgeEl = document.getElementById('reader-page-badge');
    const titleEl = document.getElementById('reader-page-title');
    const footerEl = document.getElementById('reader-page-footer');
    const curNavEl = document.getElementById('reader-nav-cur');
    const labelEl = document.getElementById('reader-dropdown-label');
    const prevBtn = document.getElementById('reader-prev-btn');
    const nextBtn = document.getElementById('reader-next-btn');
    const cardSurface = document.getElementById('reader-content-card');

    const curPage = pageObj.page_number;
    const totalPages = standaloneReaderState.totalPages;

    // 1. Text and labels
    if (textEl) textEl.innerHTML = (pageObj.text_content || '').replace(/\n/g, '<br>');
    if (badgeEl) badgeEl.textContent = `Page ${curPage} of ${totalPages}`;
    if (titleEl) titleEl.textContent = pageObj.title;
    if (footerEl) footerEl.textContent = `Page ${curPage} of ${totalPages}`;
    if (curNavEl) curNavEl.textContent = curPage;
    if (labelEl) labelEl.textContent = pageObj.title;

    // 2. Buttons enable/disable
    if (prevBtn) {
        prevBtn.disabled = curPage <= 1;
        prevBtn.style.opacity = curPage <= 1 ? '0.4' : '1';
    }
    if (nextBtn) {
        nextBtn.disabled = curPage >= totalPages;
        nextBtn.style.opacity = curPage >= totalPages ? '0.4' : '1';
    }

    // 3. Dropdown active item highlight
    const menuItems = document.querySelectorAll('#reader-dropdown-menu a.dropdown-item');
    menuItems.forEach((item, idx) => {
        if (idx === (curPage - 1)) {
            item.classList.add('active', 'fw-bold');
        } else {
            item.classList.remove('active', 'fw-bold');
        }
    });

    // 4. Trigger Realistic 3D Page Turn Animation
    if (cardSurface) {
        cardSurface.classList.remove('anim-page-flip-next', 'anim-page-flip-prev');
        void cardSurface.offsetWidth; // Force browser reflow to restart animation
        const animClass = (direction === 'prev') ? 'anim-page-flip-prev' : 'anim-page-flip-next';
        cardSurface.classList.add(animClass);
        setTimeout(() => {
            cardSurface.classList.remove('anim-page-flip-next', 'anim-page-flip-prev');
        }, 460);
    }

    // 5. Scroll smoothly to top of book if scrolled down
    const rootEl = document.getElementById('reader-root');
    if (rootEl && window.scrollY > 200) {
        rootEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

/* --------------------------------------------------------------------------
   Customization: Themes, Fonts, and Font Sizing
   -------------------------------------------------------------------------- */
function setReaderTheme(theme) {
    standaloneReaderState.theme = theme;
    localStorage.setItem('pustika_reader_theme', theme);

    const card = document.getElementById('reader-content-card');
    if (!card) return;

    card.classList.remove('theme-light', 'theme-sepia', 'theme-night', 'bg-white', 'bg-dark', 'text-white');
    
    if (theme === 'sepia') {
        card.classList.add('theme-sepia');
        card.style.backgroundColor = '#fbf0d9';
        card.style.color = '#5f4b32';
    } else if (theme === 'night') {
        card.classList.add('theme-night');
        card.style.backgroundColor = '#181a1b';
        card.style.color = '#e8e6e3';
    } else {
        card.classList.add('theme-light');
        card.style.backgroundColor = '#ffffff';
        card.style.color = '#2b2523';
    }
}

function changeReaderFont(family) {
    standaloneReaderState.fontFamily = family;
    localStorage.setItem('pustika_reader_font', family);

    const textEl = document.getElementById('reader-text');
    if (!textEl) return;

    textEl.classList.remove('font-sans', 'font-serif', 'font-mono');
    if (family === 'sans-serif') {
        textEl.style.fontFamily = 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    } else if (family === 'monospace') {
        textEl.style.fontFamily = '"Fira Code", monospace, "Courier New"';
    } else {
        textEl.style.fontFamily = 'Merriweather, Georgia, "Times New Roman", serif';
    }
}

function adjustFontSize(delta) {
    standaloneReaderState.fontSize = Math.min(Math.max(14, standaloneReaderState.fontSize + delta), 36);
    localStorage.setItem('pustika_reader_size', standaloneReaderState.fontSize);
    applyFontSize();
}

function applyFontSize() {
    const textEl = document.getElementById('reader-text');
    if (textEl) {
        textEl.style.fontSize = `${standaloneReaderState.fontSize}px`;
        textEl.style.lineHeight = (standaloneReaderState.fontSize > 24) ? '1.6' : '1.8';
    }
}
