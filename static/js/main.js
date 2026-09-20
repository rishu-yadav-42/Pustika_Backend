/* ==========================================================================
   Main Application Script - Theme Engine, Language Switcher, Toast Notifications
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    initThemeManager();
    initLanguageEngine();
});

/* --------------------------------------------------------------------------
   1. Dark Mode & Theme Manager
   -------------------------------------------------------------------------- */
function initThemeManager() {
    const themeToggleBtn = document.getElementById('theme-toggle-btn');
    const themeIcon = document.getElementById('theme-toggle-icon');
    
    const savedTheme = localStorage.getItem('theme') || 
                      (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
                      
    applyTheme(savedTheme);

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            applyTheme(newTheme);
            localStorage.setItem('theme', newTheme);
        });
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        if (themeIcon) {
            if (theme === 'dark') {
                themeIcon.className = 'bi bi-sun-fill text-warning';
            } else {
                themeIcon.className = 'bi bi-moon-stars-fill text-primary';
            }
        }
    }
}

/* --------------------------------------------------------------------------
   2. Hindi & English Client-Side Language Switcher
   -------------------------------------------------------------------------- */
const i18nDict = {
    en: {
        nav_home: "Home",
        nav_books: "Explore Books",
        nav_categories: "Categories",
        nav_favorites: "My Favorites",
        nav_history: "Reading History",
        nav_admin: "Admin Dashboard",
        nav_login: "Sign In",
        nav_register: "Register",
        nav_logout: "Logout",
        search_placeholder: "Search title, author, category...",
        hero_title: "Discover Your Next Favorite Book & Audiobook",
        hero_subtitle: "Listen to natural AI voices in English & Hindi, or read distraction-free online.",
        btn_read_now: "Read Now",
        btn_listen_audio: "Listen Audiobook",
        btn_add_favorite: "Favorite",
        btn_convert_audio: "Convert Text to Audio",
        section_featured: "Featured Audiobooks",
        section_hindi: "Popular Hindi Books (हिंदी पुस्तकें)",
        section_english: "Top English Audiobooks",
        label_author: "Author",
        label_category: "Category",
        label_language: "Language",
        label_chapters: "Chapters",
        label_duration: "Duration"
    },
    hi: {
        nav_home: "मुख्य पृष्ठ",
        nav_books: "पुस्तके खोजें",
        nav_categories: "श्रेणियाँ",
        nav_favorites: "पसंदीदा किताबें",
        nav_history: "पठन इतिहास",
        nav_admin: "एडमिन डैशबोर्ड",
        nav_login: "लॉग इन",
        nav_register: "रजिस्टर",
        nav_logout: "लॉग आउट",
        search_placeholder: "शीर्षक, लेखक, श्रेणी खोजें...",
        hero_title: "अपनी पसंदीदा ई-पुस्तकें और ऑडियोबुक्स सुनें व पढ़ें",
        hero_subtitle: "हिंदी और अंग्रेजी में प्राकृतिक आवाज में ऑडियोबुक सुनें या ऑनलाइन पढ़ें।",
        btn_read_now: "अभी पढ़ें",
        btn_listen_audio: "ऑडियोबुक सुनें",
        btn_add_favorite: "पसंदीदा में जोड़ें",
        btn_convert_audio: "टेक्स्ट को ऑडियो में बदलें",
        section_featured: "प्रमुख ऑडियोबुक्स",
        section_hindi: "लोकप्रिय हिंदी पुस्तकें",
        section_english: "शीर्ष अंग्रेजी पुस्तकें",
        label_author: "लेखक",
        label_category: "श्रेणी",
        label_language: "भाषा",
        label_chapters: "अध्याय",
        label_duration: "अवधि"
    }
};

function initLanguageEngine() {
    const langBtn = document.getElementById('lang-toggle-btn');
    const currentLangSpan = document.getElementById('current-lang-text');
    
    let activeLang = localStorage.getItem('site_lang') || 'en';
    applyLanguage(activeLang);

    if (langBtn) {
        langBtn.addEventListener('click', () => {
            activeLang = activeLang === 'en' ? 'hi' : 'en';
            localStorage.setItem('site_lang', activeLang);
            applyLanguage(activeLang);
        });
    }

    function applyLanguage(lang) {
        if (currentLangSpan) {
            currentLangSpan.textContent = lang === 'en' ? 'EN / हिंदी' : 'हिंदी / EN';
        }
        
        const langElements = document.querySelectorAll('[data-i18n]');
        langElements.forEach(el => {
            const key = el.getAttribute('data-i18n');
            if (i18nDict[lang] && i18nDict[lang][key]) {
                if (el.tagName === 'INPUT' && el.type === 'text') {
                    el.placeholder = i18nDict[lang][key];
                } else {
                    el.textContent = i18nDict[lang][key];
                }
            }
        });
    }
}

/* --------------------------------------------------------------------------
   3. Toggle Favorite AJAX Call
   -------------------------------------------------------------------------- */
async function toggleFavorite(bookId, buttonEl) {
    try {
        const response = await fetch('/api/favorite/toggle', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ book_id: bookId })
        });
        
        const data = await response.json();
        if (response.ok && data.success) {
            const icon = buttonEl.querySelector('i');
            if (data.is_favorited) {
                if (icon) icon.className = 'bi bi-heart-fill text-danger';
                showToast('Success', 'Added to your favorites!', 'success');
            } else {
                if (icon) icon.className = 'bi bi-heart text-secondary';
                showToast('Info', 'Removed from your favorites.', 'info');
            }
        } else {
            showToast('Authentication Required', data.message || 'Please log in to save favorites.', 'warning');
        }
    } catch (err) {
        console.error('Error toggling favorite:', err);
    }
}

/* --------------------------------------------------------------------------
   4. Toast Notification Utility
   -------------------------------------------------------------------------- */
function showToast(title, message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const bgClass = type === 'success' ? 'bg-success text-white' :
                    type === 'danger' ? 'bg-danger text-white' :
                    type === 'warning' ? 'bg-warning text-dark' : 'bg-primary text-white';

    const toastHtml = `
        <div class="toast align-items-center ${bgClass} border-0 show shadow-lg mb-2" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    <strong>${title}:</strong> ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;
    
    container.insertAdjacentHTML('beforeend', toastHtml);
    const toasts = container.querySelectorAll('.toast');
    const latestToast = toasts[toasts.length - 1];
    setTimeout(() => {
        latestToast.remove();
    }, 4000);
}
