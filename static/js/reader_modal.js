/* ==========================================================================
   Pustika Interactive Reader & Player Modal Engine
   ========================================================================== */

let pustikaModalState = {
    book: null,
    chapters: [],
    currentChapterIndex: 0,
    currentPageIndex: 1,
    totalPages: 1,
    mode: 'text', // 'text', 'audio', 'both'
    fontScale: 100,
    theme: 'light', // 'light', 'sepia', 'dark'
    playbackSpeed: 1.0,
    isPlaying: false,
    selectedVoice: 'rachel',
    selectedVoiceLabel: 'Rachel (AI)'
};

function selectNarratorVoice(voiceId, voiceLabel) {
    pustikaModalState.selectedVoice = voiceId;
    pustikaModalState.selectedVoiceLabel = voiceLabel;
    
    const labelEl = document.getElementById('pm-selected-voice-label');
    const subtitleEl = document.getElementById('pm-active-voice-subtitle');
    if (labelEl) labelEl.textContent = voiceLabel;
    if (subtitleEl) subtitleEl.textContent = voiceLabel;
    
    const menuLinks = document.querySelectorAll('#pm-voice-menu a');
    menuLinks.forEach(link => {
        if (link.getAttribute('onclick') && link.getAttribute('onclick').includes(voiceId)) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });

    showToast('Narrator Voice Changed', `AI Narrator switched to ${voiceLabel}`, 'info');
}

let currentActiveBookId = 1;

document.addEventListener('DOMContentLoaded', () => {
    initPustikaModalEvents();
});

function initPustikaModalEvents() {
    const audioEl = document.getElementById('pm-native-audio-player');
    const seekEl = document.getElementById('pm-audio-seek');

    if (audioEl) {
        audioEl.addEventListener('timeupdate', () => {
            if (!audioEl.duration) return;
            const progress = (audioEl.currentTime / audioEl.duration) * 100;
            if (seekEl) seekEl.value = progress;
            
            const curTimeSpan = document.getElementById('pm-audio-current-time');
            const durTimeSpan = document.getElementById('pm-audio-duration');
            if (curTimeSpan) curTimeSpan.textContent = formatTime(audioEl.currentTime);
            if (durTimeSpan) durTimeSpan.textContent = formatTime(audioEl.duration);

            // Sync audio with text highlighting in 'both' mode
            if (pustikaModalState.mode === 'both') {
                highlightSyncedParagraph(audioEl.currentTime, audioEl.duration);
            }
        });

        audioEl.addEventListener('ended', () => {
            pustikaModalState.isPlaying = false;
            updatePlayButtonIcon(false);
            // Auto advance chapter if available
            if (pustikaModalState.currentChapterIndex < pustikaModalState.chapters.length - 1) {
                switchChapter(pustikaModalState.currentChapterIndex + 1);
            }
        });
    }

    // Clean up audio when modal closes
    const modalEl = document.getElementById('pustikaReaderModal');
    if (modalEl) {
        modalEl.addEventListener('hidden.bs.modal', () => {
            if (audioEl) {
                audioEl.pause();
                pustikaModalState.isPlaying = false;
            }
        });
    }
}

/* --------------------------------------------------------------------------
   Laptop View Floating Reader Window Functions
   -------------------------------------------------------------------------- */
async function selectBookForReader(bookId) {
    currentActiveBookId = bookId;
    toggleFloatingReader(true);
    
    try {
        const response = await fetch(`/api/book/${bookId}/full_details`);
        if (!response.ok) return;
        const data = await response.json();
        
        pustikaModalState.book = data;
        pustikaModalState.chapters = data.chapters || [];

        const titleEl = document.getElementById('fr-title');
        const authorEl = document.getElementById('fr-author');
        const coverEl = document.getElementById('fr-cover');
        const headingEl = document.getElementById('fr-chapter-heading');
        const contentEl = document.getElementById('fr-text-content');
        
        if (titleEl) titleEl.textContent = data.title;
        if (authorEl) authorEl.textContent = data.author;
        if (coverEl) coverEl.src = data.cover_url;
        
        if (data.chapters && data.chapters.length > 0) {
            const chap = data.chapters[0];
            if (headingEl) headingEl.textContent = chap.title.replace(/^.*Chapter \d+:?\s*/i, '') || chap.title;
            if (contentEl) {
                const paragraphs = chap.text_content.split(/\n\s*\n/).filter(p => p.trim() !== '');
                contentEl.innerHTML = paragraphs.slice(0, 3).map(p => `<p class="mb-3">${escapeHtml(p)}</p>`).join('');
            }
        }
    } catch (e) {
        console.error("Error updating floating reader:", e);
    }
}

function toggleFloatingReader(show) {
    const el = document.getElementById('floatingReaderOverlay');
    if (!el) return;
    if (show) {
        el.style.display = 'block';
        el.style.opacity = '1';
    } else {
        el.style.display = 'none';
    }
}

/* --------------------------------------------------------------------------
   Open Book Modal via API
   -------------------------------------------------------------------------- */
async function openPustikaBookModal(bookId, defaultMode = 'text') {
    try {
        const response = await fetch(`/api/book/${bookId}/full_details`);
        if (!response.ok) throw new Error('Book details fetch failed');

        const data = await response.json();
        pustikaModalState.book = data;
        pustikaModalState.chapters = data.chapters || [];
        pustikaModalState.currentChapterIndex = 0;
        pustikaModalState.currentPageIndex = data.last_page || 1;
        pustikaModalState.mode = defaultMode;

        // Header info
        document.getElementById('pm-book-title').textContent = data.title;
        document.getElementById('pm-book-author').textContent = `By ${data.author}`;
        document.getElementById('pm-cover-img').src = data.cover_url;

        // Favorite icon
        const favBtnIcon = document.querySelector('#pm-fav-btn i');
        if (favBtnIcon) {
            favBtnIcon.className = data.is_favorited ? 'bi bi-heart-fill text-danger fs-5' : 'bi bi-heart fs-5';
        }

        // Chapter Menu
        populateChapterDropdown();

        // Render current chapter
        loadChapterContent(0);

        // Mode set
        setReaderMode(defaultMode);

        // Show Bootstrap Modal
        const bsModal = new bootstrap.Modal(document.getElementById('pustikaReaderModal'));
        bsModal.show();

    } catch (err) {
        console.error('Error launching Pustika modal:', err);
        showToast('Error', 'Unable to open book. Please try again.', 'danger');
    }
}

/* --------------------------------------------------------------------------
   Chapter & Content Rendering
   -------------------------------------------------------------------------- */
function populateChapterDropdown() {
    const menuEl = document.getElementById('pm-chapter-menu');
    if (!menuEl) return;

    menuEl.innerHTML = pustikaModalState.chapters.map((ch, idx) => `
        <li>
            <a class="dropdown-item ${idx === pustikaModalState.currentChapterIndex ? 'active fw-bold' : ''}" href="#" onclick="switchChapter(${idx}); return false;">
                Ch ${ch.chapter_number}: ${ch.title}
            </a>
        </li>
    `).join('');
}

function switchChapter(idx) {
    if (idx < 0 || idx >= pustikaModalState.chapters.length) return;
    pustikaModalState.currentChapterIndex = idx;
    pustikaModalState.currentPageIndex = 1;
    populateChapterDropdown();
    loadChapterContent(idx);
}

function loadChapterContent(idx) {
    const chap = pustikaModalState.chapters[idx];
    if (!chap) return;

    document.getElementById('pm-chapter-badge').textContent = `Chapter ${chap.chapter_number}`;
    document.getElementById('pm-chapter-heading').textContent = chap.title;
    document.getElementById('pm-current-chapter-title').textContent = `Ch ${chap.chapter_number}: ${chap.title}`;

    // Load Audio source
    const audioEl = document.getElementById('pm-native-audio-player');
    const audioTitle = document.getElementById('pm-audio-title');
    if (chap.audio && chap.audio.audio_url) {
        if (audioEl) audioEl.src = chap.audio.audio_url;
        if (audioTitle) audioTitle.textContent = `${chap.title}`;
    } else {
        if (audioEl) audioEl.src = '';
        if (audioTitle) audioTitle.textContent = `${chap.title} (No Audio File)`;
    }

    // Process & pagination of text
    const paragraphs = chap.text_content.split(/\n\s*\n/).filter(p => p.trim() !== '');
    const chunkSize = 3;
    const pages = [];
    for (let i = 0; i < paragraphs.length; i += chunkSize) {
        pages.push(paragraphs.slice(i, i + chunkSize));
    }

    pustikaModalState.pages = pages.length > 0 ? pages : [[chap.text_content]];
    pustikaModalState.totalPages = pustikaModalState.pages.length;

    renderPageContent();
}

function renderPageContent() {
    const pages = pustikaModalState.pages || [];
    const curIdx = pustikaModalState.currentPageIndex - 1;
    const curParagraphs = pages[curIdx] || [];

    const bodyEl = document.getElementById('pm-text-body');
    if (bodyEl) {
        bodyEl.innerHTML = curParagraphs.map((p, pIdx) => `
            <p class="pm-paragraph mb-4" data-para-index="${pIdx}">${escapeHtml(p)}</p>
        `).join('');
    }

    const cp = document.getElementById('pm-current-page');
    const tp = document.getElementById('pm-total-pages');
    const fp = document.getElementById('pm-footer-page');
    if (cp) cp.textContent = pustikaModalState.currentPageIndex;
    if (tp) tp.textContent = pustikaModalState.totalPages;
    if (fp) fp.textContent = pustikaModalState.currentPageIndex;
}

function changeReaderPage(delta) {
    const newPage = pustikaModalState.currentPageIndex + delta;
    if (newPage >= 1 && newPage <= pustikaModalState.totalPages) {
        pustikaModalState.currentPageIndex = newPage;
        renderPageContent();
    }
}

/* --------------------------------------------------------------------------
   Reader Mode Switcher (Text, Audio, Both)
   -------------------------------------------------------------------------- */
function setReaderMode(mode) {
    pustikaModalState.mode = mode;

    const btnText = document.getElementById('pm-mode-text');
    const btnAudio = document.getElementById('pm-mode-audio');
    const btnBoth = document.getElementById('pm-mode-both');
    const paperSurface = document.getElementById('pm-paper-surface');
    const audioWrapper = document.getElementById('pm-audio-player-wrapper');

    [btnText, btnAudio, btnBoth].forEach(b => b && b.classList.remove('active-mode', 'bg-white', 'shadow-sm', 'fw-bold'));

    if (mode === 'text') {
        if (btnText) btnText.classList.add('active-mode', 'bg-white', 'shadow-sm', 'fw-bold');
        if (paperSurface) paperSurface.classList.remove('d-none');
        if (audioWrapper) audioWrapper.classList.add('d-none');
    } else if (mode === 'audio') {
        if (btnAudio) btnAudio.classList.add('active-mode', 'bg-white', 'shadow-sm', 'fw-bold');
        if (paperSurface) paperSurface.classList.add('d-none');
        if (audioWrapper) audioWrapper.classList.remove('d-none');
    } else if (mode === 'both') {
        if (btnBoth) btnBoth.classList.add('active-mode', 'bg-white', 'shadow-sm', 'fw-bold');
        if (paperSurface) paperSurface.classList.remove('d-none');
        if (audioWrapper) audioWrapper.classList.remove('d-none');
    }
}

/* --------------------------------------------------------------------------
   Audio Playback Controls
   -------------------------------------------------------------------------- */
function toggleModalAudioPlayback() {
    const audioEl = document.getElementById('pm-native-audio-player');
    if (!audioEl || !audioEl.src) {
        showToast('Audio', 'No audio file generated for this chapter yet.', 'warning');
        return;
    }

    if (audioEl.paused) {
        audioEl.play();
        pustikaModalState.isPlaying = true;
        updatePlayButtonIcon(true);
    } else {
        audioEl.pause();
        pustikaModalState.isPlaying = false;
        updatePlayButtonIcon(false);
    }
}

function updatePlayButtonIcon(isPlaying) {
    const iconEl = document.getElementById('pm-audio-play-icon');
    if (iconEl) {
        iconEl.className = isPlaying ? 'bi bi-pause-fill' : 'bi bi-play-fill';
    }
}

function seekModalAudio(percent) {
    const audioEl = document.getElementById('pm-native-audio-player');
    if (audioEl && audioEl.duration) {
        audioEl.currentTime = (percent / 100) * audioEl.duration;
    }
}

function setModalAudioVolume(vol) {
    const audioEl = document.getElementById('pm-native-audio-player');
    if (audioEl) audioEl.volume = vol;
}

function changePlaybackSpeed() {
    const audioEl = document.getElementById('pm-native-audio-player');
    const speedBtn = document.getElementById('pm-speed-btn');

    const speeds = [1.0, 1.25, 1.5, 2.0, 0.8];
    let nextIdx = (speeds.indexOf(pustikaModalState.playbackSpeed) + 1) % speeds.length;
    pustikaModalState.playbackSpeed = speeds[nextIdx];

    if (audioEl) audioEl.playbackRate = pustikaModalState.playbackSpeed;
    if (speedBtn) speedBtn.textContent = `${pustikaModalState.playbackSpeed}x`;
}

function highlightSyncedParagraph(currentTime, duration) {
    const paragraphs = document.querySelectorAll('.pm-paragraph');
    if (!paragraphs.length || !duration) return;

    const currentFraction = currentTime / duration;
    const activeParaIndex = Math.min(Math.floor(currentFraction * paragraphs.length), paragraphs.length - 1);

    paragraphs.forEach((p, idx) => {
        if (idx === activeParaIndex) {
            p.classList.add('synced-highlight');
        } else {
            p.classList.remove('synced-highlight');
        }
    });
}

/* --------------------------------------------------------------------------
   Font Scaling & Theme Switcher
   -------------------------------------------------------------------------- */
function adjustFontScale(delta) {
    let newScale = pustikaModalState.fontScale + delta;
    if (newScale < 80) newScale = 80;
    if (newScale > 160) newScale = 160;

    pustikaModalState.fontScale = newScale;
    const fsEl = document.getElementById('pm-font-scale');
    const fzEl = document.getElementById('fr-zoom');
    if (fsEl) fsEl.textContent = `${newScale}%`;
    if (fzEl) fzEl.textContent = `${newScale}%`;

    const bodyEl = document.getElementById('pm-text-body');
    const frBodyEl = document.getElementById('fr-text-content');
    if (bodyEl) bodyEl.style.fontSize = `${(1.15 * (newScale / 100)).toFixed(2)}rem`;
    if (frBodyEl) frBodyEl.style.fontSize = `${(1.0 * (newScale / 100)).toFixed(2)}rem`;
}

function toggleReaderTheme() {
    const paperSurface = document.getElementById('pm-paper-surface');
    const frPaperSurface = document.getElementById('fr-body-paper');
    const themes = ['light', 'sepia', 'dark'];
    let nextIdx = (themes.indexOf(pustikaModalState.theme) + 1) % themes.length;
    pustikaModalState.theme = themes[nextIdx];

    [paperSurface, frPaperSurface].forEach(surf => {
        if (surf) {
            surf.classList.remove('theme-sepia', 'theme-dark');
            if (pustikaModalState.theme === 'sepia') surf.classList.add('theme-sepia');
            if (pustikaModalState.theme === 'dark') surf.classList.add('theme-dark');
        }
    });
}

function toggleModalFullscreen() {
    const modalDialog = document.querySelector('#pustikaReaderModal .modal-dialog');
    if (modalDialog) {
        modalDialog.classList.toggle('modal-fullscreen');
    }
}

async function handleModalFavoriteToggle() {
    if (!pustikaModalState.book) return;
    const bookId = pustikaModalState.book.id;
    const favBtn = document.getElementById('pm-fav-btn');
    await toggleFavorite(bookId, favBtn);
    pustikaModalState.book.is_favorited = !pustikaModalState.book.is_favorited;
}

function formatTime(seconds) {
    if (isNaN(seconds)) return '00:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function escapeHtml(text) {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return text.replace(/[&<>"']/g, m => map[m]);
}
