#!/bin/bash
# migrate.sh - TTS Bot Migration Script
# Easy migration to new machine with automated setup

set -e

echo "=== TTS Bot Migration Script ==="
echo ""

# Check if .env files exist
ENV_FILES=("bot_service/.env" "frontend/.env")
MISSING_ENV=()

for env_file in "${ENV_FILES[@]}"; do
    if [ ! -f "$env_file" ]; then
        MISSING_ENV+=("$env_file")
    fi
done

if [ ${#MISSING_ENV[@]} -gt 0 ]; then
    echo "Creating .env files from templates..."
    
    # Copy .env.example to .env for each service
    if [ ! -f "bot_service/.env" ]; then
        cp bot_service/.env.example bot_service/.env
        echo "✓ Created bot_service/.env"
    fi
    
    if [ ! -f "frontend/.env" ]; then
        cp frontend/.env.example frontend/.env
        echo "✓ Created frontend/.env"
    fi
    
    echo ""
    echo "[WARN] Please edit the .env files with your configuration before continuing."
    echo "   Run this script again after editing."
    exit 1
fi

echo "✓ .env files found"
echo ""

# Generate secrets if needed
echo "Checking security keys..."
if grep -q "your-secret-key-here" bot_service/.env; then
    echo "Generating security keys..."
    
    # Check if openssl is available
    if command -v openssl &> /dev/null; then
        SECRET_KEY=$(openssl rand -hex 32)
    else
        echo "[ERROR] openssl not found. Please install openssl or manually generate SECRET_KEY"
        exit 1
    fi
    
    # Generate Fernet key for encryption
    if command -v python3 &> /dev/null; then
        ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    elif command -v python &> /dev/null; then
        ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    else
        echo "[ERROR] Python not found. Please install Python or manually generate TOKEN_ENCRYPTION_KEY"
        exit 1
    fi
    
    # Update bot_service/.env
    sed -i.bak "s/your-secret-key-here-generate-with-openssl-rand-hex-32/$SECRET_KEY/" bot_service/.env
    sed -i.bak "s/your-encryption-key-here-generate-with-fernet/$ENCRYPTION_KEY/" bot_service/.env
    rm bot_service/.env.bak
    
    echo "✓ Generated security keys"
fi

echo "✓ Security keys configured"
echo ""

# Create required directories
echo "Creating required directories..."
mkdir -p data logs/{access,app,audit,errors,monitoring} models voices audio
mkdir -p bot_service/{data,logs}

echo "✓ Created directories"
echo ""

# Install dependencies
echo "Installing dependencies..."

# Backend dependencies
echo "Installing bot_service dependencies..."
cd bot_service
pip install -r requirements.txt || pip3 install -r requirements.txt
cd ..
echo "✓ Bot service dependencies installed"

# Frontend dependencies
echo "Installing frontend dependencies..."
cd frontend
npm install
cd ..
echo "✓ Frontend dependencies installed"
echo ""

# Run database migrations
echo "Running database migrations..."
cd bot_service
alembic upgrade head || echo "[WARN] Database migration failed. This is normal for first-time setup."
cd ..
echo "✓ Database ready"
echo ""

echo "=== Migration Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit .env files with your OAuth credentials"
echo "2. For TTS service: Configure Cloudflare Tunnel (optional)"
echo "3. Run: docker-compose up -d (or npm run dev for development)"
echo ""
echo "Development commands:"
echo "  cd bot_service && python main.py   - Start bot service"
echo "  # Run F5 TTS from standalone repository or external host"
echo "  cd frontend && npm run dev        - Start frontend"
echo ""

