# Deploying to GitHub

This guide walks you through setting up the Charleston County lead scraper to run automatically on GitHub Actions (free tier).

---

## Overview: What runs where

| Component | Runs on | Purpose |
|-----------|---------|---------|
| **Scrapers** | GitHub Actions (cron) | Pull data from county portals on schedule |
| **Database** | Supabase (cloud) | Store leads, properties, audit logs |
| **API** | Railway / Render / Fly.io | Serve data to your dashboard |
| **Dashboard** | Any static host (Netlify / Vercel / GitHub Pages) | Your front-end |

**Why this architecture?** GitHub Actions gives you free compute for scrapers (2,000 minutes/month = ~1 hour/day). The scrapers write to Supabase, the API reads from Supabase, and the dashboard talks to the API. Everything is stateless and horizontally scalable.

---

## Step-by-step setup

### 1. Create a Supabase project (5 min)

1. Go to https://app.supabase.com → **New Project**
2. Pick a name (e.g. `charleston-leads`) and region (`us-east-1`)
3. Wait for it to provision (~2 min)
4. Go to **SQL Editor** → **New Query** → paste the contents of `db/schema.sql` → **Run**
5. Go to **Settings → API** and copy these three values:
   - **Project URL** → save as `SUPABASE_URL`
   - **Project API Keys → `service_role`** (secret) → save as `SUPABASE_SERVICE_KEY`
   - **Project API Keys → `anon`** (public) → save as `SUPABASE_ANON_KEY`

✅ Your database is ready.

---

### 2. Push code to GitHub (3 min)

```bash
# In your local copy of charleston_backend/
git init
git add .
git commit -m "Initial commit - Charleston County lead scraper"

# Create a new repo on GitHub (github.com/new), then:
git remote add origin https://github.com/YOUR_USERNAME/charleston-leads.git
git branch -M main
git push -u origin main
```

✅ Code is on GitHub.

---

### 3. Configure GitHub Secrets (2 min)

1. Go to your repo on GitHub → **Settings → Secrets and variables → Actions**
2. Click **New repository secret** and add these two:
   - Name: `SUPABASE_URL` → Value: (paste your Project URL from step 1)
   - Name: `SUPABASE_SERVICE_KEY` → Value: (paste your service_role key)

**Why secrets?** GitHub Actions reads these as environment variables, but they're never logged or exposed in the UI.

✅ Secrets configured.

---

### 4. Enable GitHub Actions (1 min)

1. In your repo → **Actions** tab
2. You should see `.github/workflows/scrapers.yml` detected
3. Click **I understand my workflows, go ahead and enable them**

✅ Automation is live. The cron schedule will kick in automatically:
- **Daily 6am ET** — fast scrapers (XLSX, HTML, PDF)
- **Daily 7am ET** — daybook scrapers
- **Sunday 6:30am ET** — heavy scrapers
- **Hourly :15** — enrichment drain

---

### 5. Test it manually (2 min)

Don't wait for cron. Run a job right now:

1. Go to **Actions** tab → **Charleston County Lead Scrapers** workflow
2. Click **Run workflow** dropdown → select `fast` → **Run workflow**
3. Wait ~2-3 minutes, refresh the page
4. Click the workflow run → click the `scrape` job → expand logs

You should see:
```
=== RealPropertyTaxSaleScraper done: {'status': 'success', 'found': 150, 'new': 150, 'updated': 0} ===
```

Now check Supabase:
1. Go to your Supabase project → **Table Editor**
2. Open the `leads` table
3. You should see 150+ rows

✅ Data is flowing.

---

### 6. Deploy the API (10 min)

The scrapers write to Supabase, but the dashboard needs an API to read from it. Deploy the FastAPI service:

#### Option A: Railway (easiest, one command)

```bash
# Install Railway CLI
npm i -g @railway/cli  # or: brew install railway

# Login
railway login

# Deploy
railway init
railway up

# Set secrets
railway variables set SUPABASE_URL=https://your-project.supabase.co
railway variables set SUPABASE_SERVICE_KEY=eyJhbGciOi...

# Your API is live at: https://charleston-leads-production.up.railway.app
```

#### Option B: Render (web UI, no CLI)

1. Go to https://render.com → **New → Web Service**
2. Connect your GitHub repo
3. Settings:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_KEY`
5. **Create Web Service**

#### Option C: Fly.io (needs Dockerfile, already included)

```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Deploy
fly launch
# Say "yes" to deploying now
# Pick a region close to your Supabase (us-east-1)

# Set secrets
fly secrets set SUPABASE_URL=https://your-project.supabase.co
fly secrets set SUPABASE_SERVICE_KEY=eyJhbGciOi...

# Your API is live at: https://charleston-leads.fly.dev
```

✅ API is deployed. Test it:
```bash
curl https://your-api-url.com/api/health
# Should return: {"status":"ok","ts":"2026-04-28T..."}

curl https://your-api-url.com/api/leads?limit=5
# Should return: {"leads":[...], "limit":5, "offset":0}
```

---

### 7. Connect the dashboard (5 min)

Update the HTML dashboard to read from your deployed API instead of browser storage.

Open `charleston_dashboard.html` and find the `loadLeads()` function around line 450. Replace it with:

```javascript
const API_URL = 'https://your-api-url.com';  // ← YOUR deployed API URL

async function loadLeads() {
  try {
    const resp = await fetch(`${API_URL}/api/leads?limit=1000`);
    const data = await resp.json();
    leads = (data.leads || []).map(l => ({
      id: l.id,
      owner: l.owner_raw || l.owner_norm || '',
      address: l.address || '',
      mailing: l.mailing_address || '',
      type: l.lead_type || 'OTH',
      case: l.case_number || '',
      amount: l.amount || null,
      source: l.source || '',
      flags: l.flags || [],
      notes: l.notes || '',
      phone: '',
      score: l.score || 0,
    }));
  } catch (e) {
    console.error('Failed to load leads from API:', e);
    // Fall back to sample data if API is down
    leads = sampleLeads();
  }
}

async function renderKPIs() {
  try {
    const resp = await fetch(`${API_URL}/api/stats`);
    const stats = await resp.json();
    const html = [
      { num: stats.total_leads, label: 'Total Leads' },
      { num: stats.high_score, label: 'Score ≥ 60' },
      { num: stats.pre_foreclosure, label: 'Pre-Foreclosure' },
      { num: stats.tax_delinquent, label: 'Tax Delinquent' },
      { num: stats.probate, label: 'Probate' },
      { num: stats.code_violations, label: 'Code Violations' },
      { num: stats.absentee, label: 'Absentee' },
      { num: stats.out_of_state, label: 'Out of State' },
    ].map(k => `<div class="kpi"><div class="num">${k.num}</div><div class="label">${k.label}</div></div>`).join('');
    document.getElementById('kpis').innerHTML = html;
  } catch (e) {
    console.error('Failed to load stats:', e);
  }
}
```

Now host the dashboard anywhere:
- **Netlify**: Drag `charleston_dashboard.html` into https://app.netlify.com/drop
- **Vercel**: `vercel --prod` (if you have Vercel CLI)
- **GitHub Pages**: Push to a `gh-pages` branch
- **Or just open it locally** — `file:///path/to/charleston_dashboard.html` will work if your API has CORS enabled (it does by default)

✅ Dashboard is live and pulling from the API.

---

## What happens now (automated)

Every day at 6am ET, GitHub Actions will:
1. Spin up an Ubuntu VM
2. Install Python + Playwright
3. Run the fast scrapers (5–7 min runtime)
4. Write new leads to Supabase
5. Shut down the VM

The enrichment job runs hourly and drains the queue (pulls tax-portal data, flags absentee/OOS).

You refresh your dashboard → you see new leads.

**Cost: $0.** GitHub Actions gives you 2,000 free minutes/month. Your total scraping time is ~45 min/week = 180 min/month.

---

## Manual operations

### Trigger a scraper from GitHub UI
1. Go to **Actions** → **Charleston County Lead Scrapers**
2. **Run workflow** → pick `fast` / `daybook` / `heavy` / `enrich` / `all`

### Trigger a scraper from command line (local)
```bash
# One-shot run any scraper
PYTHONPATH=. python -m scrapers.rp_tax_sale

# Or via the scheduler
PYTHONPATH=. python -m scheduler.runner fast
```

### Trigger a scraper via API (from anywhere)
```bash
curl -X POST https://your-api-url.com/api/scrape/rp_tax_sale
curl -X POST https://your-api-url.com/api/enrich
```

### Check scrape history
Supabase → Table Editor → `scrape_runs` table shows every run with status, record counts, errors.

### Debugging a failed workflow
1. **Actions** tab → click the failed run
2. Click the `scrape` job
3. Expand **Run scraper job** step
4. Download logs via **Upload logs on failure** artifact

---

## Adjusting the schedule

Edit `.github/workflows/scrapers.yml`:

```yaml
schedule:
  # Cron is in UTC. ET = UTC-5 (winter) or UTC-4 (summer DST)
  # Daily 6am ET = 10:00 UTC (DST) or 11:00 UTC (winter)
  - cron: '0 10 * * *'  # Change the hour here
```

Cron syntax: `minute hour day month day-of-week`
- `0 10 * * *` = 10:00 UTC every day
- `30 10 * * 0` = 10:30 UTC every Sunday
- `15 * * * *` = :15 past every hour

After editing, commit and push:
```bash
git add .github/workflows/scrapers.yml
git commit -m "Adjust scraper schedule"
git push
```

---

## Monitoring

### GitHub Actions usage
**Settings → Billing → Plans and usage** shows how many Action minutes you've used this month.

### Supabase usage
**Settings → Usage** shows:
- Database size (free tier = 500 MB)
- API requests (free tier = 500K/month)
- Egress bandwidth (free tier = 5 GB)

You're nowhere near the limits — this system uses ~10 MB DB + ~50K requests/month.

---

## Troubleshooting

**"Resource not accessible by integration" in Actions**
→ Go to **Settings → Actions → General → Workflow permissions** → select **Read and write permissions** → Save

**Scraper finds 0 records**
→ The county portal might be down or the HTML changed. Run the scraper locally with `PLAYWRIGHT_HEADLESS=false` in `.env` to watch what it's seeing.

**API returns 500 error**
→ Check your Railway/Render/Fly logs. Likely missing `SUPABASE_SERVICE_KEY` environment variable.

**CORS error in dashboard**
→ Your API's CORS is open by default (`allow_origins=["*"]`). If you locked it down, add your dashboard's domain to the list in `api/main.py`.

**Enrichment queue grows but never drains**
→ The hourly enrichment job runs on GitHub Actions, not your API server. Make sure the Actions workflow is enabled.

---

## Next steps

1. **Add notifications**: GitHub Actions can post to Slack/Discord when a scrape completes. Add a step to `.github/workflows/scrapers.yml` using a webhook.

2. **Add more scrapers**: Drop a new `.py` file in `scrapers/`, register it in `api/main.py`, and add to a job group in `scheduler/runner.py`.

3. **Wire up GHL export**: Add a `/api/export/ghl` endpoint that returns the GHL CSV format, then point your dashboard's export button to `fetch(API_URL + '/api/export/ghl')`.

4. **Set up alerts for failed runs**: GitHub can email you when a workflow fails. Go to **repo → Watch → Custom → Workflows**.

---

## Cost breakdown (all free tiers)

| Service | Free tier | Your usage | Cost |
|---------|-----------|------------|------|
| GitHub Actions | 2,000 min/month | ~180 min/month | $0 |
| Supabase | 500 MB DB + 500K requests | ~10 MB + 50K req | $0 |
| Railway / Render / Fly | 500 hrs/month | ~730 hrs (always-on API) | $0 |
| Netlify (dashboard) | 100 GB bandwidth | <1 GB | $0 |

**Total: $0/month** until you hit ~10K leads in the database or 100K API requests/month, at which point you'll pay Supabase ~$5–10/mo. The rest stays free.
