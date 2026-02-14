import zipfile
import re
import os

file_path = r"C:\Users\ASUS\Documents\Список селлеров b2b парсер\docs\File\STM_Sellers_Full_Master_v3_contacts_partial (1).xlsx"

try:
    with zipfile.ZipFile(file_path, 'r') as z:
        # sharedStrings.xml contains the text values
        if 'xl/sharedStrings.xml' in z.namelist():
            with z.open('xl/sharedStrings.xml') as f:
                content = f.read().decode('utf-8')
                # Simple regex to find <t> tags
                strings = re.findall(r'<t[^>]*>(.*?)</t>', content)
                print("Found strings (potential headers/data):")
                print(strings[:50])  # Print first 50 unique strings
        else:
            print("No sharedStrings.xml found. Values might be inline.")
            
        # sheet1.xml contains the cell structure
        # We can try to infer structure from the first few rows if needed, 
        # but sharedStrings is usually enough to see the headers.
except Exception as e:
    print(f"Error reading xlsx as zip: {e}")
