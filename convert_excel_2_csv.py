"""Convert the Online Retail II Excel file (two sheets) into one CSV."""
import pandas as pd

# Change these two paths to match your computer
INPUT_XLSX = r"C:\path\to\online_retail_II.xlsx"
OUTPUT_CSV = r"C:\path\to\online_retail.csv"

sheets = pd.read_excel(INPUT_XLSX, sheet_name=None, dtype=str)  # reads both sheets
df = pd.concat(sheets.values(), ignore_index=True)              # stacks them
df.to_csv(OUTPUT_CSV, index=False)
print(len(df), "rows written")