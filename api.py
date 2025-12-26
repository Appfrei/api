from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pathlib import Path
from passlib.context import CryptContext
import json
from fastapi.middleware.cors import CORSMiddleware

# Dateipfade
USERS_FILE = Path("users.json")
CODES_FILE = Path("codes.json")

app = FastAPI()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# CORS für iOS App erlauben
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELS ---
class AuthRequest(BaseModel):
    email: str
    password: str

class ProductRequest(BaseModel):
    email: str
    barcode: str
    quantity: int = 1

class CodeRequest(BaseModel):
    barcode: str
    name: str

# --- HELPERS ---
def load_json(file_path):
    if not file_path.exists(): 
        file_path.write_text("[]")
    try:
        data = json.loads(file_path.read_text())
        return data if isinstance(data, list) else []
    except:
        return []

def save_json(file_path, data):
    file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

# --- CODES VERWALTUNG (Deine Datenbank) ---

@app.post("/codes/add")
def add_global_code(data: CodeRequest):
    """Fügt ein Produkt dauerhaft der Datenbank hinzu."""
    codes = load_json(CODES_FILE)
    # Prüfen ob Barcode schon existiert
    for c in codes:
        if c["barcode"] == data.barcode:
            c["name"] = data.name # Name aktualisieren
            save_json(CODES_FILE, codes)
            return {"message": "Produkt aktualisiert"}
    
    codes.append({"barcode": data.barcode, "name": data.name})
    save_json(CODES_FILE, codes)
    return {"message": "Produkt neu registriert"}

@app.get("/codes/{barcode}")
def get_code_info(barcode: str):
    """Sucht einen Barcode in der lokalen codes.json."""
    codes = load_json(CODES_FILE)
    product = next((c for c in codes if c["barcode"] == barcode), None)
    if not product:
        # Fallback für unbekannte Barcodes
        return {"barcode": barcode, "name": f"Unbekannt ({barcode})"}
    return product

# --- SCAN & BESTAND ---

@app.post("/scan")
def scan_product(data: ProductRequest):
    users = load_json(USERS_FILE)
    codes = load_json(CODES_FILE)
    
    email = data.email.lower().strip()
    user = next((u for u in users if u["email"].lower() == email), None)
    if not user: 
        raise HTTPException(status_code=404, detail="User nicht gefunden")
    
    # Check ob Code bekannt ist
    known_code = next((c for c in codes if c["barcode"] == data.barcode), None)
    product_name = known_code["name"] if known_code else f"Unbekannt ({data.barcode})"
    
    if "products" not in user: 
        user["products"] = []
    
    existing = next((p for p in user["products"] if p["barcode"] == data.barcode), None)
    if existing:
        existing["quantity"] += data.quantity
    else:
        user["products"].append({
            "barcode": data.barcode, 
            "name": product_name, 
            "quantity": data.quantity
        })
    
    save_json(USERS_FILE, users)
    return {"status": "ok", "name": product_name}

# --- PRODUKT OPERATIONEN (Entnehmen/Löschen) ---

@app.post("/products/remove")
def remove_product(data: ProductRequest):
    users = load_json(USERS_FILE)
    user = next((u for u in users if u["email"].lower() == data.email.lower().strip()), None)
    
    if not user:
        raise HTTPException(status_code=404, detail="User nicht gefunden")
    
    if "products" not in user or not user["products"]:
        return {"status": "ok", "message": "Keine Produkte vorhanden"}
    
    for i, p in enumerate(user["products"]):
        if p["barcode"] == data.barcode:
            p["quantity"] -= data.quantity
            if p["quantity"] <= 0: 
                user["products"].pop(i)
            break
    
    save_json(USERS_FILE, users)
    return {"status": "ok", "message": "Produkt entfernt"}

@app.post("/products/delete_all")
def delete_all(data: ProductRequest):
    users = load_json(USERS_FILE)
    user = next((u for u in users if u["email"].lower() == data.email.lower().strip()), None)
    
    if not user:
        raise HTTPException(status_code=404, detail="User nicht gefunden")
    
    if "products" in user:
        user["products"] = [p for p in user["products"] if p["barcode"] != data.barcode]
        save_json(USERS_FILE, users)
    
    return {"status": "ok", "message": "Alle Einheiten gelöscht"}

@app.get("/products/{email}")
def get_products(email: str):
    users = load_json(USERS_FILE)
    user = next((u for u in users if u["email"].lower() == email.lower().strip()), None)
    
    if not user:
        raise HTTPException(status_code=404, detail="User nicht gefunden")
    
    return {"products": user.get("products", [])}

# --- AUTH ---

@app.post("/login")
def login(data: AuthRequest):
    users = load_json(USERS_FILE)
    user = next((u for u in users if u["email"].lower() == data.email.lower().strip()), None)
    if not user or not pwd_context.verify(data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Ungültige Anmeldedaten")
    return {"status": "ok", "email": user["email"]}

@app.post("/register")
def register(data: AuthRequest):
    users = load_json(USERS_FILE)
    email = data.email.lower().strip()
    
    if any(u["email"].lower() == email for u in users):
        raise HTTPException(status_code=400, detail="Email bereits registriert")
    
    users.append({
        "email": email, 
        "password": pwd_context.hash(data.password), 
        "products": []
    })
    
    save_json(USERS_FILE, users)
    return {"status": "ok", "email": email}

# --- HEALTH CHECK ---
@app.get("/")
def root():
    return {"status": "running", "message": "API ist online"}