# run Agent Service

### 1. Setup Virtual Environment

```powershell
# create venv (virtual environment)
python -3.10 -m venv .venv

# active venv
.venv\Scripts\activate
```

### 2. Dependencies

```powershell
pip install -r requirements.txt
```

### 3. Setup Environment Variables (.env)
Dự án cần kết nối tới Supabase và Google AI Studio.
1. Tạo `.env` từ file mẫu: `copy .env.example .env`
2. Mở `.env` và điền các thông tin:
   - `SUPABASE_URL`: URL của Supabase.
   - `SUPABASE_SERVICE_ROLE_KEY`: Key bí mật (service role) để Agent có quyền đọc/ghi.
   - `GOOGLE_API_KEY`: API Key của Google AI Studio.

### 4. Run Server (FastAPI)

```powershell
# Cách 1: Chạy module mặc định
python  -m api.main

# Cách 2: chạy và tự động reload khi sửa code
uvicorn api.main:app --reload --port 8000
```

### 5. Kiểm tra kết quả
- **Health Check:** [http://localhost:8000/api/health](http://localhost:8000/api/health)
- **API Documentation (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Kiểm tra Tools:** [http://localhost:8000/api/tools](http://localhost:8000/api/tools)
