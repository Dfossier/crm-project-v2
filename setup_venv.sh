#!/bin/bash

echo "🏛️  Louisiana Foundations CRM Setup"
echo "=================================================="

# Create virtual environment
echo "🐍 Creating virtual environment..."
python3 -m venv venv
if [ $? -ne 0 ]; then
    echo "❌ Error creating virtual environment!"
    exit 1
fi

# Activate virtual environment
echo "⚡ Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "📦 Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "📦 Installing required packages..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "❌ Error installing requirements!"
    exit 1
fi

# Create directories
echo "📁 Creating directory structure..."
mkdir -p data database exports logs
echo "   Created: data/"
echo "   Created: database/"
echo "   Created: exports/"
echo "   Created: logs/"
echo "✅ Directory structure created!"

# Initialize database
echo "🗄️  Initializing database..."
python3 run.py init
if [ $? -ne 0 ]; then
    echo "⚠️  Warning: Database initialization failed. You can try running 'python run.py init' later."
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "🚀 To use the system:"
echo "1. Activate virtual environment: source venv/bin/activate"
echo "2. Run data acquisition: python3 run.py acquire"
echo "3. Start web interface: python3 run.py webapp"
echo "4. Or export data: python3 run.py export"
echo ""
echo "📖 For more information, see README.md"