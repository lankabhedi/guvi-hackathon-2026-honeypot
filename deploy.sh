#!/bin/bash
# Deployment script for Honey-Pot API

echo "🚀 Deploying Agentic Honey-Pot API..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed"
    exit 1
fi

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed"
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
pip3 install -r requirements.txt --break-system-packages

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cat > .env << EOF
GROQ_API_KEY=your_groq_api_key_here
API_KEY=hackathon-api-key-2026
DATABASE_URL=sqlite:///./honeypot.db
PORT=8001
EOF
    echo "⚠️  Please edit .env and add your actual GROQ_API_KEY"
fi

# Initialize database
echo "🗄️  Initializing database..."
python3 -c "from app.database import init_db; init_db()"

# Kill existing server if running
pkill -f "python3 app/main.py" 2>/dev/null || true

# Start server
echo "🌐 Starting server on port 8001..."
nohup python3 app/main.py > server.log 2>&1 &

# Wait for server to start
sleep 3

# Test if server is running
if curl -s http://localhost:8001/health | grep -q "healthy"; then
    echo "✅ Server is running!"
    echo ""
    echo "📋 API Endpoints:"
    echo "   Health:  http://localhost:8001/health"
    echo "   Honeypot: http://localhost:8001/honeypot"
    echo ""
    echo "🔑 API Key: $(grep API_KEY .env | cut -d= -f2)"
    echo ""
    echo "📊 View logs: tail -f server.log"
    echo "🧪 Run tests: python3 test_api.py"
else
    echo "❌ Server failed to start. Check server.log"
    exit 1
fi
