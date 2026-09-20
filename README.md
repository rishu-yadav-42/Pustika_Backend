# Pustika Backend - E-Book & Audiobook Flask API Server

Python Flask Backend server for **Pustika** platform featuring SQLite database models, ElevenLabs AI Text-to-Speech API integration, gTTS fallback engine, and smart PDF Unicode Hindi/English text extractor.

## 🚀 Quick Setup & Run

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure `.env`**:
   Copy `.env.example` to `.env` and set secret key or ElevenLabs key (optional).

3. **Initialize Database**:
   ```bash
   python seed_data.py
   ```

4. **Start Server**:
   ```bash
   python app.py
   ```
   Or double click `run_app.bat` on Windows.
