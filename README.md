# AI DevOS

## Run the application locally

### 1. Create and activate the virtual environment

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution, run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 2. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Start the API

The FastAPI app is rooted in the backend package, so start it from the backend folder:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 4. Check the app

Open the health endpoint in your browser or use curl:

```powershell
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status": "healthy"}
```

### 5. Run the tests

From the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p "test_*.py"
```
