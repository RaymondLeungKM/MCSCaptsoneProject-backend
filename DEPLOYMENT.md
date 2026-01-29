# Backend Deployment Guide

## Prerequisites

- Linux server (Ubuntu 20.04+ or similar)
- SSH access with sudo privileges
- Domain name (optional but recommended)

## 1. Server Setup

### Update system packages

```bash
sudo apt update
sudo apt upgrade -y
```

### Install Python 3.11+

```bash
sudo apt install -y python3.11 python3.11-venv python3-pip
```

### Install PostgreSQL

```bash
sudo apt install -y postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### Install Nginx (reverse proxy)

```bash
sudo apt install -y nginx
sudo systemctl start nginx
sudo systemctl enable nginx
```

## 2. Database Setup

### Create PostgreSQL database and user

```bash
sudo -u postgres psql

# In PostgreSQL prompt:
CREATE DATABASE preschool_vocab_db;
CREATE USER vocab_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE preschool_vocab_db TO vocab_user;
ALTER DATABASE preschool_vocab_db OWNER TO vocab_user;
\q
```

### Configure PostgreSQL for remote connections (if needed)

```bash
sudo nano /etc/postgresql/14/main/postgresql.conf
# Change: listen_addresses = 'localhost' to listen_addresses = '*'

sudo nano /etc/postgresql/14/main/pg_hba.conf
# Add: host all all 0.0.0.0/0 md5

sudo systemctl restart postgresql
```

## 3. Application Deployment

### Create application directory

```bash
sudo mkdir -p /var/www/preschool-vocab-backend
sudo chown $USER:$USER /var/www/preschool-vocab-backend
```

### Upload your code

```bash
# From your local machine:
rsync -avz --exclude='__pycache__' --exclude='*.pyc' \
  /path/to/backend/ user@your-server:/var/www/preschool-vocab-backend/
```

Or clone from Git:

```bash
cd /var/www/preschool-vocab-backend
git clone https://github.com/yourusername/preschool-vocab-backend.git .
```

### Create virtual environment

```bash
cd /var/www/preschool-vocab-backend
python3.11 -m venv venv
source venv/bin/activate
```

### Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
pip install email-validator  # Required dependency
```

### Create production environment file

```bash
nano .env.production
```

Add:

```env
# Database
DATABASE_URL=postgresql+asyncpg://vocab_user:your_secure_password@localhost/preschool_vocab_db

# Security
SECRET_KEY=your-super-secret-key-min-32-chars-long-random-string
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# CORS
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# Environment
ENVIRONMENT=production
```

Generate secure SECRET_KEY:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Run database migrations

```bash
source venv/bin/activate
python -c "from app.db.session import init_db; import asyncio; asyncio.run(init_db())"
```

### Seed initial data (optional)

```bash
python seed_words.py
```

## 4. Process Management with Systemd

### Create systemd service file

```bash
sudo nano /etc/systemd/system/preschool-vocab.service
```

Add:

```ini
[Unit]
Description=Preschool Vocabulary Platform Backend
After=network.target postgresql.service

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/var/www/preschool-vocab-backend
Environment="PATH=/var/www/preschool-vocab-backend/venv/bin"
EnvironmentFile=/var/www/preschool-vocab-backend/.env.production
ExecStart=/var/www/preschool-vocab-backend/venv/bin/gunicorn \
    -k uvicorn.workers.UvicornWorker \
    -w 4 \
    --bind 127.0.0.1:8000 \
    --access-logfile /var/log/preschool-vocab/access.log \
    --error-logfile /var/log/preschool-vocab/error.log \
    --timeout 120 \
    main:app

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Set proper permissions

```bash
sudo chown -R www-data:www-data /var/www/preschool-vocab-backend
sudo mkdir -p /var/log/preschool-vocab
sudo chown www-data:www-data /var/log/preschool-vocab
```

### Start the service

```bash
sudo systemctl daemon-reload
sudo systemctl start preschool-vocab
sudo systemctl enable preschool-vocab
sudo systemctl status preschool-vocab
```

### View logs

```bash
sudo journalctl -u preschool-vocab -f
sudo tail -f /var/log/preschool-vocab/error.log
```

## 5. Nginx Reverse Proxy

### Create Nginx configuration

```bash
sudo nano /etc/nginx/sites-available/preschool-vocab-backend
```

Add:

```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }

    # Health check endpoint
    location /health {
        access_log off;
        proxy_pass http://127.0.0.1:8000/health;
    }
}
```

### Enable the site

```bash
sudo ln -s /etc/nginx/sites-available/preschool-vocab-backend /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 6. SSL/HTTPS Setup with Let's Encrypt

### Install Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx
```

### Obtain SSL certificate

```bash
sudo certbot --nginx -d api.yourdomain.com
```

Follow the prompts. Certbot will automatically update your Nginx config.

### Auto-renewal (already set up by default)

```bash
sudo certbot renew --dry-run
```

## 7. Security Hardening

### Configure firewall

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### Secure PostgreSQL

```bash
# Only allow local connections
sudo nano /etc/postgresql/14/main/pg_hba.conf
# Ensure: host all all 127.0.0.1/32 md5
sudo systemctl restart postgresql
```

### Set up fail2ban (optional)

```bash
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

## 8. Monitoring & Maintenance

### Check application status

```bash
sudo systemctl status preschool-vocab
curl http://localhost:8000/health
```

### View application logs

```bash
# Application logs
sudo journalctl -u preschool-vocab -n 100 --no-pager

# Nginx access logs
sudo tail -f /var/log/nginx/access.log

# Nginx error logs
sudo tail -f /var/log/nginx/error.log
```

### Database backup

```bash
# Create backup script
sudo nano /usr/local/bin/backup-vocab-db.sh
```

Add:

```bash
#!/bin/bash
BACKUP_DIR="/var/backups/preschool-vocab"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
pg_dump -U vocab_user preschool_vocab_db | gzip > $BACKUP_DIR/backup_$DATE.sql.gz
# Keep only last 7 days
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete
```

Make executable and schedule:

```bash
sudo chmod +x /usr/local/bin/backup-vocab-db.sh
sudo crontab -e
# Add: 0 2 * * * /usr/local/bin/backup-vocab-db.sh
```

### Update deployment

```bash
cd /var/www/preschool-vocab-backend
git pull origin main  # or rsync new files
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart preschool-vocab
```

## 9. Testing the Deployment

### Test API endpoints

```bash
# Health check
curl https://api.yourdomain.com/health

# API docs
curl https://api.yourdomain.com/docs

# Test login
curl -X POST https://api.yourdomain.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"yourpassword"}'
```

### Performance testing

```bash
# Install Apache Bench
sudo apt install apache2-utils

# Load test
ab -n 1000 -c 10 https://api.yourdomain.com/health
```

## 10. Troubleshooting

### Application won't start

```bash
# Check logs
sudo journalctl -u preschool-vocab -n 50

# Check if port is in use
sudo netstat -tulpn | grep 8000

# Test manually
cd /var/www/preschool-vocab-backend
source venv/bin/activate
python main.py
```

### Database connection issues

```bash
# Test database connection
sudo -u postgres psql preschool_vocab_db

# Check PostgreSQL status
sudo systemctl status postgresql

# View PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-14-main.log
```

### Nginx 502 Bad Gateway

```bash
# Check if app is running
sudo systemctl status preschool-vocab

# Check Nginx error logs
sudo tail -f /var/log/nginx/error.log

# Test backend directly
curl http://127.0.0.1:8000/health
```

## Production Checklist

- [ ] PostgreSQL database created and secured
- [ ] Environment variables set in `.env.production`
- [ ] Strong SECRET_KEY generated
- [ ] Database migrations run
- [ ] Systemd service configured and running
- [ ] Nginx reverse proxy configured
- [ ] SSL certificate installed (HTTPS)
- [ ] Firewall configured (UFW)
- [ ] CORS origins updated for production domain
- [ ] Database backups scheduled
- [ ] Log rotation configured
- [ ] Monitoring set up (optional: New Relic, DataDog)
- [ ] Update frontend `NEXT_PUBLIC_API_URL` to production domain

## Environment Variables Reference

```env
# Required
DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname
SECRET_KEY=your-secret-key-here

# Optional
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
ALLOWED_ORIGINS=https://yourdomain.com
ENVIRONMENT=production
LOG_LEVEL=info
```

## Quick Commands Reference

```bash
# Restart application
sudo systemctl restart preschool-vocab

# View logs
sudo journalctl -u preschool-vocab -f

# Check status
sudo systemctl status preschool-vocab

# Test Nginx config
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx

# Database backup
pg_dump -U vocab_user preschool_vocab_db > backup.sql

# Database restore
psql -U vocab_user preschool_vocab_db < backup.sql
```
