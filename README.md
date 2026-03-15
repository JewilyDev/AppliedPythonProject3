# URL Shortener API

## Run

### Local (Python)
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

API base URL: `http://127.0.0.1:8000`  
Swagger UI: `http://127.0.0.1:8000/docs`

### Docker Compose
```bash
docker compose up --build
```

API base URL: `http://127.0.0.1:8000`  
Swagger UI: `http://127.0.0.1:8000/docs`

## Примеры использования

### 1) Register user
```bash
curl -X POST "http://127.0.0.1:8000/auth/register" ^
  -H "Content-Type: application/json" ^
  -d "{\"username\":\"student1\",\"password\":\"12345\"}"
```

### 2) Login (get bearer token)
```bash
curl -X POST "http://127.0.0.1:8000/auth/login" ^
  -H "Content-Type: application/json" ^
  -d "{\"username\":\"student1\",\"password\":\"12345\"}"
```

### 3) Create short link (anonymous)
```bash
curl -X POST "http://127.0.0.1:8000/links/shorten" ^
  -H "Content-Type: application/json" ^
  -d "{\"original_url\":\"https://example.com\"}"
```

### 4) Create short link with custom alias
```bash
curl -X POST "http://127.0.0.1:8000/links/shorten" ^
  -H "Content-Type: application/json" ^
  -d "{\"original_url\":\"https://example.com/very/long/path\",\"custom_alias\":\"my_link\"}"
```

### 5) Create short link with expiration
```bash
curl -X POST "http://127.0.0.1:8000/links/shorten" ^
  -H "Content-Type: application/json" ^
  -d "{\"original_url\":\"https://example.com\",\"expires_at\":\"2030-01-01T12:30:00+00:00\"}"
```

### 6) Open short link (redirect)
```bash
curl -i "http://127.0.0.1:8000/links/my_link"
```

### 7) Get link stats
```bash
curl "http://127.0.0.1:8000/links/my_link/stats"
```

### 8) Update link (owner only)
```bash
curl -X PUT "http://127.0.0.1:8000/links/my_link" ^
  -H "Authorization: Bearer YOUR_TOKEN" ^
  -H "Content-Type: application/json" ^
  -d "{\"new_url\":\"https://newsite.com\"}"
```

### 9) Delete link (owner only)
```bash
curl -X DELETE "http://127.0.0.1:8000/links/my_link" ^
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 10) Search by original URL
```bash
curl "http://127.0.0.1:8000/links/search?original_url=https://example.com"
```
