import json
from pathlib import Path

# Import the processing function
from processing import process_single_pdf

def process_pdfs():
    # Get input and output directories
    input_dir = Path("app/input")
    output_dir = Path("app/output")
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Get all PDF files
    pdf_files = list(input_dir.glob("*.pdf"))
    
    if not pdf_files:
        print("No PDF files found in the input directory.")
        return
    
    print(f"Found {len(pdf_files)} PDF files to process.")
    
    successful_count = 0
    failed_count = 0
    
    for pdf_file in pdf_files:
        print(f"\n{'='*80}")
        print(f"PROCESSING: {pdf_file.name}")
        print(f"{'='*80}")
        
        # Process the PDF and get JSON data
        json_data = process_single_pdf(str(pdf_file))
        
        if json_data is not None:
            # Create output JSON file
            output_file = output_dir / f"{pdf_file.stem}.json"
            
            try:
                with open(output_file, "w", encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2, ensure_ascii=False)
                
                print(f"✅ Successfully processed {pdf_file.name} -> {output_file.name}")
                successful_count += 1
                
            except Exception as e:
                print(f"❌ Error saving JSON for {pdf_file.name}: {str(e)}")
                failed_count += 1
        else:
            print(f"❌ Failed to process {pdf_file.name}")
            failed_count += 1
    
    print(f"\n{'='*80}")
    print(f"PROCESSING SUMMARY")
    print(f"{'='*80}")
    print(f"Total PDFs: {len(pdf_files)}")
    print(f"Successful: {successful_count}")
    print(f"Failed: {failed_count}")

if __name__ == "__main__":
    print("Starting processing pdfs")
    process_pdfs() 
    print("Completed processing pdfs")