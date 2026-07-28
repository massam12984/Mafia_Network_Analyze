# 🔫 Mafia Network Analyzer

Analyze criminal networks using graph centrality measures (degree, betweenness, eigenvector).  
Now with **MongoDB-backed Sign Up / Sign In** authentication.

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure MongoDB

**Option A – Local MongoDB**
Make sure MongoDB is running on your machine:
```bash
mongod --dbpath /data/db
```
Set in `.env` (or just leave default):
```
MONGO_URI=mongodb://localhost:27017/
```

**Option B – MongoDB Atlas (cloud)**
```
MONGO_URI=mongodb+srv://<username>:<password>@cluster.mongodb.net/
```

### 3. Set environment variables
```bash
cp .env.example .env
# Edit .env with your MONGO_URI and a SECRET_KEY
```

Or export directly:
```bash
export MONGO_URI="mongodb://localhost:27017/"
export SECRET_KEY="some-random-secret"
```

### 4. Run the app
```bash
python app.py
```
Visit: http://127.0.0.1:5000

---

## Auth Flow

```
/ (root)
  ├── Not logged in → /login  (Sign In / Sign Up)
  └── Logged in    → /analyzer (main page)

/login POST  → verifies credentials against MongoDB users collection
              → sets session → redirects to /analyzer

/logout      → clears session → redirects to /login
```

- Passwords are hashed with **Werkzeug's `generate_password_hash`** (PBKDF2-SHA256)
- MongoDB collection: `mafia_analyzer.users`
- Unique index on both `username` and `email`

---

## CSV Format

Your CSV must have `Source` and `Target` columns:

```
Source,Target
Don_Corleone,Sonny
Don_Corleone,Michael
Michael,Barzini
...
```

Download a sample at `/sample-csv` after logging in.
