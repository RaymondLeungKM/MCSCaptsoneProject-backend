# Preschool Vocabulary Platform - Backend API

FastAPI backend for a Cantonese/English vocabulary learning platform for preschool children.

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 13+
- pip and virtualenv

### Local Development Setup

1. **Create virtual environment**

```bash
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. **Install dependencies**

```bash
pip install -r requirements.txt
```

3. **Configure environment**

```bash
cp .env.example .env
# Edit .env with your database credentials
```

4. **Initialize database**

```bash
python init_db.py
```

5. **Seed data (optional)**

```bash
python seed_database.py           # Comprehensive vocabulary with 100+ words
```

6. **Run development server**

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Visit: http://localhost:8000/docs for API documentation

## 📚 Features

- **User Management**: Parent/child accounts with authentication
- **Vocabulary System**: Words, categories, progress tracking
- **Content Generation**: AI-powered stories and sentences (Ollama integration)
- **Learning Analytics**: Detailed progress tracking and insights
- **Multi-language Support**: English and Cantonese (Traditional Chinese with Jyutping)
- **Adaptive Learning**: Personalized learning paths based on child's progress

## 🗂️ Project Structure

```
backend/
├── main.py                      # Application entry point
├── init_db.py                   # Database initialization script
├── seed_words.py                # English vocabulary data
├── seed_cantonese_words.py      # Cantonese vocabulary data
├── requirements.txt             # Python dependencies
├── .env                         # Environment variables (create from .env.example)
├── alembic/                     # Database migrations
└── app/
    ├── api/endpoints/           # API route handlers
    ├── core/                    # Configuration and security
    ├── db/                      # Database session and base
    ├── models/                  # SQLAlchemy models
    ├── schemas/                 # Pydantic schemas
    └── services/                # Business logic
```

## 🔧 Key Technologies

- **FastAPI** - Modern async web framework
- **SQLAlchemy 2.0** - Async ORM with PostgreSQL
- **Pydantic** - Data validation
- **JWT** - Authentication
- **Ollama** - Local LLM for content generation (optional)

## 📖 API Endpoints

### Authentication
- `POST /auth/register` - Register new parent account
- `POST /auth/login` - Login
- `GET /auth/me` - Get current user

### Children
- `GET /children` - List all children for parent
- `POST /children` - Create child profile
- `GET /children/{id}` - Get child details
- `PUT /children/{id}` - Update child profile

### Vocabulary
- `GET /vocabulary/words` - List words (with filters)
- `GET /vocabulary/categories` - List categories
- `GET /vocabulary/words/{id}` - Get word details
- `POST /vocabulary/progress` - Update learning progress

### Content
- `POST /stories/generate` - Generate AI story
- `GET /stories/{id}` - Get story details
- `POST /sentences/generate` - Generate example sentences

### Analytics
- `GET /analytics/child/{id}/daily-stats` - Daily learning stats
- `GET /analytics/child/{id}/progress` - Overall progress
- `GET /analytics/child/{id}/insights` - Learning insights

Full API documentation available at `/docs` when server is running.

## 🌍 Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost/dbname
ASYNC_DATABASE_URL=postgresql+asyncpg://user:password@localhost/dbname

# Security
SECRET_KEY=your-secret-key-here

# CORS (comma-separated)
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001

# Ollama (optional - for AI content generation)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:1b
```

## 🗄️ Database Models

- **User** - Parent accounts
- **Child** - Child profiles with learning preferences
- **Category** - Vocabulary categories
- **Word** - Vocabulary words with Cantonese/English
- **WordProgress** - Individual word learning progress
- **LearningSession** - Learning activity sessions
- **Story** - Generated stories
- **GeneratedSentence** - Example sentences
- **DailyLearningStats** - Daily aggregated statistics
- **WeeklyReport** - Weekly progress reports

## 🚢 Production Deployment

See [VM_SETUP_GUIDE.md](../VM_SETUP_GUIDE.md) in the parent directory for complete production setup instructions.

### Quick Production Checklist

- [ ] Set strong SECRET_KEY
- [ ] Configure production database
- [ ] Set ALLOWED_ORIGINS to your frontend domain
- [ ] Use HTTPS with SSL certificates
- [ ] Set up database backups
- [ ] Configure monitoring and logging
- [ ] Use systemd service for auto-restart
- [ ] Set up Nginx reverse proxy

## 🛠️ Development Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Run development server
uvicorn main:app --reload

# Run with custom host/port
uvicorn main:app --host 0.0.0.0 --port 8000

# Create database migration
alembic revision --autogenerate -m "description"

# Run migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

## 🐛 Troubleshooting

### Database Connection Issues

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Test connection
psql -h localhost -U your_user -d your_db
```

### Import Errors

Make sure all model modules are imported before database initialization. The `init_db.py` script imports all necessary models.

### Module Not Found

```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

## 📝 License

This project is for educational purposes.

---

**For complete VM setup instructions, see**: [VM_SETUP_GUIDE.md](../VM_SETUP_GUIDE.md)

- `POST /api/v1/vocabulary` - Create word (admin)
- `PATCH /api/v1/vocabulary/{word_id}` - Update word

### Categories

- `GET /api/v1/categories` - List all categories
- `GET /api/v1/categories/{category_id}/words` - Get words in category
- `POST /api/v1/categories` - Create category (admin)

### Stories

- `GET /api/v1/stories` - List stories
- `GET /api/v1/stories/{story_id}` - Get story with pages
- `GET /api/v1/stories/child/{child_id}` - Get stories with progress
- `POST /api/v1/stories/{story_id}/progress` - Update story progress

### Games

- `GET /api/v1/games` - List available games
- `GET /api/v1/games/{game_id}` - Get game details
- `POST /api/v1/games/{game_id}/play` - Record game session

### Missions

- `GET /api/v1/missions/daily/{child_id}` - Get today's missions
- `GET /api/v1/missions/offline/{child_id}` - Get offline missions
- `POST /api/v1/missions/{mission_id}/complete` - Mark mission complete

### Progress

- `GET /api/v1/progress/{child_id}` - Get overall progress stats
- `GET /api/v1/progress/{child_id}/words` - Get word-level progress
- `POST /api/v1/progress/{child_id}/session` - Start learning session
- `PATCH /api/v1/progress/session/{session_id}` - End learning session

### Analytics

- `GET /api/v1/analytics/{child_id}/daily` - Get daily stats
- `GET /api/v1/analytics/{child_id}/weekly` - Get weekly summary
- `GET /api/v1/analytics/{child_id}/achievements` - Get achievements

### Adaptive Learning

- `GET /api/v1/adaptive/{child_id}/recommendations` - Get personalized recommendations
- `GET /api/v1/adaptive/{child_id}/word-of-the-day` - Get word of the day
- `GET /api/v1/adaptive/{child_id}/next-activity` - Get next recommended activity

## Setup Instructions

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis (optional, for caching)

### 2. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Environment Configuration

```bash
cp .env.example .env
# Edit .env with your configuration
```

### 4. Database Setup

```bash
# Create PostgreSQL database
createdb preschool_vocab

# Run migrations
alembic upgrade head
```

### 5. Run Development Server

```bash
# Development mode with auto-reload
python main.py

# Or with uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Access API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

## Development

### Adding New Endpoints

1. Create endpoint file in `app/api/endpoints/`
2. Define routes using FastAPI router
3. Add router to `app/api/__init__.py`

### Adding New Models

1. Create model in appropriate file in `app/models/`
2. Create corresponding Pydantic schemas in `app/schemas/`
3. Generate migration: `alembic revision --autogenerate -m "add_model_name"`
4. Apply migration: `alembic upgrade head`

## Adaptive Learning Algorithm

The system uses a sophisticated adaptive learning algorithm that considers:

- **Exposure Count**: 6-12 exposures needed for retention
- **Learning Style**: Visual, auditory, kinesthetic, or mixed
- **Interest Alignment**: Prioritizes preferred categories
- **Spacing Effect**: Optimal review timing (3-7 days)
- **Difficulty Matching**: Appropriate challenge level
- **Active vs Passive**: Distinguishes output vs recognition

## Security

- JWT-based authentication
- Password hashing with bcrypt
- CORS protection
- SQL injection prevention via SQLAlchemy
- Input validation via Pydantic

## Testing

```bash
# Run tests
pytest

# With coverage
pytest --cov=app tests/
```

## Deployment

### Docker

```bash
docker build -t preschool-vocab-api .
docker run -p 8000:8000 preschool-vocab-api
```

### Production Considerations

- Use production-grade ASGI server (Gunicorn + Uvicorn)
- Enable HTTPS
- Configure proper CORS origins
- Set strong SECRET_KEY
- Use environment-specific database
- Enable logging and monitoring
- Configure Redis for caching
- Set up Celery for background tasks

## License

MIT License
