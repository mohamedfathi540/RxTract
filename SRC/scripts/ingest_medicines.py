import os
import sys
import csv
import re
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure we can import DB models
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Models.DB_Schemes.minirag.Schemes.Medicine import Medicine

# Fetch Connection String
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5436/minirag")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def extract_active_ingredient(text: str) -> str:
    """
    Attempt to isolate the active ingredient from a bundled product description/name.
    """
    if not text:
        return "Unknown"
        
    # 1. Look for explicit "with <ingredient>"
    with_match = re.search(r'\bwith\s+([A-Za-z0-9, &]+?)(?:\s+for\s+|\s*$|[.!?])', text, re.IGNORECASE)
    if with_match:
        return with_match.group(1).strip()
        
    # 2. Look for ingredients in parentheses e.g. "DrugName (Active Ingredient) 10mg"
    paren_match = re.search(r'\(([^)]+)\)', text)
    if paren_match:
        content = paren_match.group(1).strip()
        # Ensure it's not a generic word like "tablet" or "adults"
        if not re.match(r'^\d+\s*(mg|gm|ml|tablet|capsule|pill|sachet)$', content, re.IGNORECASE):
            return content

    # 3. Look for "contains <ingredient>"
    contains_match = re.search(r'\bcontains\s+([A-Za-z0-9, &]+?)(?:\s+for\s+|\s*$|[.!?])', text, re.IGNORECASE)
    if contains_match:
        return contains_match.group(1).strip()

    return "Unknown"

def clean_trade_name(text: str) -> str:
    # Remove dosage and anything in parens to get the pure brand name
    return re.sub(r'\(.*?\)', '', text).strip()

def ingest_file(session, file_path: str):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    print(f"Ingesting {file_path} ...")
    count = 0
    with open(file_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        
        for row in reader:
            # Determine mapping based on available columns
            if "Drugname" in headers:
                raw_name = row.get("Drugname", "")
                trade_name = clean_trade_name(raw_name)
                # Form, Company, Category are available
                form = row.get("Form", "")
                pharm_class = row.get("Category", "")
                
                try:
                    price = float(row.get("Price", "0").replace(",", ""))
                except ValueError:
                    price = 0.0

            elif "name" in headers:
                raw_name = row.get("name", "")
                trade_name = clean_trade_name(raw_name)
                form = row.get("packaging", "")
                pharm_class = ""
                
                try:
                    price = float(row.get("price", "0").replace(",", ""))
                except ValueError:
                    price = 0.0
            else:
                trade_name = row.get("Trade Name", row.get("name", ""))
                raw_name = trade_name
                form = ""
                pharm_class = ""
                price = 0.0
                
            if not trade_name:
                continue
                
            active_ingredient = extract_active_ingredient(raw_name)
            
            med = Medicine(
                trade_name=trade_name,
                active_ingredient=active_ingredient,
                pharmacological_class=pharm_class,
                price=price,
                dosage_form=form,
                raw_description=raw_name
            )
            session.add(med)
            
            count += 1
            if count % 10000 == 0:
                session.commit()
                print(f"  Inserted {count} rows...")
                
    session.commit()
    print(f"Finished. Total inserted from file: {count}")

def main():
    db = SessionLocal()
    try:
        # Clear existing data so we don't duplicate on re-run
        db.query(Medicine).delete()
        db.commit()
        
        base_dir = "/root/RxTract/SRC/Assets/Files/1"
        files_to_ingest = [
            "medicines_data_updated.csv",
            "Pharmacy_Products.csv",
            "Pharmacy_Products (1).csv"
        ]
        
        for fname in files_to_ingest:
            fpath = os.path.join(base_dir, fname)
            ingest_file(db, fpath)
            
    except Exception as e:
        print(f"Error during ingestion: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()
