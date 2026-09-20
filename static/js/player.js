/* ==========================================================================
   Interactive Audiobook Player Engine
   Controls: Play/Pause, Skip ±10s, Speed rate (0.5x-2x), Progress bar, Playlist sync
   ========================================================================== */

class AudioPlayerEngine {
    constructor() {
        this.audio = new Audio();
        this.playlist = [];
        this.currentIndex = 0;
        this.bookId = null;

        // UI elements
        this.playPauseBtn = document.getElementById('player-play-btn');
        this.prevBtn = document.getElementById('player-prev-btn');
        this.nextBtn = document.getElementById('player-next-btn');
        this.rewindBtn = document.getElementById('player-rewind-btn');
        this.forwardBtn = document.getElementById('player-forward-btn');
        this.speedSelect = document.getElementById('player-speed-select');
        this.progressBar = document.getElementById('player-progress-container');
        this.progressFill = document.getElementById('player-progress-fill');
        this.currentTimeEl = document.getElementById('player-current-time');
        this.durationEl = document.getElementById('player-duration');
        this.chapterTitleEl = document.getElementById('player-chapter-title');
        this.volumeSlider = document.getElementById('player-volume-slider');

        this.initEventListeners();
    }

    init(bookId, playlist, startIndex = 0, initialPosition = 0) {
        this.bookId = bookId;
        this.playlist = playlist;
        this.currentIndex = startIndex;

        if (this.playlist.length > 0) {
            this.loadTrack(this.currentIndex, initialPosition);
        }
    }

    loadTrack(index, startTime = 0) {
        if (index < 0 || index >= this.playlist.length) return;
        this.currentIndex = index;

        const track = this.playlist[index];
        this.audio.src = track.audio_url;
        
        if (this.chapterTitleEl) {
            this.chapterTitleEl.textContent = `${track.chapter_number}. ${track.title}`;
        }

        // Highlight playlist item in sidebar if available
        document.querySelectorAll('.playlist-item').forEach((item, i) => {
            if (i === index) {
                item.classList.add('active', 'bg-primary', 'text-white');
            } else {
                item.classList.remove('active', 'bg-primary', 'text-white');
            }
        });

        this.audio.addEventListener('loadedmetadata', () => {
            if (this.durationEl) {
                this.durationEl.textContent = this.formatTime(this.audio.duration);
            }
            if (startTime > 0 && startTime < this.audio.duration) {
                this.audio.currentTime = startTime;
            }
        }, { once: true });
    }

    play() {
        this.audio.play();
        this.updatePlayStateUI(true);
    }

    pause() {
        this.audio.pause();
        this.updatePlayStateUI(false);
    }

    togglePlay() {
        if (this.audio.paused) {
            this.play();
        } else {
            this.pause();
        }
    }

    skip(seconds) {
        this.audio.currentTime = Math.max(0, Math.min(this.audio.duration || 0, this.audio.currentTime + seconds));
    }

    setSpeed(rate) {
        this.audio.playbackRate = parseFloat(rate);
    }

    setVolume(vol) {
        this.audio.volume = parseFloat(vol);
    }

    updatePlayStateUI(isPlaying) {
        if (this.playPauseBtn) {
            const icon = this.playPauseBtn.querySelector('i');
            if (icon) {
                icon.className = isPlaying ? 'bi bi-pause-fill' : 'bi bi-play-fill';
            }
        }
    }

    formatTime(secs) {
        if (isNaN(secs) || secs === Infinity) return "00:00";
        const m = Math.floor(secs / 60);
        const s = Math.floor(secs % 60);
        return `${m < 10 ? '0' + m : m}:${s < 10 ? '0' + s : s}`;
    }

    initEventListeners() {
        if (this.playPauseBtn) {
            this.playPauseBtn.addEventListener('click', () => this.togglePlay());
        }

        if (this.rewindBtn) {
            this.rewindBtn.addEventListener('click', () => this.skip(-10));
        }

        if (this.forwardBtn) {
            this.forwardBtn.addEventListener('click', () => this.skip(10));
        }

        if (this.prevBtn) {
            this.prevBtn.addEventListener('click', () => {
                if (this.currentIndex > 0) {
                    this.loadTrack(this.currentIndex - 1);
                    this.play();
                }
            });
        }

        if (this.nextBtn) {
            this.nextBtn.addEventListener('click', () => {
                if (this.currentIndex < this.playlist.length - 1) {
                    this.loadTrack(this.currentIndex + 1);
                    this.play();
                }
            });
        }

        if (this.speedSelect) {
            this.speedSelect.addEventListener('change', (e) => this.setSpeed(e.target.value));
        }

        if (this.volumeSlider) {
            this.volumeSlider.addEventListener('input', (e) => this.setVolume(e.target.value));
        }

        if (this.progressBar) {
            this.progressBar.addEventListener('click', (e) => {
                const rect = this.progressBar.getBoundingClientRect();
                const clickX = e.clientX - rect.left;
                const pct = clickX / rect.width;
                if (this.audio.duration) {
                    this.audio.currentTime = pct * this.audio.duration;
                }
            });
        }

        // Timeupdate listener for progress bar fill & history sync
        let lastSyncTime = 0;
        this.audio.addEventListener('timeupdate', () => {
            if (this.audio.duration) {
                const pct = (this.audio.currentTime / this.audio.duration) * 100;
                if (this.progressFill) this.progressFill.style.width = `${pct}%`;
                if (this.currentTimeEl) this.currentTimeEl.textContent = this.formatTime(this.audio.currentTime);
                
                const now = Date.now();
                if (now - lastSyncTime > 10000 && this.bookId) {
                    lastSyncTime = now;
                    this.syncProgressToBackend();
                }
            }
        });

        // Auto-advance track on ended
        this.audio.addEventListener('ended', () => {
            if (this.currentIndex < this.playlist.length - 1) {
                this.loadTrack(this.currentIndex + 1);
                this.play();
            } else {
                this.updatePlayStateUI(false);
            }
        });
    }

    async syncProgressToBackend() {
        if (!this.bookId || !this.playlist[this.currentIndex]) return;
        const currentChap = this.playlist[this.currentIndex];
        
        try {
            await fetch('/api/history/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    book_id: this.bookId,
                    chapter_id: currentChap.chapter_id,
                    audio_position: this.audio.currentTime
                })
            });
        } catch (e) {
            console.warn('Failed to sync history:', e);
        }
    }
}

window.audioPlayer = new AudioPlayerEngine();
