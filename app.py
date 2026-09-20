import os
import re
import uuid
import requests
import pypdf
from typing import List, Dict, Any
from datetime import datetime
from functools import wraps
from gtts import gTTS
from dotenv import load_dotenv

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ==========================================
# 1. CONFIGURATION
# ==========================================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default_fallback_secret_key_12345')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', f"sqlite:///{os.path.join(BASE_DIR, 'database.db')}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    STATIC_FOLDER = os.path.join(BASE_DIR, 'static')
    UPLOAD_FOLDER = os.path.join(STATIC_FOLDER, 'uploads')
    PDF_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, 'pdfs')
    COVER_UPLOAD_FOLDER = os.path.join(STATIC_FOLDER, 'images', 'covers')
    AUDIO_FOLDER = os.path.join(STATIC_FOLDER, 'audio')
    
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB
    MAX_FORM_MEMORY_SIZE = 50 * 1024 * 1024 # 50MB
    
    ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY', '')
    ELEVENLABS_VOICE_ID = os.getenv('ELEVENLABS_VOICE_ID', '21m00Tcm4TlvDq8ikWAM')
    
    ALLOWED_PDF_EXTENSIONS = {'pdf'}
    ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}

# ==========================================
# 2. DATABASE MODELS
# ==========================================
db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    favorites = db.relationship('Favorite', backref='user', lazy=True, cascade='all, delete-orphan')
    history = db.relationship('ReadingHistory', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_favorited(self, book_id):
        return Favorite.query.filter_by(user_id=self.id, book_id=book_id).first() is not None


class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    books = db.relationship('Book', backref='category', lazy=True)


class Book(db.Model):
    __tablename__ = 'books'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    language = db.Column(db.String(30), default='English')
    cover_image = db.Column(db.String(255), default='default_cover.jpg')
    pdf_file = db.Column(db.String(255), nullable=True)
    is_featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    chapters = db.relationship('Chapter', backref='book', lazy=True, cascade='all, delete-orphan', order_by='Chapter.chapter_number')

    @property
    def has_audio(self):
        return any(ch.audio_file for ch in self.chapters)
    
    @property
    def total_audio_duration(self):
        return sum(ch.audio_file.duration_seconds for ch in self.chapters if ch.audio_file)


class Chapter(db.Model):
    __tablename__ = 'chapters'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    chapter_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    text_content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    audio_file = db.relationship('AudioFile', backref='chapter', uselist=False, cascade='all, delete-orphan')


class AudioFile(db.Model):
    __tablename__ = 'audio_files'
    id = db.Column(db.Integer, primary_key=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id'), unique=True, nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    duration_seconds = db.Column(db.Float, default=0.0)
    voice_engine = db.Column(db.String(50), default='elevenlabs')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Favorite(db.Model):
    __tablename__ = 'favorites'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    book = db.relationship('Book', backref='favorited_by')
    __table_args__ = (db.UniqueConstraint('user_id', 'book_id', name='_user_book_uc'),)


class ReadingHistory(db.Model):
    __tablename__ = 'reading_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id'), nullable=True)
    last_audio_position = db.Column(db.Float, default=0.0)
    last_read_page = db.Column(db.Integer, default=1)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    book = db.relationship('Book')
    chapter = db.relationship('Chapter')

# ==========================================
# 3. UTILITIES (Auth, PDF, TTS Engine)
# ==========================================
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login', next=request.url))
        if not current_user.is_admin:
            flash("Access denied. Admin privileges required.", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def clean_devanagari_text(t: str) -> str:
    if not t:
        return ""
    t = re.sub(r'([अ-ह])्\s+([अ-ह])', r'\1्\2', t)
    t = re.sub(r'(?:^|\s)ि\s*नया\b', ' धनिया', t)
    exact_replacements = {
        ' ोरीराम': ' होरीराम', ' ोरी': ' होरी', ' ाथ': ' हाथ', ' ाथों': ' हाथों',
        ' ुए': ' हुए', ' ुई': ' हुई', ' ुआ': ' हुआ', ' ोती': ' होती', ' ोता': ' होता',
        ' ोते': ' होते', ' ोगा': ' होगा', ' ोगी': ' होगी', ' ोकर': ' होकर', ' ो': ' हो'
    }
    for k, v in exact_replacements.items():
        t = t.replace(k, v)
    t = re.sub(r'[ \t]{2,}', ' ', t)
    return t.strip()

def extract_text_from_pdf(pdf_path: str) -> str:
    extracted_text = []
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                page_text = page.extract_text(layout=False)
                if page_text:
                    cleaned_page = clean_devanagari_text(page_text.strip())
                    extracted_text.append(f"--- Page {page_idx + 1} ---\n{cleaned_page}")
            if extracted_text:
                return "\n\n".join(extracted_text)
    except Exception as e:
        print(f"pdfplumber fallback to pypdf: {e}")

    try:
        reader = pypdf.PdfReader(pdf_path)
        for page_idx, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                cleaned_page = clean_devanagari_text(page_text.strip())
                extracted_text.append(f"--- Page {page_idx + 1} ---\n{cleaned_page}")
    except Exception as e:
        print(f"Error extracting PDF text: {e}")
        return ""
    return "\n\n".join(extracted_text)

def auto_split_into_chapters(full_text: str, default_chunk_size: int = 4000) -> List[Dict[str, Any]]:
    clean_text = re.sub(r'--- Page \d+ ---\n?', '', full_text).strip()
    if not clean_text:
        return []

    chapter_pattern = r'(?i)(?:\n|\A)(chapter\s+\d+|chapter\s+[ivxlcdm]+|अध्याय\s+\d+|section\s+\d+|भाग\s+\d+|part\s+\d+)'
    splits = re.split(chapter_pattern, clean_text)
    chapters = []
    if len(splits) > 1:
        current_title = "Introduction / Preface"
        current_content = splits[0].strip()
        if current_content:
            chapters.append({"chapter_number": 1, "title": current_title, "text_content": current_content})
        chap_num = len(chapters) + 1
        for i in range(1, len(splits), 2):
            chap_heading = splits[i].strip()
            chap_body = splits[i+1].strip() if (i+1) < len(splits) else ""
            body_lines = chap_body.split('\n')
            subtitle = body_lines[0].strip() if body_lines else ""
            if subtitle and len(subtitle) < 60 and not subtitle.lower().startswith('chapter'):
                full_chap_title = f"{chap_heading.title()}: {subtitle}"
                body_content = "\n".join(body_lines[1:]).strip()
            else:
                full_chap_title = chap_heading.title()
                body_content = chap_body
            if body_content:
                chapters.append({"chapter_number": chap_num, "title": full_chap_title, "text_content": body_content})
                chap_num += 1
    else:
        paragraphs = clean_text.split('\n\n')
        current_chunk = []
        current_length = 0
        chap_num = 1
        for para in paragraphs:
            para_str = para.strip()
            if not para_str: continue
            if current_length + len(para_str) > default_chunk_size and current_chunk:
                chapters.append({"chapter_number": chap_num, "title": f"Chapter {chap_num}", "text_content": "\n\n".join(current_chunk)})
                chap_num += 1
                current_chunk = [para_str]
                current_length = len(para_str)
            else:
                current_chunk.append(para_str)
                current_length += len(para_str)
        if current_chunk:
            chapters.append({"chapter_number": chap_num, "title": f"Chapter {chap_num}", "text_content": "\n\n".join(current_chunk)})
    return chapters

def extract_chapters_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    full_text = extract_text_from_pdf(pdf_path)
    if not full_text: return []
    return auto_split_into_chapters(full_text)

def estimate_audio_duration(text: str, words_per_minute: int = 150) -> float:
    words = len(text.split())
    return round((words / max(words_per_minute, 1)) * 60, 2)

def generate_audio_elevenlabs(text: str, voice_id: str, api_key: str, output_path: str) -> bool:
    if not api_key or api_key.strip() in ("", "your_elevenlabs_api_key_here"):
        return False
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": api_key}
    payload = {"text": text, "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        if resp.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            return True
    except Exception as e:
        print(f"ElevenLabs error: {e}")
    return False

def generate_audio_gtts(text: str, lang: str, output_path: str) -> bool:
    try:
        language_code = 'hi' if lang.lower() == 'hindi' else 'en'
        tts = gTTS(text=text[:5000], lang=language_code, slow=False)
        tts.save(output_path)
        return True
    except Exception as e:
        print(f"gTTS error: {e}")
        return False

def convert_text_to_audio(text: str, book_id: int, chapter_number: int, language: str = 'English') -> dict:
    audio_dir = Config.AUDIO_FOLDER
    os.makedirs(audio_dir, exist_ok=True)
    filename = f"book_{book_id}_chap_{chapter_number}_{uuid.uuid4().hex[:8]}.mp3"
    full_path = os.path.join(audio_dir, filename)
    
    success = generate_audio_elevenlabs(text, Config.ELEVENLABS_VOICE_ID, Config.ELEVENLABS_API_KEY, full_path)
    engine = "elevenlabs"
    if not success:
        success = generate_audio_gtts(text, language, full_path)
        engine = "gtts"
    if not success or not os.path.exists(full_path):
        raise RuntimeError("Failed to generate audio.")
    return {
        "file_path": f"audio/{filename}",
        "duration_seconds": estimate_audio_duration(text),
        "voice_engine": engine
    }

# ==========================================
# 4. APP FACTORIES & ROUTES
# ==========================================
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(Config.PDF_UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(Config.COVER_UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(Config.AUDIO_FOLDER, exist_ok=True)

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = 'login'
    login_manager.login_message_category = 'warning'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_global_vars():
        try:
            categories = Category.query.all()
        except Exception:
            categories = []
        return {
            'all_categories': categories,
            'elevenlabs_configured': bool(Config.ELEVENLABS_API_KEY and Config.ELEVENLABS_API_KEY != 'your_elevenlabs_api_key_here')
        }

    # --- MAIN ROUTES ---
    @app.route('/')
    def index():
        all_books = Book.query.order_by(Book.id.asc()).all()
        shelf1_books = all_books[0:5] if len(all_books) >= 5 else all_books
        shelf2_books = all_books[5:10] if len(all_books) >= 10 else []
        shelf3_books = all_books[10:15] if len(all_books) >= 15 else []
        return render_template('index.html', shelf1_books=shelf1_books, shelf2_books=shelf2_books, shelf3_books=shelf3_books, all_books=all_books, categories=Category.query.all())

    @app.route('/books')
    def books_catalog():
        query_text = request.args.get('q', '').strip()
        category_id = request.args.get('category', type=int)
        language = request.args.get('language', '').strip()
        author = request.args.get('author', '').strip()
        
        books_query = Book.query
        if query_text:
            search_filter = f"%{query_text}%"
            books_query = books_query.filter((Book.title.ilike(search_filter)) | (Book.author.ilike(search_filter)) | (Book.description.ilike(search_filter)))
        if category_id:
            books_query = books_query.filter_by(category_id=category_id)
        if language:
            books_query = books_query.filter(Book.language.ilike(f"%{language}%"))
        if author:
            books_query = books_query.filter(Book.author.ilike(f"%{author}%"))
            
        books = books_query.order_by(Book.id.desc()).all()
        authors = [a[0] for a in db.session.query(Book.author).distinct().all()]
        return render_template('books.html', books=books, categories=Category.query.all(), authors=authors, selected_q=query_text, selected_category=category_id, selected_language=language, selected_author=author)

    @app.route('/book/<int:book_id>')
    def book_detail(book_id):
        book = Book.query.get_or_404(book_id)
        related_books = Book.query.filter(Book.category_id == book.category_id, Book.id != book.id).limit(4).all()
        is_fav = current_user.is_authenticated and current_user.is_favorited(book.id)
        return render_template('book_detail.html', book=book, related_books=related_books, is_favorited=is_fav)

    @app.route('/read/<int:book_id>')
    def reader(book_id):
        book = Book.query.get_or_404(book_id)
        chapter_id = request.args.get('chapter', type=int)
        selected_chapter = Chapter.query.filter_by(id=chapter_id, book_id=book.id).first() if chapter_id else None
        if not selected_chapter and book.chapters:
            selected_chapter = book.chapters[0]
        if current_user.is_authenticated and selected_chapter:
            history = ReadingHistory.query.filter_by(user_id=current_user.id, book_id=book.id).first()
            if not history:
                history = ReadingHistory(user_id=current_user.id, book_id=book.id, chapter_id=selected_chapter.id)
                db.session.add(history)
            else:
                history.chapter_id = selected_chapter.id
            db.session.commit()
        return render_template('reader.html', book=book, current_chapter=selected_chapter)

    @app.route('/listen/<int:book_id>')
    def audio_player(book_id):
        book = Book.query.get_or_404(book_id)
        chapter_id = request.args.get('chapter', type=int)
        audio_chapters = [ch for ch in book.chapters if ch.audio_file]
        selected_chapter = Chapter.query.filter_by(id=chapter_id, book_id=book.id).first() if chapter_id else None
        if not selected_chapter:
            selected_chapter = audio_chapters[0] if audio_chapters else (book.chapters[0] if book.chapters else None)
        last_position = 0.0
        if current_user.is_authenticated:
            history = ReadingHistory.query.filter_by(user_id=current_user.id, book_id=book.id).first()
            if history and history.last_audio_position:
                last_position = history.last_audio_position
        return render_template('audio_player.html', book=book, audio_chapters=audio_chapters, current_chapter=selected_chapter, start_position=last_position)

    @app.route('/favorites')
    @login_required
    def favorites():
        user_favs = Favorite.query.filter_by(user_id=current_user.id).order_by(Favorite.created_at.desc()).all()
        return render_template('favorites.html', books=[fav.book for fav in user_favs if fav.book])

    @app.route('/history')
    @login_required
    def history():
        user_history = ReadingHistory.query.filter_by(user_id=current_user.id).order_by(ReadingHistory.updated_at.desc()).all()
        return render_template('history.html', history_items=user_history)

    # --- AUTH ROUTES ---
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            if not username or not email or not password:
                flash('All fields are required.', 'danger')
                return render_template('register.html')
            if password != confirm_password:
                flash('Passwords do not match.', 'danger')
                return render_template('register.html')
            if len(password) < 6:
                flash('Password must be at least 6 characters long.', 'danger')
                return render_template('register.html')
            if User.query.filter((User.username == username) | (User.email == email)).first():
                flash('Username or Email already registered.', 'warning')
                return render_template('register.html')
            is_admin = (User.query.count() == 0)
            new_user = User(username=username, email=email, is_admin=is_admin)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            flash('Account created successfully!', 'success')
            return redirect(url_for('admin_dashboard') if new_user.is_admin else url_for('index'))
        return render_template('register.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('admin_dashboard') if current_user.is_admin else url_for('index'))
        if request.method == 'POST':
            email_or_user = request.form.get('login_input', '').strip()
            password = request.form.get('password', '')
            remember = True if request.form.get('remember') else False
            if not email_or_user or not password:
                flash('Please enter both email/username and password.', 'danger')
                return render_template('login.html')
            user = User.query.filter((User.email == email_or_user.lower()) | (User.username == email_or_user)).first()
            if user and user.check_password(password):
                login_user(user, remember=remember)
                next_page = request.args.get('next')
                flash(f'Welcome back, {user.username}!', 'success')
                return redirect(next_page or (url_for('admin_dashboard') if user.is_admin else url_for('index')))
            flash('Invalid username/email or password.', 'danger')
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('You have been logged out.', 'info')
        return redirect(url_for('index'))

    # --- ADMIN ROUTES ---
    @app.route('/admin')
    @admin_required
    def admin_dashboard():
        return render_template(
            'admin/dashboard.html',
            total_books=Book.query.count(),
            total_users=User.query.count(),
            total_chapters=Chapter.query.count(),
            total_audios=AudioFile.query.count(),
            recent_books=Book.query.order_by(Book.id.asc()).limit(6).all(),
            categories=Category.query.all(),
            latest_users=User.query.order_by(User.id.desc()).limit(5).all()
        )

    @app.route('/admin/book/new', methods=['GET', 'POST'])
    @admin_required
    def book_create():
        categories = Category.query.all()
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            author = request.form.get('author', '').strip()
            description = request.form.get('description', '').strip()
            category_id = request.form.get('category_id', type=int)
            language = request.form.get('language', 'English').strip()
            is_featured = True if request.form.get('is_featured') else False
            pasted_text = request.form.get('pasted_text', '').strip()
            
            if not title or not author or not category_id:
                flash('Title, Author, and Category are required.', 'danger')
                return render_template('admin/book_form.html', categories=categories, book=None)

            cover_filename = 'default_cover.jpg'
            if 'cover_image' in request.files:
                file = request.files['cover_image']
                if file and file.filename and allowed_file(file.filename, Config.ALLOWED_IMAGE_EXTENSIONS):
                    cover_filename = f"cover_{secure_filename(file.filename)}"
                    file.save(os.path.join(Config.COVER_UPLOAD_FOLDER, cover_filename))

            pdf_filename = None
            if 'pdf_file' in request.files:
                file = request.files['pdf_file']
                if file and file.filename and allowed_file(file.filename, Config.ALLOWED_PDF_EXTENSIONS):
                    pdf_filename = f"pdf_{secure_filename(file.filename)}"
                    full_pdf_path = os.path.join(Config.PDF_UPLOAD_FOLDER, pdf_filename)
                    file.save(full_pdf_path)

            new_book = Book(title=title, author=author, description=description, category_id=category_id, language=language, cover_image=cover_filename, pdf_file=pdf_filename, is_featured=is_featured)
            db.session.add(new_book)
            db.session.commit()

            if pdf_filename:
                full_pdf_path = os.path.join(Config.PDF_UPLOAD_FOLDER, pdf_filename)
                extracted_chaps = extract_chapters_from_pdf(full_pdf_path)
                for c_info in extracted_chaps:
                    db.session.add(Chapter(book_id=new_book.id, chapter_number=c_info['chapter_number'], title=c_info['title'], text_content=c_info['text_content']))
                db.session.commit()
                flash(f'Book "{title}" created! Extracted {len(extracted_chaps)} chapters from PDF.', 'success')
            elif pasted_text:
                chap_list = auto_split_into_chapters(pasted_text)
                for c_info in chap_list:
                    db.session.add(Chapter(book_id=new_book.id, chapter_number=c_info['chapter_number'], title=c_info['title'], text_content=c_info['text_content']))
                db.session.commit()
                flash(f'Book "{title}" created with pasted chapters.', 'success')
            else:
                flash(f'Book "{title}" created successfully!', 'success')
            return redirect(url_for('chapter_editor', book_id=new_book.id))
        return render_template('admin/book_form.html', categories=categories, book=None)

    @app.route('/admin/book/edit/<int:book_id>', methods=['GET', 'POST'])
    @admin_required
    def book_edit(book_id):
        book = Book.query.get_or_404(book_id)
        categories = Category.query.all()
        if request.method == 'POST':
            book.title = request.form.get('title', '').strip()
            book.author = request.form.get('author', '').strip()
            book.description = request.form.get('description', '').strip()
            book.category_id = request.form.get('category_id', type=int)
            book.language = request.form.get('language', 'English').strip()
            book.is_featured = True if request.form.get('is_featured') else False
            if 'cover_image' in request.files:
                file = request.files['cover_image']
                if file and file.filename and allowed_file(file.filename, Config.ALLOWED_IMAGE_EXTENSIONS):
                    cover_filename = f"cover_{secure_filename(file.filename)}"
                    file.save(os.path.join(Config.COVER_UPLOAD_FOLDER, cover_filename))
                    book.cover_image = cover_filename
            if 'pdf_file' in request.files:
                file = request.files['pdf_file']
                if file and file.filename and allowed_file(file.filename, Config.ALLOWED_PDF_EXTENSIONS):
                    pdf_filename = f"pdf_{secure_filename(file.filename)}"
                    full_pdf_path = os.path.join(Config.PDF_UPLOAD_FOLDER, pdf_filename)
                    file.save(full_pdf_path)
                    book.pdf_file = pdf_filename
                    extracted_chaps = extract_chapters_from_pdf(full_pdf_path)
                    if extracted_chaps:
                        Chapter.query.filter_by(book_id=book.id).delete()
                        for c_info in extracted_chaps:
                            db.session.add(Chapter(book_id=book.id, chapter_number=c_info['chapter_number'], title=c_info['title'], text_content=c_info['text_content']))
                        flash(f'PDF updated and {len(extracted_chaps)} chapters extracted.', 'success')
            db.session.commit()
            flash(f'Book "{book.title}" updated successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        return render_template('admin/book_form.html', categories=categories, book=book)

    @app.route('/admin/book/delete/<int:book_id>', methods=['POST'])
    @admin_required
    def book_delete(book_id):
        book = Book.query.get_or_404(book_id)
        title = book.title
        db.session.delete(book)
        db.session.commit()
        flash(f'Book "{title}" deleted successfully.', 'info')
        return redirect(url_for('admin_dashboard'))

    @app.route('/admin/book/<int:book_id>/pdf-extract', methods=['GET', 'POST'])
    @admin_required
    def pdf_extract_review(book_id):
        book = Book.query.get_or_404(book_id)
        if not book.pdf_file:
            flash('No PDF file uploaded for this book.', 'warning')
            return redirect(url_for('book_edit', book_id=book.id))
        pdf_full_path = os.path.join(Config.PDF_UPLOAD_FOLDER, book.pdf_file)
        extracted_text = extract_text_from_pdf(pdf_full_path) if os.path.exists(pdf_full_path) else ""
        if request.method == 'POST':
            edited_text = request.form.get('extracted_text', '').strip()
            auto_split = True if request.form.get('auto_split') else False
            Chapter.query.filter_by(book_id=book.id).delete()
            db.session.commit()
            if auto_split and edited_text:
                for c_info in auto_split_into_chapters(edited_text):
                    db.session.add(Chapter(book_id=book.id, chapter_number=c_info['chapter_number'], title=c_info['title'], text_content=c_info['text_content']))
            elif edited_text:
                db.session.add(Chapter(book_id=book.id, chapter_number=1, title="Full Book Text", text_content=edited_text))
            db.session.commit()
            flash('Extracted text saved into chapters successfully!', 'success')
            return redirect(url_for('tts_generate', book_id=book.id))
        return render_template('admin/pdf_extract.html', book=book, extracted_text=extracted_text, parsed_chapters=auto_split_into_chapters(extracted_text) if extracted_text else [])

    @app.route('/admin/book/<int:book_id>/chapters', methods=['GET', 'POST'])
    @admin_required
    def chapter_editor(book_id):
        book = Book.query.get_or_404(book_id)
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add_chapter':
                title = request.form.get('title', 'New Chapter').strip()
                content = request.form.get('text_content', '').strip()
                db.session.add(Chapter(book_id=book.id, chapter_number=len(book.chapters) + 1, title=title, text_content=content))
                db.session.commit()
                flash(f'Added Chapter "{title}".', 'success')
            elif action == 'add_multiple_chapters':
                titles = request.form.getlist('titles[]')
                contents = request.form.getlist('contents[]')
                added_count = 0
                for t, c in zip(titles, contents):
                    t_clean = t.strip() if t else f"Chapter {len(book.chapters) + 1}"
                    c_clean = c.strip() if c else ""
                    if t_clean or c_clean:
                        db.session.add(Chapter(book_id=book.id, chapter_number=len(book.chapters) + 1, title=t_clean, text_content=c_clean))
                        db.session.commit()
                        added_count += 1
                flash(f'Successfully added {added_count} chapter(s)!', 'success')
            elif action == 'upload_pdf_chapters':
                if 'pdf_file' in request.files:
                    file = request.files['pdf_file']
                    mode = request.form.get('mode', 'append')
                    if file and file.filename and allowed_file(file.filename, Config.ALLOWED_PDF_EXTENSIONS):
                        pdf_filename = f"pdf_{secure_filename(file.filename)}"
                        full_pdf_path = os.path.join(Config.PDF_UPLOAD_FOLDER, pdf_filename)
                        file.save(full_pdf_path)
                        book.pdf_file = pdf_filename
                        extracted_chaps = extract_chapters_from_pdf(full_pdf_path)
                        if mode == 'replace':
                            Chapter.query.filter_by(book_id=book.id).delete()
                            db.session.commit()
                        start_num = len(book.chapters) if mode == 'append' else 0
                        for c_info in extracted_chaps:
                            db.session.add(Chapter(book_id=book.id, chapter_number=start_num + c_info['chapter_number'], title=c_info['title'], text_content=c_info['text_content']))
                        db.session.commit()
                        flash(f'Imported {len(extracted_chaps)} chapters from PDF file!', 'success')
            elif action == 'edit_chapter':
                chap = Chapter.query.get_or_404(request.form.get('chapter_id', type=int))
                chap.title = request.form.get('title', chap.title).strip()
                chap.text_content = request.form.get('text_content', chap.text_content).strip()
                db.session.commit()
                flash(f'Updated Chapter "{chap.title}".', 'success')
            elif action == 'delete_chapter':
                chap = Chapter.query.get_or_404(request.form.get('chapter_id', type=int))
                db.session.delete(chap)
                db.session.commit()
                flash('Chapter deleted.', 'info')
            return redirect(url_for('chapter_editor', book_id=book.id))
        return render_template('admin/chapter_editor.html', book=book)

    @app.route('/admin/book/<int:book_id>/tts', methods=['GET', 'POST'])
    @admin_required
    def tts_generate(book_id):
        book = Book.query.get_or_404(book_id)
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'batch_generate':
                count = 0
                for chap in book.chapters:
                    if not chap.audio_file:
                        try:
                            res = convert_text_to_audio(chap.text_content, book.id, chap.chapter_number, book.language)
                            db.session.add(AudioFile(chapter_id=chap.id, file_path=res['file_path'], duration_seconds=res['duration_seconds'], voice_engine=res['voice_engine']))
                            db.session.commit()
                            count += 1
                        except Exception as e:
                            flash(f'Error generating audio for Chapter {chap.chapter_number}: {e}', 'danger')
                flash(f'Batch audio conversion completed! Generated audio for {count} chapters.', 'success')
                return redirect(url_for('tts_generate', book_id=book.id))
        return render_template('admin/tts_generate.html', book=book)

    @app.route('/admin/chapter/<int:chapter_id>/generate-audio', methods=['POST'])
    @admin_required
    def generate_chapter_audio(chapter_id):
        chap = Chapter.query.get_or_404(chapter_id)
        try:
            if chap.audio_file:
                db.session.delete(chap.audio_file)
                db.session.commit()
            res = convert_text_to_audio(chap.text_content, chap.book_id, chap.chapter_number, chap.book.language)
            db.session.add(AudioFile(chapter_id=chap.id, file_path=res['file_path'], duration_seconds=res['duration_seconds'], voice_engine=res['voice_engine']))
            db.session.commit()
            flash(f'Audio generated successfully for "{chap.title}" using {res["voice_engine"].upper()} engine.', 'success')
        except Exception as e:
            flash(f'Failed to generate audio: {e}', 'danger')
        return redirect(url_for('tts_generate', book_id=chap.book_id))

    # --- API ENDPOINTS ---
    @app.route('/api/favorite/toggle', methods=['POST'])
    @login_required
    def toggle_favorite():
        data = request.get_json() or {}
        book_id = data.get('book_id')
        if not book_id:
            return jsonify({'success': False, 'message': 'Missing book_id'}), 400
        book = Book.query.get(book_id)
        if not book:
            return jsonify({'success': False, 'message': 'Book not found'}), 404
        fav = Favorite.query.filter_by(user_id=current_user.id, book_id=book.id).first()
        if fav:
            db.session.delete(fav)
            db.session.commit()
            return jsonify({'success': True, 'is_favorited': False, 'message': 'Removed from favorites'})
        db.session.add(Favorite(user_id=current_user.id, book_id=book.id))
        db.session.commit()
        return jsonify({'success': True, 'is_favorited': True, 'message': 'Added to favorites'})

    @app.route('/api/history/update', methods=['POST'])
    @login_required
    def update_history():
        data = request.get_json() or {}
        book_id = data.get('book_id')
        chapter_id = data.get('chapter_id')
        audio_pos = data.get('audio_position', 0.0)
        page_num = data.get('page_number', 1)
        if not book_id:
            return jsonify({'success': False, 'message': 'Missing book_id'}), 400
        history = ReadingHistory.query.filter_by(user_id=current_user.id, book_id=book_id).first()
        if not history:
            db.session.add(ReadingHistory(user_id=current_user.id, book_id=book_id, chapter_id=chapter_id, last_audio_position=audio_pos, last_read_page=page_num))
        else:
            if chapter_id: history.chapter_id = chapter_id
            if audio_pos: history.last_audio_position = audio_pos
            if page_num: history.last_read_page = page_num
        db.session.commit()
        return jsonify({'success': True})

    @app.route('/api/book/<int:book_id>/playlist')
    def get_book_playlist(book_id):
        book = Book.query.get_or_404(book_id)
        playlist = []
        for chap in book.chapters:
            if chap.audio_file:
                playlist.append({
                    'chapter_id': chap.id,
                    'chapter_number': chap.chapter_number,
                    'title': chap.title,
                    'audio_url': f"/static/{chap.audio_file.file_path}",
                    'duration': chap.audio_file.duration_seconds,
                    'engine': chap.audio_file.voice_engine
                })
        return jsonify({'book_id': book.id, 'book_title': book.title, 'author': book.author, 'cover_url': f"/static/images/covers/{book.cover_image}", 'playlist': playlist})

    @app.route('/api/book/<int:book_id>/full_details')
    def get_book_full_details(book_id):
        book = Book.query.get_or_404(book_id)
        is_fav = current_user.is_authenticated and current_user.is_favorited(book.id)
        last_chap_id, last_page, last_audio_pos = None, 1, 0.0
        if current_user.is_authenticated:
            history = ReadingHistory.query.filter_by(user_id=current_user.id, book_id=book.id).first()
            if history:
                last_chap_id = history.chapter_id
                last_page = history.last_read_page or 1
                last_audio_pos = history.last_audio_position or 0.0

        chapters_data = []
        for chap in book.chapters:
            audio_info = None
            if chap.audio_file:
                audio_info = {'id': chap.audio_file.id, 'audio_url': f"/static/{chap.audio_file.file_path}", 'duration': chap.audio_file.duration_seconds, 'engine': chap.audio_file.voice_engine}
            chapters_data.append({'id': chap.id, 'chapter_number': chap.chapter_number, 'title': chap.title, 'text_content': chap.text_content, 'audio': audio_info})
            
        return jsonify({
            'id': book.id, 'title': book.title, 'author': book.author, 'description': book.description,
            'language': book.language, 'category': book.category.name if book.category else 'General',
            'cover_url': f"/static/images/covers/{book.cover_image}", 'is_favorited': is_fav,
            'has_audio': book.has_audio, 'last_chapter_id': last_chap_id, 'last_page': last_page,
            'last_audio_pos': last_audio_pos, 'chapters': chapters_data
        })

    # --- ERROR HANDLERS ---
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(413)
    def request_entity_too_large(e):
        flash("The uploaded file/data is too large! Maximum allowed upload size is 500 MB.", "danger")
        return redirect(request.referrer or url_for('admin_dashboard'))

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('500.html'), 500

    with app.app_context():
        db.create_all()

    return app

app = create_app()

if __name__ == '__main__':
    print("Starting E-Book & Audiobook Consolidated Flask Application...")
    app.run(host='0.0.0.0', port=5000, debug=True)
