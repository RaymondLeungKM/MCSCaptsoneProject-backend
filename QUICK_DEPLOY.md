# Quick Deployment Guide - Bare Minimum

## Prerequisites

- Ubuntu/Debian Linux server
- SSH access with sudo

## 1. Install Dependencies (5 minutes)

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python, PostgreSQL, and Nginx
sudo apt install -y python3.11 python3.11-venv python3-pip postgresql postgresql-contrib nginx
```

## 2. Setup Database (2 minutes)

```bash
# Create database and user
sudo -u postgres psql << EOF
CREATE DATABASE preschool_vocab_db;
CREATE USER vocab_user WITH PASSWORD 'postgres2026';
GRANT ALL PRIVILEGES ON DATABASE preschool_vocab_db TO vocab_user;
ALTER DATABASE preschool_vocab_db OWNER TO vocab_user;
\q
EOF
```

## 3. Deploy Application (5 minutes)

```bash
# Create directory
sudo mkdir -p /home/ubuntu/preschool-vocabulary-platform/backend
sudo chown ubuntu:ubuntu /home/ubuntu/preschool-vocabulary-platform/backend
cd /home/ubuntu/preschool-vocabulary-platform/backend

# Upload your code (from local machine)
# rsync -avz /path/to/backend/ ubuntu@server:/home/ubuntu/preschool-vocabulary-platform/backend/
# OR clone from git:
# git clone <your-repo-url> .

# Setup virtual environment
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt gunicorn email-validator

# Create environment file (include ASYNC_DATABASE_URL!)
cat > .env << 'EOF'
DATABASE_URL=postgresql+asyncpg://vocab_user:postgres2026@localhost/preschool_vocab_db
ASYNC_DATABASE_URL=postgresql+asyncpg://vocab_user:postgres2026@localhost/preschool_vocab_db
SECRET_KEY=CHANGE_THIS_TO_RANDOM_SECRET_KEY
EOF

# Generate a secure secret key and update .env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))" >> .env

# Verify .env file contents
echo "=== Checking .env file ==="
cat .env
echo "=========================="

# Create database initialization script
cat > init_db.py << 'EOF'
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Verify environment variables are loaded
db_url = os.getenv('DATABASE_URL')
print(f"DATABASE_URL from env: {db_url}")

if not db_url or 'vocab_user' not in db_url:
    print("ERROR: DATABASE_URL not loaded correctly from .env file!")
    print("Please check that .env file exists and contains:")
    print("DATABASE_URL=postgresql+asyncpg://vocab_user:postgres2026@localhost/preschool_vocab_db")
    print("ASYNC_DATABASE_URL=postgresql+asyncpg://vocab_user:postgres2026@localhost/preschool_vocab_db")
    exit(1)

from app.db.session import engine
from app.db.base import Base
# Import models so metadata is populated
from app.models import vocabulary  # noqa: F401
from app.models import user  # noqa: F401

async def init_db():
    print("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('✓ Database tables created successfully!')

asyncio.run(init_db())
EOF

# Install python-dotenv if not already installed
pip install python-dotenv

# Initialize database
python init_db.py

python seed_words.py  # Optional: seed sample data
```

## 4. Run Application (2 minutes)

### Option A: Run Directly (for testing)

```bash
cd /home/ubuntu/preschool-vocabulary-platform/backend
source venv/bin/activate
gunicorn -k uvicorn.workers.UvicornWorker -w 2 --bind 0.0.0.0:8000 main:app
```

### Option B: Run as Service (recommended)

```bash
# Create service file (paths match /home/ubuntu/preschool-vocabulary-platform/backend)
sudo tee /etc/systemd/system/preschool-vocab.service << EOF
[Unit]
Description=Preschool Vocab Backend
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/preschool-vocabulary-platform/backend
Environment="PATH=/home/ubuntu/preschool-vocabulary-platform/backend/venv/bin"
EnvironmentFile=/home/ubuntu/preschool-vocabulary-platform/backend/.env
ExecStart=/home/ubuntu/preschool-vocabulary-platform/backend/venv/bin/gunicorn -k uvicorn.workers.UvicornWorker -w 2 --bind 0.0.0.0:8000 main:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Start service
sudo systemctl daemon-reload
sudo systemctl start preschool-vocab
sudo systemctl enable preschool-vocab
sudo systemctl status preschool-vocab
```

## 5. Setup Nginx (2 minutes)

```bash
# Create nginx config
sudo tee /etc/nginx/sites-available/preschool-vocab << EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/preschool-vocab /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default  # Remove default site
sudo nginx -t
sudo systemctl restart nginx
```

## 6. Test It

```bash
# Test locally
curl http://localhost:8000/docs

# Test through nginx
curl http://your-server-ip/docs
```

Your backend is now running at:

- **Direct:** http://your-server-ip:8000
- **Through Nginx:** http://your-server-ip

## Quick Commands

```bash
# View logs
sudo journalctl -u preschool-vocab -f

# Restart service
sudo systemctl restart preschool-vocab

# Stop service
sudo systemctl stop preschool-vocab

# Update code
cd /home/ubuntu/preschool-vocabulary-platform/backend
git pull  # or upload new files
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart preschool-vocab
```

## Firewall (Optional but Recommended)

```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw enable
```

## Next Steps (Optional)

- Add SSL certificate with Let's Encrypt: `sudo certbot --nginx`
- Setup database backups
- Configure monitoring
- Use stronger database password
- Restrict CORS origins in `.env`

---

**Total Setup Time: ~15 minutes**

That's it! Your backend is deployed and running.
