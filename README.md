# 🎓 South London College — AI Chatbot

An AI-powered admissions chatbot for South London College that:

- Answers learner questions using data from your `courses.xlsx` Excel file
- Redirects pricing questions to the course webpage
- Integrates with **Brevo Conversations** via webhook
- **Auto-replies after 3 minutes** if no human agent has responded
- Built with Python, FastAPI, and OpenAI

---

## 📁 Project Structure

```
college-chatbot/
├── main.py                  # FastAPI app + webhook endpoint
├── bot.py                   # AI reply logic (OpenAI)
├── excel_loader.py          # Reads and searches courses.xlsx
├── brevo_handler.py         # Brevo API calls (send/fetch messages)
├── scheduler.py             # 3-minute auto-reply timer logic
├── create_sample_excel.py   # Run once to generate a sample courses.xlsx
├── courses.xlsx             # Your course data (create with script below)
├── requirements.txt
├── Procfile                 # For Railway / Render deployment
├── railway.toml             # Railway-specific config
├── .env.example             # Copy to .env and fill in your keys
└── .gitignore
```

---

## ⚙️ Setup Instructions

### 1. Clone / Download the Project

```bash
cd college-chatbot
```

### 2. Create a Virtual Environment

```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Where to find it |
|---|---|
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| `BREVO_API_KEY` | Brevo → Settings → API Keys |
| `BREVO_AGENT_ID` | Brevo → Conversations → Agents → Your bot agent |

### 5. Generate Sample Course Data

```bash
python create_sample_excel.py
```

This creates `courses.xlsx` with 10 sample courses.
**Replace the sample data with your real courses** — keep the same column headers.

### 6. Run Locally

```bash
python main.py
```

The API will be running at: `http://localhost:8000`

Test the bot directly:
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What IT courses do you offer?"}'
```

---

## 📊 Excel File Format

Your `courses.xlsx` should have these columns (case-insensitive, spaces OK):

| Column | Required | Description |
|---|---|---|
| `course_name` | ✅ | Full name of the course |
| `description` | ✅ | What the course covers |
| `level` | Recommended | e.g. Level 2, Level 3, HNC |
| `duration` | Recommended | e.g. 1 Year Full-Time |
| `start_date` | Recommended | e.g. September 2025 |
| `mode` | Optional | On-Campus / Online / Blended |
| `department` | Optional | e.g. Business, Health, Digital |
| `price` | Optional | Numeric value (bot will never state this — redirects to URL) |
| `url` | ✅ | Direct link to the course page on your website |

---

## 🔗 Brevo Integration Setup

### Step 1: Create a Bot Agent in Brevo
1. Go to **Brevo → Conversations → Agents**
2. Create a new agent, name it something like `College Bot`
3. Copy the **Agent ID** and add it to your `.env` as `BREVO_AGENT_ID`

### Step 2: Configure the Webhook
1. Go to **Brevo → Settings → Integrations → Webhooks**
2. Click **Add new webhook**
3. Set the URL to: `https://your-deployed-app.railway.app/webhook/brevo`
4. Select these events:
   - ✅ **New message** (visitor sent a message)
   - ✅ **Agent message sent** (human agent replied)
5. Save the webhook

### Step 3: Test It
- Open a test conversation in Brevo Chat
- Send a message
- Wait 3 minutes without replying as an agent
- The bot should auto-reply ✅

---

## 🚀 Deploying to Railway (Recommended)

Railway is the recommended host — always-on, simple deploys, no cold starts.

### Option A: Deploy via GitHub (Recommended)
1. Push this project to a GitHub repository
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub**
3. Select your repo
4. Railway auto-detects the `Procfile` and deploys

### Option B: Deploy via CLI
```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

### Set Environment Variables on Railway
In your Railway project dashboard:
- Go to **Variables**
- Add `OPENAI_API_KEY`, `BREVO_API_KEY`, `BREVO_AGENT_ID`

### Get Your Public URL
Railway gives you a URL like `https://your-app.railway.app`
Use this as your Brevo webhook URL.

---

## 🌐 Other Hosting Options

| Platform | Free Tier | Notes |
|---|---|---|
| **Railway** ⭐ | $5 credit/month | Best overall — no sleep, easy setup |
| **Render** | Yes (sleeps after 15min idle) | Good free tier, may have cold starts |
| **Fly.io** | Generous free tier | Fast global edge, good for always-on |
| **Google Cloud Run** | 2M req/month free | Scales to zero, pay per use |
| **Hugging Face Spaces** | Free | Cold starts, limited for webhooks |

---

## 🔄 How the 3-Minute Auto-Reply Works

```
Visitor sends message
        ↓
Brevo fires webhook → /webhook/brevo
        ↓
Bot timer starts (3 minutes)
        ↓
   ┌────┴────┐
   │         │
Agent     No agent
replies   replies
within    within
3 mins    3 mins
   │         │
Timer     Bot reads
cancelled  conversation
          history & replies
```

The timer resets if the visitor sends another message before the 3 minutes are up.

---

## 🧪 Testing Without Brevo

Use the `/chat` endpoint to test the bot's responses directly:

```bash
# Test a course enquiry
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Do you have any evening accounting courses?",
    "history": []
  }'

# Test a pricing question
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How much does the hairdressing course cost?",
    "history": []
  }'

# Test with conversation history
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Which one is shorter?",
    "history": [
      {"role": "user", "content": "What IT courses do you offer?"},
      {"role": "assistant", "content": "We have a T-Level in Digital..."}
    ]
  }'
```

---

## 🛠️ API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/webhook/brevo` | Receives Brevo chat events |
| `POST` | `/chat` | Direct chat (for testing) |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Auto-generated Swagger UI |

---

## 🔧 Customisation

**Change the bot name or personality:**
Edit the `SYSTEM_PROMPT_TEMPLATE` in `bot.py`

**Change the 3-minute delay:**
Set `BOT_REPLY_DELAY_SECONDS=60` in `.env` (or any number of seconds)

**Use a different AI model:**
Set `OPENAI_MODEL=gpt-4o` in `.env` for higher quality responses

**Add more course columns:**
Just add them to your Excel file — the bot automatically includes all columns in its context

---

## ❓ Troubleshooting

**Bot isn't replying:**
- Check `BREVO_AGENT_ID` is correct in `.env`
- Check your webhook URL is publicly accessible (not localhost)
- Check Brevo webhook is configured for the right events

**Excel not loading:**
- Make sure `courses.xlsx` is in the same directory as `main.py`
- Ensure column headers are present in row 1
- Run `python create_sample_excel.py` to generate a valid template

**OpenAI errors:**
- Verify `OPENAI_API_KEY` is valid and has credit
- Check the model name in `OPENAI_MODEL` is correct

---

## 📞 Support

For questions about this chatbot, contact your development team or raise an issue in the repository.
