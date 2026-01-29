# Preschool Vocabulary Platform - FastAPI Backend

A comprehensive FastAPI backend for managing vocabulary learning for preschool children with adaptive learning, progress tracking, and multi-sensory engagement features.

## Features

### Core Functionality

- **User Management**: Parent authentication and child profile management
- **Vocabulary System**: Words, categories, and personalized learning paths
- **Content Delivery**: Interactive stories, games, and missions
- **Progress Tracking**: Detailed analytics and learning session monitoring
- **Adaptive Learning**: AI-powered recommendations based on child's learning style and progress
- **Multi-sensory Learning**: Visual, auditory, and kinesthetic learning modes

### Key Technologies

- **FastAPI**: Modern, fast web framework
- **SQLAlchemy 2.0**: Async ORM with PostgreSQL
- **Pydantic**: Data validation and settings management
- **JWT**: Secure authentication
- **Redis**: Caching and session management
- **Celery**: Background task processing

## Project Structure

```
backend/
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variables template
├── alembic/               # Database migrations
├── app/
│   ├── api/
│   │   ├── __init__.py    # API router aggregation
│   │   └── endpoints/     # API endpoints
│   │       ├── auth.py           # Authentication
│   │       ├── users.py          # User management
│   │       ├── children.py       # Child profiles
│   │       ├── vocabulary.py     # Word management
│   │       ├── categories.py     # Category management
│   │       ├── stories.py        # Story content
│   │       ├── games.py          # Game management
│   │       ├── missions.py       # Mission system
│   │       ├── progress.py       # Progress tracking
│   │       ├── analytics.py      # Analytics & stats
│   │       └── adaptive_learning.py  # AI recommendations
│   ├── core/
│   │   ├── config.py      # App configuration
│   │   └── security.py    # Security utilities (JWT, hashing)
│   ├── db/
│   │   ├── base.py        # SQLAlchemy base
│   │   └── session.py     # Database session management
│   ├── models/            # SQLAlchemy models
│   │   ├── user.py        # User & Child models
│   │   ├── vocabulary.py  # Word & Category models
│   │   ├── content.py     # Story, Game, Mission models
│   │   └── analytics.py   # Learning session & stats models
│   ├── schemas/           # Pydantic schemas
│   │   ├── user.py
│   │   ├── vocabulary.py
│   │   ├── content.py
│   │   └── analytics.py
│   ├── services/          # Business logic
│   │   ├── adaptive_learning.py  # Adaptive learning engine
│   │   ├── progress.py           # Progress calculation
│   │   └── speech.py             # Speech processing
│   └── utils/             # Utility functions
```

## Database Models

### User Models

- **User**: Parent/guardian accounts
- **Child**: Child profiles with learning preferences
- **ChildInterest**: Child's category preferences

### Vocabulary Models

- **Category**: Word categories (Animals, Food, etc.)
- **Word**: Vocabulary words with multi-sensory content
- **WordProgress**: Child's progress on individual words

### Content Models

- **Story**: Interactive stories with dialogic reading prompts
- **StoryProgress**: Story completion tracking
- **Game**: Learning games with characteristics
- **Mission**: Daily and offline missions
- **MissionProgress**: Mission completion tracking

### Analytics Models

- **LearningSession**: Individual session tracking
- **DailyStats**: Daily aggregated statistics
- **Achievement**: Achievement/badge definitions
- **ChildAchievement**: Earned achievements

## API Endpoints

### Authentication

- `POST /api/v1/auth/register` - Register new parent user
- `POST /api/v1/auth/login` - Login and get JWT token
- `POST /api/v1/auth/token` - OAuth2 compatible token endpoint

### User Management

- `GET /api/v1/users/me` - Get current user profile
- `PATCH /api/v1/users/me` - Update user profile

### Children

- `POST /api/v1/children` - Create child profile
- `GET /api/v1/children` - List all children for user
- `GET /api/v1/children/{child_id}` - Get child profile with stats
- `PATCH /api/v1/children/{child_id}` - Update child profile
- `DELETE /api/v1/children/{child_id}` - Delete child profile

### Vocabulary

- `GET /api/v1/vocabulary` - List words (with filters)
- `GET /api/v1/vocabulary/{word_id}` - Get word details
- `GET /api/v1/vocabulary/child/{child_id}` - Get words with progress
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
