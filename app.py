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

from flask import Flask, request, jsonify, send_from_directory, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ==========================================
# 1. CONFIGURATION
# ==========================================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

def get_db_uri():
    db_url = os.getenv('DATABASE_URL', '').strip()
    if not db_url:
        if os.getenv('VERCEL'):
            return f"sqlite:///{os.path.join('/tmp', 'database.db')}"
        return f"sqlite:///{os.path.join(BASE_DIR, 'database.db')}"
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+pg8000://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)
    return db_url


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default_fallback_secret_key_12345')
    SQLALCHEMY_DATABASE_URI = get_db_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    STATIC_FOLDER = os.path.join(BASE_DIR, 'static')
    
    if os.getenv('VERCEL'):
        UPLOAD_FOLDER = '/tmp/uploads'
        PDF_UPLOAD_FOLDER = '/tmp/uploads/pdfs'
        COVER_UPLOAD_FOLDER = '/tmp/static/images/covers'
        AUDIO_FOLDER = '/tmp/static/audio'
    else:
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

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "is_admin": self.is_admin,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    books = db.relationship('Book', backref='category', lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "book_count": len(self.books)
        }

class Book(db.Model):
    __tablename__ = 'books'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    cover_image = db.Column(db.String(255), nullable=True, default='covers/default.jpg')
    pdf_file = db.Column(db.String(255), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    chapters = db.relationship('Chapter', backref='book', lazy=True, cascade='all, delete-orphan', order_by='Chapter.chapter_number')
    audio_files = db.relationship('AudioFile', backref='book', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, include_chapters=False):
        data = {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "description": self.description,
            "cover_image": self.cover_image,
            "pdf_file": self.pdf_file,
            "category_id": self.category_id,
            "category_name": self.category.name if self.category else "Uncategorized",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "total_chapters": len(self.chapters)
        }
        if include_chapters:
            data["chapters"] = [c.to_dict() for c in self.chapters]
        return data

class Chapter(db.Model):
    __tablename__ = 'chapters'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    chapter_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    text_content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self, include_text=True):
        data = {
            "id": self.id,
            "book_id": self.book_id,
            "chapter_number": self.chapter_number,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
        if include_text:
            data["text_content"] = self.text_content
        return data

class AudioFile(db.Model):
    __tablename__ = 'audio_files'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    chapter_number = db.Column(db.Integer, nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    voice_engine = db.Column(db.String(50), default='gtts')
    duration_seconds = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "book_id": self.book_id,
            "chapter_number": self.chapter_number,
            "file_path": self.file_path,
            "voice_engine": self.voice_engine,
            "duration_seconds": self.duration_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class Favorite(db.Model):
    __tablename__ = 'favorites'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    book = db.relationship('Book', lazy=True)

class ReadingHistory(db.Model):
    __tablename__ = 'reading_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    last_chapter_number = db.Column(db.Integer, default=1)
    last_position_seconds = db.Column(db.Float, default=0.0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    book = db.relationship('Book', lazy=True)

# ==========================================
# 3. UTILITY FUNCTIONS & PDF PARSER
# ==========================================
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({"error": "Admin privileges required"}), 403
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename: str, allowed_set: set) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

def extract_text_from_pdf(pdf_path: str) -> str:
    text = ""
    try:
        reader = pypdf.PdfReader(pdf_path)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n\n"
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {e}")
    return text

def auto_split_into_chapters(full_text: str, default_chunk_size: int = 4000) -> List[Dict[str, Any]]:
    chapters = []
    clean_text = full_text.strip()
    if not clean_text:
        return chapters

    pattern = re.compile(r'(?i)^(chapter\s+\d+|adhyaay\s+\d+|\d+\.\s+[A-Z])', re.MULTILINE)
    matches = list(pattern.finditer(clean_text))

    if len(matches) >= 2:
        chap_num = 1
        for i in range(len(matches)):
            start_idx = matches[i].start()
            end_idx = matches[i+1].start() if i + 1 < len(matches) else len(clean_text)
            chap_text = clean_text[start_idx:end_idx].strip()
            lines = chap_text.split('\n')
            first_line = lines[0].strip() if lines else f"Chapter {chap_num}"

            if re.match(r'(?i)^chapter\s+\d+$', first_line) and len(lines) > 1 and lines[1].strip():
                full_chap_title = f"{first_line}: {lines[1].strip()}"
                body_content = "\n".join(lines[2:]).strip()
            else:
                full_chap_title = first_line
                body_content = "\n".join(lines[1:]).strip()

            if not body_content and len(lines) > 1:
                body_content = chap_text
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
    try:
        os.makedirs(audio_dir, exist_ok=True)
    except Exception:
        pass

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
        "filename": filename,
        "duration_seconds": estimate_audio_duration(text),
        "voice_engine": engine
    }

# ==========================================
# 4. APP FACTORY & REST API ENDPOINTS
# ==========================================
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Enable CORS for frontend applications
    CORS(app, supports_credentials=True, origins="*")

    try:
        os.makedirs(Config.PDF_UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.COVER_UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.AUDIO_FOLDER, exist_ok=True)
    except Exception:
        pass

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # --- ROOT, DOCS & HEALTH CHECK ---
    @app.route('/', methods=['GET'])
    def root_info():
        return jsonify({
            "service": "Pustika Backend REST API Server",
            "status": "online",
            "version": "1.0.0",
            "documentation": "/docs",
            "endpoints": {
                "docs": "/docs",
                "health": "/api/health",
                "books": "/api/books",
                "categories": "/api/categories",
                "auth_me": "/api/me"
            }
        }), 200

    @app.route('/docs', methods=['GET'])
    @app.route('/swagger', methods=['GET'])
    def swagger_ui():
        html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Pustika REST API - Swagger UI</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
  <link rel="icon" type="image/png" href="https://unpkg.com/swagger-ui-dist@5/favicon-32x32.png" />
  <style>
    html { box-sizing: border-box; overflow-y: scroll; }
    *, *:before, *:after { box-sizing: inherit; }
    body { margin: 0; background: #0f172a; color: #f8fafc; font-family: sans-serif; }
    .swagger-ui .topbar { display: none; }
    .swagger-ui { max-width: 1200px; margin: 0 auto; padding: 20px; }
    .swagger-ui .info .title { color: #f59e0b; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js" charset="UTF-8"></script>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js" charset="UTF-8"></script>
  <script>
    window.onload = function() {
      window.ui = SwaggerUIBundle({
        url: "/swagger.json",
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIStandalonePreset
        ],
        layout: "BaseLayout"
      });
    };
  </script>
</body>
</html>"""
        return make_response(html_content)

    @app.route('/swagger.json', methods=['GET'])
    def swagger_json():
        return jsonify({
            "openapi": "3.0.0",
            "info": {
                "title": "Pustika REST API Documentation",
                "version": "1.0.0",
                "description": "Interactive Swagger OpenAPI 3.0 documentation for Pustika E-Book & Audiobook Backend API."
            },
            "servers": [
                {"url": "https://pustika-backend.vercel.app", "description": "Production Backend"},
                {"url": "http://127.0.0.1:5000", "description": "Local Backend"}
            ],
            "paths": {
                "/api/health": {
                    "get": {
                        "tags": ["System"],
                        "summary": "Health Check Status",
                        "responses": {"200": {"description": "API status online"}}
                    }
                },
                "/api/register": {
                    "post": {
                        "tags": ["Authentication"],
                        "summary": "User Registration",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "username": {"type": "string"},
                                            "email": {"type": "string"},
                                            "password": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        },
                        "responses": {"201": {"description": "Registered successfully"}}
                    }
                },
                "/api/login": {
                    "post": {
                        "tags": ["Authentication"],
                        "summary": "User Login",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "email": {"type": "string"},
                                            "password": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        },
                        "responses": {"200": {"description": "Logged in successfully"}}
                    }
                },
                "/api/logout": {
                    "post": {
                        "tags": ["Authentication"],
                        "summary": "User Logout",
                        "responses": {"200": {"description": "Logged out successfully"}}
                    }
                },
                "/api/me": {
                    "get": {
                        "tags": ["Authentication"],
                        "summary": "Get Current Logged-in User Profile",
                        "responses": {"200": {"description": "User details"}}
                    }
                },
                "/api/categories": {
                    "get": {
                        "tags": ["Categories"],
                        "summary": "Get List of Book Categories",
                        "responses": {"200": {"description": "Categories list"}}
                    }
                },
                "/api/books": {
                    "get": {
                        "tags": ["Books"],
                        "summary": "Get Catalog of Books",
                        "parameters": [
                            {"name": "q", "in": "query", "schema": {"type": "string"}, "description": "Search keyword"},
                            {"name": "category", "in": "query", "schema": {"type": "string"}, "description": "Category slug"}
                        ],
                        "responses": {"200": {"description": "List of books"}}
                    },
                    "post": {
                        "tags": ["Books (Admin)"],
                        "summary": "Upload PDF Book & Split Chapters",
                        "responses": {"201": {"description": "Book created"}}
                    }
                },
                "/api/books/{book_id}": {
                    "get": {
                        "tags": ["Books"],
                        "summary": "Get Book Details and Chapter List",
                        "parameters": [{"name": "book_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                        "responses": {"200": {"description": "Book details"}}
                    },
                    "delete": {
                        "tags": ["Books (Admin)"],
                        "summary": "Delete Book",
                        "parameters": [{"name": "book_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                        "responses": {"200": {"description": "Book deleted"}}
                    }
                },
                "/api/chapters/{chapter_id}": {
                    "get": {
                        "tags": ["Chapters & Audio"],
                        "summary": "Get Chapter Text Content",
                        "parameters": [{"name": "chapter_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                        "responses": {"200": {"description": "Chapter text"}}
                    }
                },
                "/api/chapters/{chapter_id}/audio": {
                    "post": {
                        "tags": ["Chapters & Audio"],
                        "summary": "Generate or Fetch Chapter Audio MP3",
                        "parameters": [{"name": "chapter_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                        "responses": {"200": {"description": "Audio file information"}}
                    }
                },
                "/api/favorites": {
                    "get": {
                        "tags": ["Favorites"],
                        "summary": "Get Favorite Books",
                        "responses": {"200": {"description": "Favorite books list"}}
                    }
                },
                "/api/favorites/{book_id}": {
                    "post": {
                        "tags": ["Favorites"],
                        "summary": "Toggle Favorite State for Book",
                        "parameters": [{"name": "book_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                        "responses": {"200": {"description": "Favorite state updated"}}
                    }
                }
            }
        })

    @app.route('/favicon.ico', methods=['GET'])
    def favicon():
        return '', 204

    @app.route('/api/health', methods=['GET'])
    def health_check():
        return jsonify({"status": "ok", "service": "Pustika Backend REST API", "timestamp": datetime.utcnow().isoformat()})

    # --- AUTHENTICATION ENDPOINTS ---
    @app.route('/api/register', methods=['POST'])
    def api_register():
        data = request.get_json() or request.form
        username = data.get('username', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '').strip()

        if not username or not email or not password:
            return jsonify({"error": "Username, email, and password are required"}), 400

        if User.query.filter_by(username=username).first():
            return jsonify({"error": "Username already exists"}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({"error": "Email already registered"}), 400

        user_count = User.query.count()
        is_admin = (user_count == 0)

        hashed = generate_password_hash(password)
        new_user = User(username=username, email=email, password_hash=hashed, is_admin=is_admin)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)

        return jsonify({"message": "Registration successful", "user": new_user.to_dict()}), 201

    @app.route('/api/login', methods=['POST'])
    def api_login():
        data = request.get_json() or request.form
        email = data.get('email', '').strip().lower()
        password = data.get('password', '').strip()

        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "Invalid email or password"}), 401

        login_user(user)
        return jsonify({"message": "Login successful", "user": user.to_dict()}), 200

    @app.route('/api/logout', methods=['POST'])
    def api_logout():
        if current_user.is_authenticated:
            logout_user()
        return jsonify({"message": "Logged out successfully"}), 200

    @app.route('/api/me', methods=['GET'])
    def api_me():
        if current_user.is_authenticated:
            return jsonify({"authenticated": True, "user": current_user.to_dict()})
        return jsonify({"authenticated": False, "user": None})

    # --- CATEGORIES ENDPOINT ---
    @app.route('/api/categories', methods=['GET'])
    def api_categories():
        categories = Category.query.all()
        return jsonify([c.to_dict() for c in categories])

    # --- BOOKS ENDPOINTS ---
    @app.route('/api/books', methods=['GET'])
    def api_get_books():
        query = request.args.get('q', '').strip()
        cat_slug = request.args.get('category', '').strip()

        book_query = Book.query
        if cat_slug:
            cat = Category.query.filter_by(slug=cat_slug).first()
            if cat:
                book_query = book_query.filter_by(category_id=cat.id)

        if query:
            search_pattern = f"%{query}%"
            book_query = book_query.filter(Book.title.ilike(search_pattern) | Book.author.ilike(search_pattern))

        books = book_query.order_by(Book.id.asc()).all()
        return jsonify([b.to_dict() for b in books])

    @app.route('/api/books/<int:book_id>', methods=['GET'])
    def api_get_book_detail(book_id):
        book = Book.query.get_or_404(book_id)
        return jsonify(book.to_dict(include_chapters=True))

    @app.route('/api/books', methods=['POST'])
    @admin_required
    def api_create_book():
        title = request.form.get('title', '').strip()
        author = request.form.get('author', '').strip()
        description = request.form.get('description', '').strip()
        category_id = request.form.get('category_id')

        if not title or not author:
            return jsonify({"error": "Title and Author are required"}), 400

        pdf_file = request.files.get('pdf_file')
        if not pdf_file or not allowed_file(pdf_file.filename, Config.ALLOWED_PDF_EXTENSIONS):
            return jsonify({"error": "A valid PDF file is required"}), 400

        # Save PDF
        pdf_filename = f"{uuid.uuid4().hex[:10]}_{secure_filename(pdf_file.filename)}"
        pdf_save_path = os.path.join(Config.PDF_UPLOAD_FOLDER, pdf_filename)
        pdf_file.save(pdf_save_path)

        # Cover image
        cover_filename = 'covers/default.jpg'
        cover_file = request.files.get('cover_image')
        if cover_file and allowed_file(cover_file.filename, Config.ALLOWED_IMAGE_EXTENSIONS):
            c_name = f"{uuid.uuid4().hex[:10]}_{secure_filename(cover_file.filename)}"
            c_path = os.path.join(Config.COVER_UPLOAD_FOLDER, c_name)
            cover_file.save(c_path)
            cover_filename = f"covers/{c_name}"

        # Create Book model
        new_book = Book(
            title=title,
            author=author,
            description=description,
            cover_image=cover_filename,
            pdf_file=f"pdfs/{pdf_filename}",
            category_id=int(category_id) if category_id and category_id.isdigit() else None
        )
        db.session.add(new_book)
        db.session.commit()

        # Parse chapters from PDF
        extracted = extract_chapters_from_pdf(pdf_save_path)
        if not extracted:
            extracted = [{"chapter_number": 1, "title": "Chapter 1", "text_content": extract_text_from_pdf(pdf_save_path)}]

        for chap in extracted:
            c_model = Chapter(
                book_id=new_book.id,
                chapter_number=chap["chapter_number"],
                title=chap["title"],
                text_content=chap["text_content"]
            )
            db.session.add(c_model)

        db.session.commit()
        return jsonify({"message": "Book created and chapters split successfully", "book": new_book.to_dict(include_chapters=True)}), 201

    @app.route('/api/books/<int:book_id>', methods=['DELETE'])
    @admin_required
    def api_delete_book(book_id):
        book = Book.query.get_or_404(book_id)
        db.session.delete(book)
        db.session.commit()
        return jsonify({"message": f"Book '{book.title}' deleted successfully"})

    # --- CHAPTERS & AUDIO ENDPOINTS ---
    @app.route('/api/chapters/<int:chapter_id>', methods=['GET'])
    def api_get_chapter(chapter_id):
        chapter = Chapter.query.get_or_404(chapter_id)
        return jsonify(chapter.to_dict(include_text=True))

    @app.route('/api/chapters/<int:chapter_id>/audio', methods=['POST'])
    def api_get_chapter_audio(chapter_id):
        chapter = Chapter.query.get_or_404(chapter_id)
        
        # Check existing audio
        existing = AudioFile.query.filter_by(book_id=chapter.book_id, chapter_number=chapter.chapter_number).first()
        if existing:
            return jsonify({
                "audio": existing.to_dict(),
                "audio_url": f"/api/audio/{os.path.basename(existing.file_path)}"
            })

        # Generate audio
        try:
            audio_info = convert_text_to_audio(
                text=chapter.text_content,
                book_id=chapter.book_id,
                chapter_number=chapter.chapter_number
            )
            new_audio = AudioFile(
                book_id=chapter.book_id,
                chapter_number=chapter.chapter_number,
                file_path=audio_info["file_path"],
                voice_engine=audio_info["voice_engine"],
                duration_seconds=audio_info["duration_seconds"]
            )
            db.session.add(new_audio)
            db.session.commit()

            return jsonify({
                "audio": new_audio.to_dict(),
                "audio_url": f"/api/audio/{audio_info['filename']}"
            })
        except Exception as e:
            return jsonify({"error": f"Audio generation failed: {str(e)}"}), 500

    # --- SERVE AUDIO & COVER FILES ---
    @app.route('/api/audio/<filename>', methods=['GET'])
    def api_serve_audio(filename):
        return send_from_directory(Config.AUDIO_FOLDER, filename)

    @app.route('/api/covers/<filename>', methods=['GET'])
    def api_serve_covers(filename):
        return send_from_directory(Config.COVER_UPLOAD_FOLDER, filename)

    # --- FAVORITES & HISTORY ENDPOINTS ---
    @app.route('/api/favorites', methods=['GET'])
    @login_required
    def api_get_favorites():
        favs = Favorite.query.filter_by(user_id=current_user.id).all()
        return jsonify([f.book.to_dict() for f in favs if f.book])

    @app.route('/api/favorites/<int:book_id>', methods=['POST'])
    @login_required
    def api_toggle_favorite(book_id):
        existing = Favorite.query.filter_by(user_id=current_user.id, book_id=book_id).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
            return jsonify({"message": "Removed from favorites", "is_favorite": False})
        else:
            new_fav = Favorite(user_id=current_user.id, book_id=book_id)
            db.session.add(new_fav)
            db.session.commit()
            return jsonify({"message": "Added to favorites", "is_favorite": True})

    @app.errorhandler(404)
    def api_not_found(e):
        return jsonify({"error": "Resource or endpoint not found", "status": 404}), 404

    @app.errorhandler(500)
    def api_internal_error(e):
        return jsonify({"error": "Internal server error", "status": 500}), 500

    # --- SEED INITIAL DATABASE DATA ---
    with app.app_context():
        db.create_all()
        # Seed categories if empty
        if Category.query.count() == 0:
            cats = [
                Category(name="Novel & Fiction", slug="novel"),
                Category(name="Biographies", slug="biographies"),
                Category(name="Self Help", slug="self-help"),
                Category(name="Audio Story", slug="story"),
            ]
            db.session.bulk_save_objects(cats)
            db.session.commit()

    return app

app = create_app()

if __name__ == '__main__':
    print("Starting Pustika Pure REST API Backend...")
    app.run(host='0.0.0.0', port=5000, debug=True)
