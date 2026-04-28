# Supabase Setup — Detailed Step-by-Step

This guide shows you **exactly** where to find and where to paste each value.

---

## Step 1: Create the Supabase Project (Web Browser)

1. Open your browser and go to: **https://app.supabase.com**
2. Sign in (or create account with GitHub/Google)
3. Click the **"New Project"** button
4. Fill in:
   - **Name**: `charleston-leads` (or whatever you want)
   - **Database Password**: Create a strong password (e.g. generate one with 1Password/LastPass)
     - ⚠️ **SAVE THIS PASSWORD** — write it down or save in password manager
     - You'll need it later if you want to connect to the database directly
   - **Region**: `East US (North Virginia)` — closest to Charleston
   - **Pricing Plan**: Free
5. Click **"Create new project"**
6. Wait ~2 minutes while it provisions

---

## Step 2: Run the Database Schema (Web Browser)

While still in Supabase:

1. In the left sidebar, click **"SQL Editor"** (looks like a `</>` icon)
2. Click **"New query"** button (top right)
3. **On your computer**: Open the file `charleston_backend/db/schema.sql` in a text editor
4. **Copy ALL the text** from that file (Ctrl+A, Ctrl+C)
5. **Back in Supabase browser**: Paste into the SQL editor
6. Click **"Run"** (or press Ctrl+Enter)
7. You should see: **"Success. No rows returned."**

✅ Your database tables are now created.

---

## Step 3: Get Your API Keys (Web Browser → Local File)

Still in Supabase browser:

1. In the left sidebar, click **"Settings"** (gear icon at bottom)
2. Click **"API"** in the Settings submenu
3. You'll see a page with several values. Here's what to copy:

### **Copy Location 1: Project URL**
- **Find it**: Look for the section labeled **"Project URL"**
- **It looks like**: `https://abcdefghijklmnop.supabase.co`
- **Copy button**: Click the copy icon next to it
- **Paste it WHERE**: In your local file `.env` (on your computer)
  ```bash
  SUPABASE_URL=https://abcdefghijklmnop.supabase.co
  ```

### **Copy Location 2: Service Role Key (SECRET)**
- **Find it**: Scroll down to **"Project API keys"** section
- **Look for**: The row labeled **"`service_role`"** with a tag that says "secret"
- **It looks like**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFi...` (VERY LONG, 400+ characters)
- **Copy button**: Click the copy icon or "Reveal" then copy
- **Paste it WHERE**: In your local file `.env` (on your computer)
  ```bash
  SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSI...
  ```
- ⚠️ **THIS IS A SECRET** — Never commit this to GitHub in plain text
- This key is for your **backend scrapers only** (has full database access)

### **Copy Location 3: Anon Public Key (SAFE FOR BROWSER)**
- **Find it**: Same **"Project API keys"** section
- **Look for**: The row labeled **"`anon`"** with a tag that says "public"
- **It looks like**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFi...` (also long, but different from service_role)
- **Copy button**: Click the copy icon
- **Paste it WHERE**: You don't need this yet, but later you can put it in the HTML dashboard if you want it to talk directly to Supabase instead of going through your API
  - **For now**: Just skip this one. The backend scrapers + API only need the service_role key.

---

## What Your `.env` File Should Look Like

After Step 3, open `charleston_backend/.env` on your computer. It should look like this:

```bash
# Supabase credentials
SUPABASE_URL=https://abcdefghijklmnop.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFiY2RlZmdoaWprbG1ub3AiLCJyb2xlIjoic2VydmljZV9yb2xlIiwiaWF0IjoxNjMwMDAwMDAwLCJleHAiOjE5NDU1NzYwMDB9.FAKE_KEY_EXAMPLE_PASTE_YOUR_REAL_ONE_HERE

# Optional (not needed yet)
# SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Playwright settings
PLAYWRIGHT_HEADLESS=true
```

⚠️ **Replace the fake values** with the real ones you copied from Supabase!

---

## When Setting Up GitHub Actions

After you push your code to GitHub, you'll also need to give GitHub Actions these same values, but you do it a **different way** (not in a file):

1. **Go to**: Your GitHub repo → **Settings** → **Secrets and variables** → **Actions**
2. **Click**: "New repository secret"
3. **Add TWO secrets**:

   **Secret #1**:
   - Name: `SUPABASE_URL`
   - Value: (paste the same Project URL from Step 3)
   
   **Secret #2**:
   - Name: `SUPABASE_SERVICE_KEY`
   - Value: (paste the same service_role key from Step 3)

4. Click "Add secret" for each one

---

## Visual Diagram: Where Everything Goes

```
┌─────────────────────────────────────────────────────┐
│  Supabase Web UI (app.supabase.com)                │
│  ┌───────────────────────────────────────────────┐  │
│  │ Settings → API                                │  │
│  │                                               │  │
│  │ Project URL:                                  │  │
│  │ https://abcdefg.supabase.co      [📋 Copy]   │──┐
│  │                                               │  │
│  │ Project API keys:                             │  │
│  │ service_role (secret)                         │  │
│  │ eyJhbGciOiJIUzI1NiIsInR...      [📋 Copy]   │──┼─┐
│  │                                               │  │ │
│  │ anon (public)                                 │  │ │
│  │ eyJhbGciOiJIUzI1NiIsInR...      [📋 Copy]   │──┼─┼─┐
│  └───────────────────────────────────────────────┘  │ │ │
└─────────────────────────────────────────────────────┘ │ │ │
                                                        │ │ │
    PASTE ↓                                             │ │ │
                                                        │ │ │
┌─────────────────────────────────────────────────────┐ │ │ │
│  Your Computer: charleston_backend/.env             │ │ │ │
│  ┌───────────────────────────────────────────────┐  │ │ │ │
│  │ SUPABASE_URL=https://abcdefg.supabase.co      │←─┘ │ │
│  │ SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIs... │←───┘ │
│  │ # SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIs... │←─────┘
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                                                        
    ALSO PASTE ↓ (for GitHub Actions)
                                                        
┌─────────────────────────────────────────────────────┐
│  GitHub: Your Repo → Settings → Secrets            │
│  ┌───────────────────────────────────────────────┐  │
│  │ Secret: SUPABASE_URL                          │←─┐ (same value)
│  │ Value: https://abcdefg.supabase.co            │  │
│  │                                               │  │
│  │ Secret: SUPABASE_SERVICE_KEY                  │←─┐ (same value)
│  │ Value: eyJhbGciOiJIUzI1NiIs...               │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## Why Two Places?

- **Local `.env` file**: So you can run scrapers on your laptop for testing
- **GitHub Secrets**: So GitHub Actions can run scrapers in the cloud on schedule

Both need the same values — you're just pasting them in two different places.

---

## Common Mistakes

❌ **"I pasted the anon key instead of service_role"**  
→ Scrapers will fail with "permission denied" errors. Use the **service_role** key (the one labeled "secret").

❌ **"I committed .env to GitHub"**  
→ That's why `.gitignore` blocks it. If you accidentally pushed it, immediately rotate your keys in Supabase (Settings → API → "Roll service_role key").

❌ **"The key has a newline in the middle"**  
→ Keys are long — make sure you copied the whole thing as one line with no line breaks.

❌ **"I saved the database password but don't know where to use it"**  
→ You only need it if you want to connect directly via `psql` or a database GUI. The scrapers don't use it — they use the service_role key.

---

## Test It Worked

After setting up `.env`:

```bash
cd charleston_backend
./setup.sh
```

If it runs without errors and the test scraper completes, your credentials are working. ✅
