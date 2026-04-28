#!/bin/bash
set -e

echo "=========================================="
echo "Charleston County Lead Scraper - First Run"
echo "=========================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Creating from template..."
    cp .env.example .env
    echo ""
    echo "✏️  IMPORTANT: Edit .env and add your Supabase credentials:"
    echo "    SUPABASE_URL=https://your-project.supabase.co"
    echo "    SUPABASE_SERVICE_KEY=eyJhbGciOi..."
    echo ""
    echo "Press Enter when you've filled in .env..."
    read
fi

# Check if Supabase vars are set
source .env
if [ -z "$SUPABASE_URL" ] || [ "$SUPABASE_URL" = "https://your-project.supabase.co" ]; then
    echo "❌ SUPABASE_URL not set in .env. Exiting."
    exit 1
fi
if [ -z "$SUPABASE_SERVICE_KEY" ] || [ "$SUPABASE_SERVICE_KEY" = "eyJhbGciOi..." ]; then
    echo "❌ SUPABASE_SERVICE_KEY not set in .env. Exiting."
    exit 1
fi

echo "✅ Environment configured"
echo ""

# Install Python dependencies
echo "📦 Installing Python dependencies..."
python -m pip install -r requirements.txt --quiet
echo "✅ Python packages installed"
echo ""

# Install Playwright browsers
echo "🎭 Installing Playwright browsers..."
python -m playwright install chromium --with-deps
echo "✅ Playwright ready"
echo ""

# Run tests
echo "🧪 Running tests..."
PYTHONPATH=. python -m pytest tests/ -v
echo "✅ All tests passed"
echo ""

# Offer to run a sample scraper
echo "=========================================="
echo "Setup complete! Ready to scrape."
echo "=========================================="
echo ""
echo "What would you like to do?"
echo "  1) Run a test scraper (Real Property Tax Sale XLSX)"
echo "  2) Run all daily fast scrapers"
echo "  3) Skip for now"
echo ""
read -p "Choice [1/2/3]: " choice

case $choice in
    1)
        echo ""
        echo "Running Real Property Tax Sale scraper..."
        PYTHONPATH=. python -m scrapers.rp_tax_sale
        ;;
    2)
        echo ""
        echo "Running all fast scrapers (XLSX + HTML + PDF)..."
        PYTHONPATH=. python -m scheduler.runner fast
        ;;
    *)
        echo ""
        echo "Skipping. You can run scrapers anytime with:"
        echo "  PYTHONPATH=. python -m scheduler.runner fast"
        ;;
esac

echo ""
echo "=========================================="
echo "Next steps:"
echo "  1. Check Supabase Table Editor → 'leads' table"
echo "  2. Deploy API: Follow GITHUB_DEPLOY.md"
echo "  3. Set up GitHub Actions for automation"
echo "=========================================="
