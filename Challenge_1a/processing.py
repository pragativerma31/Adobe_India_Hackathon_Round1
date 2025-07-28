import os
import json

# Import functions from title_extracter
from title_extracter import (
    title_extract_main
)

# Import functions from header_extracter  
from header_extracter import (
    heading_extracter_main
)


def process_single_pdf(pdf_file_path):
    """
    Process a single PDF file and return the JSON data.
    
    Args:
        pdf_file_path: Path to the PDF file to process
        
    Returns:
        Dictionary containing the JSON data, or None if processing failed
    """
    try:
        # Step 1: Extract title and get its lower y coordinate using title_extract_fitz_data
        print("="*80)
        print(f"STEP 1: EXTRACTING TITLE FROM {pdf_file_path}")
        print("="*80)

        # Extract data from first page only
        title_data, title_lower_y = title_extract_main(pdf_file_path)

        if not title_data:
            print("No text data found on first page")
            title_lower_y = 200  # Default fallback

        # Add buffer below title
        page1_y_threshold = title_lower_y + 10
        
        # Extract data from page 1 to end with y threshold for page 1
        json_data = heading_extracter_main(pdf_file_path, page1_y_threshold, title_data)
        
        # Process the header data through the filtering pipeline
        print("="*80)
        print("Processing completed successfully!")
        print("="*80)
        
        return json_data
        
    except Exception as e:
        print(f"\nError processing PDF {pdf_file_path}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def main_execution():    
    try:
        # Step 1: Extract title and get its lower y coordinate using title_extract_fitz_data
        print("="*80)
        print("STEP 1: EXTRACTING TITLE FROM FIRST PAGE")
        print("="*80)
        pdf_file = "C:\\python\\adobe\\app\\input\\file01.pdf"  # Replace with your PDF file path

        # Extract data from first page only
        title_data , title_lower_y = title_extract_main(pdf_file)

        if not title_data:
            print("No text data found on first page")
            title_lower_y = 200  # Default fallback


        # Add buffer below title
        page1_y_threshold = title_lower_y + 10
        
        # Extract data from page 1 to end with y threshold for page 1
        json_data = heading_extracter_main(pdf_file, page1_y_threshold , title_data)

        
        # Process the header data through the filtering pipeline
        print("="*80)
        print("Processing completed successfully!")
        print("="*80)
        print("Generated JSON data:")
        print(json.dumps(json_data, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"\nError processing PDF: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main_execution()


