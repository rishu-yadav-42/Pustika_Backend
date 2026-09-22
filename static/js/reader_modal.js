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

    // Keyboard navigation (Left/Right arrow keys to turn pages)
    document.addEventListener('keydown', (e) => {
        if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;
        const modalEl = document.getElementById('pustikaReaderModal');
        const isModalOpen = modalEl && (modalEl.classList.contains('show') || modalEl.style.display === 'block');
        const frEl = document.getElementById('floatingReaderOverlay');
        const isFrOpen = frEl && frEl.style.display === 'block';

        if (isModalOpen || isFrOpen) {
            if (e.key === 'ArrowLeft') {
                e.preventDefault();
                changeReaderPage(-1);
            } else if (e.key === 'ArrowRight') {
                e.preventDefault();
                changeReaderPage(1);
            }
        }
    });
}

/* --------------------------------------------------------------------------
   PDF / Page Preparation Engine (1:1 Exact PDF Page Mapping)
   -------------------------------------------------------------------------- */
function prepareBookPages(data) {
    const chaps = data.chapters || [];
    if (!chaps.length) {
        return [{ pageNumber: 1, title: 'Page 1', content: [data.description || 'No content available.'] }];
    }

    const isPdfOrMultiPage = data.is_pdf || chaps.length > 1 || (chaps[0].title && chaps[0].title.toLowerCase().startsWith('page '));

    if (isPdfOrMultiPage) {
        // EXACT 1:1 Sequential Page Mapping: each entry in chapters IS an exact page!
        return chaps.map((ch, idx) => {
            const lines = (ch.text_content || '').split(/\n\s*\n/).map(l => l.trim()).filter(l => l.length > 0);
            return {
                pageNumber: ch.chapter_number || (idx + 1),
                title: ch.title || `Page ${idx + 1}`,
                content: lines.length > 0 ? lines : [ch.text_content || `[Page ${idx + 1}]`],
                audio: ch.audio || null
            };
        });
    } else {
        // Single chapter text splitting
        const text = chaps[0].text_content || data.description || '';
        const paragraphs = text.split(/\n\s*\n/).map(p => p.trim()).filter(p => p !== '');
        const chunkSize = 3;
        const pages = [];
        let pNum = 1;
        for (let i = 0; i < paragraphs.length; i += chunkSize) {
            pages.push({
                pageNumber: pNum,
                title: `Page ${pNum}`,
                content: paragraphs.slice(i, i + chunkSize),
                audio: chaps[0].audio || null
            });
            pNum++;
        }
        return pages.length > 0 ? pages : [{ pageNumber: 1, title: 'Page 1', content: [text], audio: chaps[0].audio || null }];
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
        pustikaModalState.bookPages = prepareBookPages(data);
        pustikaModalState.totalPages = pustikaModalState.bookPages.length;
        pustikaModalState.currentPageIndex = Math.min(Math.max(1, data.last_page || 1), pustikaModalState.totalPages);

        const titleEl = document.getElementById('fr-title');
        const authorEl = document.getElementById('fr-author');
        const coverEl = document.getElementById('fr-cover');
        
        if (titleEl) titleEl.textContent = data.title;
        if (authorEl) authorEl.textContent = data.author;
        if (coverEl) coverEl.src = data.cover_url;
        
        renderPageContent('next');
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
        pustikaModalState.bookPages = prepareBookPages(data);
        pustikaModalState.totalPages = pustikaModalState.bookPages.length;
        pustikaModalState.currentPageIndex = Math.min(Math.max(1, data.last_page || 1), pustikaModalState.totalPages);
        pustikaModalState.mode = defaultMode;

        // Header info
        const titleEl = document.getElementById('pm-book-title');
        const authorEl = document.getElementById('pm-book-author');
        const coverEl = document.getElementById('pm-cover-img');
        if (titleEl) titleEl.textContent = data.title;
        if (authorEl) authorEl.textContent = `By ${data.author}`;
        if (coverEl) coverEl.src = data.cover_url;

        // Favorite icon
        const favBtnIcon = document.querySelector('#pm-fav-btn i');
        if (favBtnIcon) {
            favBtnIcon.className = data.is_favorited ? 'bi bi-heart-fill text-danger fs-5' : 'bi bi-heart fs-5';
        }

        // Chapter / Page Dropdown
        populateChapterDropdown();

        // Render current page content
        renderPageContent('next');

        // Mode set
        setReaderMode(defaultMode);

        // Show Bootstrap Modal
        const modalDom = document.getElementById('pustikaReaderModal');
        if (modalDom) {
            const bsModal = bootstrap.Modal.getInstance(modalDom) || new bootstrap.Modal(modalDom);
            bsModal.show();
        }

    } catch (err) {
        console.error('Error launching Pustika modal:', err);
        showToast('Error', 'Unable to open book. Please try again.', 'danger');
    }
}

/* --------------------------------------------------------------------------
   Page / Chapter Dropdown Navigation
   -------------------------------------------------------------------------- */
function populateChapterDropdown() {
    const menuEl = document.getElementById('pm-chapter-menu');
    if (!menuEl) return;

    const pages = pustikaModalState.bookPages || [];
    const curIdx = pustikaModalState.currentPageIndex - 1;

    let jumpHtml = '';
    if (pages.length > 3) {
        jumpHtml = `
            <li class="px-3 py-2 border-bottom sticky-top bg-white">
                <div class="input-group input-group-sm">
                    <input type="number" id="pm-jump-page-input" class="form-control form-control-sm" placeholder="Go to Page (1-${pages.length})" min="1" max="${pages.length}" onkeydown="if(event.key==='Enter'){jumpToReaderPage();}">
                    <button class="btn btn-warning btn-sm fw-bold px-2" type="button" onclick="jumpToReaderPage()">Go</button>
                </div>
            </li>
        `;
    }

    const itemsHtml = pages.map((pg, idx) => `
        <li>
            <a class="dropdown-item ${idx === curIdx ? 'active fw-bold' : ''}" href="#" onclick="jumpToReaderPageNumber(${idx + 1}); return false;">
                ${pg.title}
            </a>
        </li>
    `).join('');

    menuEl.innerHTML = jumpHtml + itemsHtml;
}

function jumpToReaderPage() {
    const input = document.getElementById('pm-jump-page-input');
    if (!input) return;
    const val = parseInt(input.value, 10);
    if (!isNaN(val) && val >= 1 && val <= pustikaModalState.totalPages) {
        jumpToReaderPageNumber(val);
    } else {
        showToast('Invalid Page', `Please enter a page between 1 and ${pustikaModalState.totalPages}`, 'warning');
    }
}

function jumpToReaderPageNumber(targetPage) {
    if (targetPage < 1 || targetPage > pustikaModalState.totalPages) return;
    const direction = targetPage >= pustikaModalState.currentPageIndex ? 'next' : 'prev';
    pustikaModalState.currentPageIndex = targetPage;
    populateChapterDropdown();
    renderPageContent(direction);
}

function switchChapter(idx) {
    jumpToReaderPageNumber(idx + 1);
}

/* --------------------------------------------------------------------------
   Page Content Rendering & 3D Realistic Page Turn Animation
   -------------------------------------------------------------------------- */
function renderPageContent(direction = 'next') {
    const pages = pustikaModalState.bookPages || [];
    const curIdx = pustikaModalState.currentPageIndex - 1;
    const pageObj = pages[curIdx] || { pageNumber: curIdx + 1, title: `Page ${curIdx + 1}`, content: [] };
    const paragraphs = pageObj.content || [];
    const totalPages = pustikaModalState.totalPages || 1;
    const curPage = pustikaModalState.currentPageIndex;

    // 1. Update PM Modal Badges & Titles
    const badgeEl = document.getElementById('pm-chapter-badge');
    const headingEl = document.getElementById('pm-chapter-heading');
    const curChapTitleEl = document.getElementById('pm-current-chapter-title');
    
    if (badgeEl) badgeEl.textContent = `PAGE ${curPage} OF ${totalPages}`;
    if (headingEl) headingEl.textContent = `${pustikaModalState.book ? pustikaModalState.book.title + ' - ' : ''}${pageObj.title}`;
    if (curChapTitleEl) curChapTitleEl.textContent = `${pageObj.title}`;

    // 2. Audio source update if page has audio
    const audioEl = document.getElementById('pm-native-audio-player');
    const audioTitle = document.getElementById('pm-audio-title');
    if (pageObj.audio && pageObj.audio.audio_url) {
        if (audioEl) audioEl.src = pageObj.audio.audio_url;
        if (audioTitle) audioTitle.textContent = `${pageObj.title}`;
    } else {
        if (audioEl) audioEl.src = '';
        if (audioTitle) audioTitle.textContent = `${pageObj.title} (No Audio File)`;
    }

    // 3. Update PM Modal Body text
    const bodyEl = document.getElementById('pm-text-body');
    const pmSurface = document.getElementById('pm-paper-surface');
    if (bodyEl) {
        bodyEl.innerHTML = paragraphs.map((p, pIdx) => `
            <p class="pm-paragraph mb-4" data-para-index="${pIdx}">${escapeHtml(p)}</p>
        `).join('');
    }

    // 4. Update Floating Reader Body text & Badges
    const frContentEl = document.getElementById('fr-text-content');
    const frSurface = document.getElementById('fr-body-paper') || document.getElementById('fr-body-paper-container');
    const frBadgeEl = document.getElementById('fr-chapter-badge');
    const frHeadingEl = document.getElementById('fr-chapter-heading');
    if (frBadgeEl) frBadgeEl.textContent = `PAGE ${curPage} OF ${totalPages}`;
    if (frHeadingEl) frHeadingEl.textContent = pageObj.title;
    if (frContentEl) {
        frContentEl.innerHTML = paragraphs.map(p => `
            <p class="mb-3">${escapeHtml(p)}</p>
        `).join('');
    }

    // 5. Apply Realistic 3D Page Turn Animation
    [pmSurface, frSurface].forEach(surf => {
        if (surf) {
            surf.classList.remove('anim-page-flip-next', 'anim-page-flip-prev');
            // Force browser reflow to trigger animation cleanly every time
            void surf.offsetWidth;
            const animClass = (direction === 'prev') ? 'anim-page-flip-prev' : 'anim-page-flip-next';
            surf.classList.add(animClass);
            setTimeout(() => {
                surf.classList.remove('anim-page-flip-next', 'anim-page-flip-prev');
            }, 460);
        }
    });

    // 6. Update all page counters
    const cp = document.getElementById('pm-current-page');
    const tp = document.getElementById('pm-total-pages');
    const fp = document.getElementById('pm-footer-page');
    const frPage = document.getElementById('fr-page-num');
    const frTotal = document.getElementById('fr-total-pages');
    const frFooter = document.getElementById('fr-footer-page');

    if (cp) cp.textContent = curPage;
    if (tp) tp.textContent = totalPages;
    if (fp) fp.textContent = curPage;

    if (frPage) frPage.textContent = curPage;
    if (frTotal) frTotal.textContent = totalPages;
    if (frFooter) frFooter.textContent = curPage;

    // 7. Save reading progress to server
    if (pustikaModalState.book) {
        saveReadingProgress(pustikaModalState.book.id, curPage);
    }
}

function changeReaderPage(delta) {
    const target = pustikaModalState.currentPageIndex + delta;
    if (target >= 1 && target <= pustikaModalState.totalPages) {
        jumpToReaderPageNumber(target);
    }
}

function saveReadingProgress(bookId, pageNumber) {
    fetch('/api/user/history', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ book_id: bookId, page_number: pageNumber })
    }).catch(() => {});
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
