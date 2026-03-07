import os
import pandas as pd
import re

# ==========================================
# CONFIG
# ==========================================

BASE_PATH = "covermore_reference_complete"
WEEKLY_PATH = os.path.join(BASE_PATH, "weekly_data")
INVOICE_FILE = os.path.join(BASE_PATH, "invoices/invoices_covermore.csv")
BANK_FILE = os.path.join(BASE_PATH, "bank_statements/bank_statement.csv")
OUTPUT_FILE = os.path.join(BASE_PATH, "output/final_matching_output.csv")

DATE_FORMAT = "%d/%m/%Y"

# ==========================================
# LOAD DATA
# ==========================================

print("Loading invoices...")
invoices = pd.read_csv(INVOICE_FILE)
invoices["Invoice_Date"] = pd.to_datetime(invoices["Invoice_Date"], format=DATE_FORMAT)

print("Loading bank transactions...")
bank = pd.read_csv(BANK_FILE)

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def extract_reference(text):
    """
    Extract NZ reference using regex
    """
    text = str(text).upper()
    match = re.search(r'\bNZ[A-Z0-9]+\b', text)
    return match.group(0) if match else None


def build_reference_index():
    """
    Build optimized reference index:
    {
        reference: {
            "Week": folder_name,
            "CompletionDate": date,
            "Total": claim_total
        }
    }
    """

    print("Building reference index...")
    reference_index = {}

    for root, dirs, files in os.walk(WEEKLY_PATH):
        for file in files:
            if file.endswith(".csv"):
                filepath = os.path.join(root, file)
                df = pd.read_csv(filepath)

                if "ReferenceNumber" not in df.columns:
                    continue

                for _, row in df.iterrows():
                    ref = str(row["ReferenceNumber"]).strip().upper()

                    reference_index[ref] = {
                        "Week": os.path.basename(root),
                        "CompletionDate": pd.to_datetime(
                            row["CompletionDate"],
                            format=DATE_FORMAT
                        ),
                        "Total": float(row["Total"])
                    }

    print(f"Loaded {len(reference_index)} references.")
    return reference_index


def get_invoice_week(invoice_date):
    """
    Convert invoice date to week folder format
    """
    iso = invoice_date.isocalendar()
    return f"{iso.year}_week_{iso.week}"


# ==========================================
# BUILD INDEX
# ==========================================

reference_index = build_reference_index()

# ==========================================
# MATCHING LOGIC
# ==========================================

def match_transaction(row):

    text = row["Transaction_Text"]
    reference = extract_reference(text)

    if not reference:
        return "", "No_Reference"

    if reference not in reference_index:
        return "", "Reference_Not_Found"

    claim_data = reference_index[reference]
    claim_week = claim_data["Week"]

    # Match invoice by week
    possible_invoices = invoices[
        invoices["Invoice_Date"].apply(get_invoice_week) == claim_week
    ]

    if len(possible_invoices) == 1:
        return possible_invoices.iloc[0]["Invoice_Number"], "Matched_By_Week"

    elif len(possible_invoices) > 1:
        return possible_invoices.iloc[0]["Invoice_Number"], "Multiple_Invoices_Same_Week"

    return "", "Invoice_Not_Found"


print("Matching transactions...")
results = bank.apply(match_transaction, axis=1)

bank["Matched_Invoice"] = results.apply(lambda x: x[0])
bank["Match_Status"] = results.apply(lambda x: x[1])

# ==========================================
# SAVE OUTPUT
# ==========================================

os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
bank.to_csv(OUTPUT_FILE, index=False)

print("==========================================")
print("Matching complete.")
print(f"Output saved to: {OUTPUT_FILE}")
print("==========================================")