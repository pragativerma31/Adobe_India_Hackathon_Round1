import fitz  # PyMuPDF
from collections import defaultdict

def truncate_middle(text, max_len=40):
    if len(text) <= max_len:
        return text
    keep = max_len // 2 - 2
    return f"{text[:keep]}...{text[-keep:]}"


def pretty_print_metadata(data):
    from tabulate import tabulate

    table_data = []
    for item in data:
        table_data.append([
            truncate_middle(item['text']),
            '✔' if item['bold'] else '❌',
            round(item['size'], 2),
            round(item['x0'], 2),
            round(item['y0'], 2),
            round(item['x1'], 2),
            round(item['y1'], 2),
            '✔' if item['centered'] else '❌'
        ])

    headers = ['Text', 'Bold', 'Size', 'x0', 'y0', 'x1', 'y1', 'Centered']
    print(tabulate(table_data, headers=headers, tablefmt="grid"))


def extract_fitz_data(pdf_path):
    """Extract text, font, bbox and centered info using pymupdf."""
    doc = fitz.open(pdf_path)
    page = doc[0]  # first page

    page_width = page.rect.width
    blocks = page.get_text("dict")["blocks"]

    results = []

    for block in blocks:
        if block['type'] != 0:  # skip non-text blocks
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                x0, y0, x1, y1 = span["bbox"]
                text = span["text"]
                font = span.get("font", "")
                size = span.get("size", 0.0)
                centered = abs((x0 + x1)/2 - page_width/2) < 10  # margin threshold

                # Determine if font is bold based on font name
                bold = 'Bold' in font or 'bold' in font.lower()

                results.append({
                    "text": text,
                    "font": font,
                    "bold": bold,
                    "size": size,
                    "x0": x0,
                    "x1": x1,
                    "y0": y0,
                    "y1": y1,
                    "centered": centered
                })
    return results


def group_spans_by_line(data, y_threshold=2.0):
    """
    Group text spans that are on the same line (similar y0 and y1 values).
    """
    grouped_lines = defaultdict(list)
    
    for item in data:
        # Create a key based on rounded y0 and y1 values
        y0_key = round(item['y0'] / y_threshold) * y_threshold
        y1_key = round(item['y1'] / y_threshold) * y_threshold
        line_key = (y0_key, y1_key)
        
        grouped_lines[line_key].append(item)
    
    # Sort each line by x0 position and merge text
    result = []
    for line_key, spans in grouped_lines.items():
        spans.sort(key=lambda x: x['x0'])  # Sort left to right
        
        # Merge spans on the same line
        merged_text = ' '.join(span['text'].strip() for span in spans if span['text'].strip())
        
        if merged_text:  # Only include non-empty lines
            result.append({
                'text': merged_text,
                'y0': spans[0]['y0'],
                'y1': spans[0]['y1'],
                'x0': spans[0]['x0'],
                'x1': spans[-1]['x1'],
                'font': spans[0]['font'],
                'size': spans[0]['size'],
                'bold': any(span['bold'] for span in spans),
                'centered': spans[0]['centered'],
                'span_count': len(spans)
            })
    
    # Sort by y position (top to bottom)
    result.sort(key=lambda x: x['y0'])
    return result


def is_meaningful_title(text):
    """
    Check if text is a meaningful title by filtering out:
    - Very short text (< 3 characters)
    - Text with only symbols/punctuation
    - Text that doesn't contain letters
    """
    text = text.strip()
    
    # Must have at least 3 characters
    if len(text) < 3:
        return False
    
    # Must contain at least one letter
    if not any(c.isalpha() for c in text):
        return False
    
    # Must have at least 2 words for a good title (optional)
    words = text.split()
    if len(words) < 2 and len(text) < 10:  # Single word must be at least 10 chars
        return False
    
    return True


def is_non_title_text(text):
    """
    Check if text should not be combined with other text to form a title.
    This includes URLs, emails, phone numbers, and other non-title elements.
    """
    import re
    
    text = text.strip().upper()
    
    # Check for URLs and web-related patterns
    url_patterns = [
        r'WWW\.',                    # Starts with WWW.
        r'HTTP[S]?://',             # HTTP or HTTPS URLs
        r'\.(COM|ORG|NET|EDU|GOV)', # Common domain extensions
        r'@.*\.(COM|ORG|NET)',      # Email patterns
    ]
    
    # Check for phone number patterns
    phone_patterns = [
        r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',  # Phone numbers like 123-456-7890
        r'\(\d{3}\)\s?\d{3}[-.\s]?\d{4}',  # Phone numbers like (123) 456-7890
    ]
    
    # Check for other non-title patterns
    other_patterns = [
        r'^[A-Z0-9\-\.]+\.(COM|ORG|NET|EDU|GOV)$',  # Domain-like text
        r'^\d+\s*(ST|ND|RD|TH)?\s+(STREET|ST|AVENUE|AVE|ROAD|RD|BLVD)',  # Address patterns
        r'[A-Z]{2,}\s+\d{5}',       # State and ZIP code patterns
    ]
    
    all_patterns = url_patterns + phone_patterns + other_patterns
    
    # Check if text matches any non-title pattern
    for pattern in all_patterns:
        if re.search(pattern, text):
            return True
    
    return False


def are_whole_texts_single_title(text1, text2, max_vertical_distance=50, alignment_threshold=100):
    """
    Determine if two whole texts belong to a single logical title by checking:
    1. Vertical distance between the whole texts
    2. Horizontal alignment/centering
    3. Neither text is a non-title element (URL, email, etc.)
    """
    # First check if either text is a non-title element that shouldn't be combined
    if is_non_title_text(text1['text']) or is_non_title_text(text2['text']):
        return False, f"One or both texts are non-title elements: '{text1['text']}' / '{text2['text']}'"
    
    # Calculate vertical distance between the whole texts
    # Use the bottom of text1 and top of text2 for more accurate distance
    vertical_distance = abs(text2['y0'] - text1['y1'])
    
    # Check if they're close enough vertically
    if vertical_distance > max_vertical_distance:
        return False, f"Too far apart vertically: {vertical_distance:.1f} > {max_vertical_distance}"
    
    # Check horizontal alignment
    # Calculate the center of each whole text
    text1_center = (text1['x0'] + text1['x1']) / 2
    text2_center = (text2['x0'] + text2['x1']) / 2
    
    # Check if they're horizontally aligned
    horizontal_distance = abs(text1_center - text2_center)
    
    # Check if both texts are centered on the page
    page_center = 306  # 612/2 for standard letter size
    text1_from_center = abs(text1_center - page_center)
    text2_from_center = abs(text2_center - page_center)
    
    # Criteria for being a single title:
    # 1. Texts are close vertically (already checked)
    # 2. Texts are aligned with each other OR both are centered
    # 3. Neither text is a non-title element (already checked)
    is_aligned = horizontal_distance < alignment_threshold
    both_centered = text1_from_center < 100 and text2_from_center < 100
    
    if is_aligned or both_centered:
        return True, f"Whole texts form single title - vertical_dist: {vertical_distance:.1f}, horizontal_align: {horizontal_distance:.1f}, both_centered: {both_centered}"
    else:
        return False, f"Not aligned - horizontal_dist: {horizontal_distance:.1f}, text1_center: {text1_center:.1f}, text2_center: {text2_center:.1f}"


def are_lines_single_title(line1, line2, max_vertical_distance=30, alignment_threshold=50):
    """
    Determine if two lines belong to a single logical title by checking:
    1. Vertical distance between lines
    2. Horizontal alignment/centering
    """
    # Calculate vertical distance between the lines
    vertical_distance = abs(line1['y0'] - line2['y0'])
    
    # Check if they're close enough vertically
    if vertical_distance > max_vertical_distance:
        return False, f"Too far apart vertically: {vertical_distance:.1f} > {max_vertical_distance}"
    
    # Check horizontal alignment
    # Calculate the center of each line
    line1_center = (line1['x0'] + line1['x1']) / 2
    line2_center = (line2['x0'] + line2['x1']) / 2
    
    # Check if they're horizontally aligned
    horizontal_distance = abs(line1_center - line2_center)
    
    # Check if both lines are centered on the page
    page_center = 306  # 612/2 for standard letter size
    line1_from_center = abs(line1_center - page_center)
    line2_from_center = abs(line2_center - page_center)
    
    # Criteria for being a single title:
    # 1. Lines are close vertically (already checked)
    # 2. Lines are aligned with each other OR both are centered
    is_aligned = horizontal_distance < alignment_threshold
    both_centered = line1_from_center < 50 and line2_from_center < 50
    
    if is_aligned or both_centered:
        return True, f"Lines form single title - vertical_dist: {vertical_distance:.1f}, horizontal_align: {horizontal_distance:.1f}, centered: {both_centered}"
    else:
        return False, f"Not aligned - horizontal_dist: {horizontal_distance:.1f}, line1_center: {line1_center:.1f}, line2_center: {line2_center:.1f}"


def is_special_character_text(text):
    """
    Check if text contains only meaningless permutations of special characters.
    These are typically decorative elements like dashes, underscores, asterisks, etc.
    """
    import re
    
    text = text.strip()
    if not text:
        return True
    
    # Define patterns for meaningless special character sequences
    special_char_patterns = [
        r'^[-_=*+~`^|\\/<>]{3,}$',  # Sequences of dashes, underscores, equals, asterisks, etc.
        r'^[•·▪▫◦‣⁃]{3,}$',        # Bullet points and similar symbols
        r'^[─━┄┅┈┉┊┋]{3,}$',       # Various line drawing characters
        r'^[.]{3,}$',               # Multiple dots (ellipsis-like)
        r'^[,]{3,}$',               # Multiple commas
        r'^[;]{3,}$',               # Multiple semicolons
        r'^[:]{3,}$',               # Multiple colons
        r'^[!]{3,}$',               # Multiple exclamation marks
        r'^[?]{3,}$',               # Multiple question marks
        r'^[\s]*[-_=*+~`^|\\/<>•·▪▫◦‣⁃─━┄┅┈┉┊┋.,:;!?]+[\s]*$',  # Mixed special chars with optional whitespace
    ]
    
    # Check if the text matches any special character pattern
    for pattern in special_char_patterns:
        if re.match(pattern, text):
            return True
    
    return False


def group_texts_by_font_size(data, sort_by_y=True):
    
    grouped = defaultdict(list)

    for item in data:
        size_key = round(item['size'], 1)
        grouped[size_key].append(item)

    result = {}
    for size, items in grouped.items():
        if sort_by_y:
            items.sort(key=lambda x: (x['y0'], x['x0']))

        full_text = ' '.join(x['text'] for x in items if x['text'].strip()).strip()

        # Filter out special character sequences and texts with <= 20 words
        if (len(full_text.split()) <= 20 and 
            not is_special_character_text(full_text)):
            result[size] = full_text

    return result





# Example usage
# pdf_file = "C:\\python\\adobe\\app\\input\\E0CCG5S239.pdf"
def title_extract_main(pdf_file):
    data = extract_fitz_data(pdf_file)

    # Now use `data` everywhere
    pretty_print_metadata(data)

    # Step 1: First group spans by line position (same y0 and y1 values)
    print("\n\n=== STEP 1: GROUP SPANS BY LINE POSITION ===")
    grouped_lines = group_spans_by_line(data)
    print(f"Total grouped lines: {len(grouped_lines)}")

    # Display some line grouping examples
    print("\nFirst 5 grouped lines:")
    for i, line in enumerate(grouped_lines[:5]):
        print(f"  Line {i+1}: '{line['text']}' (Size: {line['size']:.1f}pt, Y: {line['y0']:.1f}, Spans: {line['span_count']})")

    # Step 2: Then group the lines by font size
    print("\n\n=== STEP 2: GROUP LINES BY FONT SIZE ===")
    grouped_texts = group_texts_by_font_size(grouped_lines)

    # Print grouped text
    print("\nGrouped Texts by Font Size:\n")
    for size in sorted(grouped_texts.keys(), reverse=True):  # largest font first
        print(f"[Font Size: {size} pt]")
        print(grouped_texts[size])
        print("-" * 80)

    # Step 3: Get top 2 whole texts from 2 biggest font sizes
    print("\n\n=== STEP 3: EXTRACT TOP 2 WHOLE TEXTS FROM 2 BIGGEST FONT SIZES ===")
    font_sizes = sorted(grouped_texts.keys(), reverse=True)

    if len(font_sizes) >= 2:
        top_2_font_sizes = font_sizes[:2]
        print(f"Top 2 font sizes: {top_2_font_sizes}")
        
        # Extract the whole text for each of the top 2 font sizes
        top_2_texts = []
        for i, font_size in enumerate(top_2_font_sizes):
            whole_text = grouped_texts[font_size]
            
            # Find all lines that contribute to this font size and calculate combined bounding box
            contributing_lines = [line for line in grouped_lines if round(line['size'], 1) == font_size]
            
            if contributing_lines:
                # Calculate the bounding box that encompasses all contributing lines
                min_x0 = min(line['x0'] for line in contributing_lines)
                max_x1 = max(line['x1'] for line in contributing_lines)
                min_y0 = min(line['y0'] for line in contributing_lines)
                max_y1 = max(line['y1'] for line in contributing_lines)
                
                # Get other properties from the first line (assuming consistent within font size)
                first_line = contributing_lines[0]
                
                top_2_texts.append({
                    'font_size': font_size,
                    'text': whole_text,
                    'rank': i + 1,
                    'x0': min_x0,
                    'x1': max_x1,
                    'y0': min_y0,
                    'y1': max_y1,
                    'font': first_line['font'],
                    'bold': any(line['bold'] for line in contributing_lines),
                    'centered': first_line['centered'],
                    'contributing_lines': len(contributing_lines)
                })
                
                print(f"Rank {i+1}: Font Size {font_size}pt -> '{whole_text}'")
                print(f"  Bounding box: x0={min_x0:.1f}, y0={min_y0:.1f}, x1={max_x1:.1f}, y1={max_y1:.1f}")
                print(f"  Contributing lines: {len(contributing_lines)}")
            else:
                # Fallback if no contributing lines found
                top_2_texts.append({
                    'font_size': font_size,
                    'text': whole_text,
                    'rank': i + 1,
                    'x0': 0,
                    'x1': 0,
                    'y0': 0,
                    'y1': 0,
                    'font': '',
                    'bold': False,
                    'centered': False,
                    'contributing_lines': 0
                })
                print(f"Rank {i+1}: Font Size {font_size}pt -> '{whole_text}' (No bounding box data)")
        
        print(f"\nExtracted {len(top_2_texts)} whole texts from top 2 font sizes")
        
    elif len(font_sizes) == 1:
        font_size = font_sizes[0]
        whole_text = grouped_texts[font_size]
        
        # Find all lines that contribute to this font size and calculate combined bounding box
        contributing_lines = [line for line in grouped_lines if round(line['size'], 1) == font_size]
        
        if contributing_lines:
            # Calculate the bounding box that encompasses all contributing lines
            min_x0 = min(line['x0'] for line in contributing_lines)
            max_x1 = max(line['x1'] for line in contributing_lines)
            min_y0 = min(line['y0'] for line in contributing_lines)
            max_y1 = max(line['y1'] for line in contributing_lines)
            
            # Get other properties from the first line
            first_line = contributing_lines[0]
            
            top_2_texts = [{
                'font_size': font_size,
                'text': whole_text,
                'rank': 1,
                'x0': min_x0,
                'x1': max_x1,
                'y0': min_y0,
                'y1': max_y1,
                'font': first_line['font'],
                'bold': any(line['bold'] for line in contributing_lines),
                'centered': first_line['centered'],
                'contributing_lines': len(contributing_lines)
            }]
            
            print(f"Only 1 font size found: {font_size}pt -> '{whole_text}'")
            print(f"  Bounding box: x0={min_x0:.1f}, y0={min_y0:.1f}, x1={max_x1:.1f}, y1={max_y1:.1f}")
            print(f"  Contributing lines: {len(contributing_lines)}")
        else:
            top_2_texts = [{
                'font_size': font_size,
                'text': whole_text,
                'rank': 1,
                'x0': 0,
                'x1': 0,
                'y0': 0,
                'y1': 0,
                'font': '',
                'bold': False,
                'centered': False,
                'contributing_lines': 0
            }]
            print(f"Only 1 font size found: {font_size}pt -> '{whole_text}' (No bounding box data)")
    else:
        top_2_texts = []
        print("No font sizes found")

    # Analyze title extraction
    print("\n\n=== TITLE ANALYSIS ===")
    page_width = 612  # Standard letter size
    page_height = 792

    # Filter for potential titles (top 2 font sizes)
    if len(top_2_texts) >= 2:
        print(f"Analyzing top 2 whole texts:")
        print(f"  Text 1 (Rank 1): '{top_2_texts[0]['text']}' (Size: {top_2_texts[0]['font_size']:.1f}pt)")
        print(f"    Bounding box: x0={top_2_texts[0]['x0']:.1f}, y0={top_2_texts[0]['y0']:.1f}, x1={top_2_texts[0]['x1']:.1f}, y1={top_2_texts[0]['y1']:.1f}")
        print(f"  Text 2 (Rank 2): '{top_2_texts[1]['text']}' (Size: {top_2_texts[1]['font_size']:.1f}pt)")
        print(f"    Bounding box: x0={top_2_texts[1]['x0']:.1f}, y0={top_2_texts[1]['y0']:.1f}, x1={top_2_texts[1]['x1']:.1f}, y1={top_2_texts[1]['y1']:.1f}")
        
        # Title selection logic: Check if the two whole texts can form a single title
        text1 = top_2_texts[0]
        text2 = top_2_texts[1]
        
        can_combine, reason = are_whole_texts_single_title(text1, text2)
        print(f"\nTitle combination analysis:")
        print(f"Whole Text 1: '{text1['text']}' (Size: {text1['font_size']:.1f}pt)")
        print(f"Whole Text 2: '{text2['text']}' (Size: {text2['font_size']:.1f}pt)")
        print(f"Can combine: {can_combine}")
        print(f"Reason: {reason}")
        
        if can_combine:
            combined_title = f"{text1['text']} {text2['text']}"
            # Use the lower y coordinate of the second text (bottom-most)
            title_lower_y = max(text1['y1'], text2['y1'])
            print(f"\nFinal title: '{combined_title}' (Combined from top 2 whole texts)")
            print(f"Title lower y coordinate: {title_lower_y:.1f}")
            selected_title = combined_title
            selected_lower_y = title_lower_y
        else:
            # Select the most meaningful title from top 2 whole texts
            meaningful_texts = [t for t in top_2_texts if is_meaningful_title(t['text'])]
            
            if meaningful_texts:
                selected_title = meaningful_texts[0]['text']
                selected_lower_y = meaningful_texts[0]['y1']
                print(f"\nFinal title: '{selected_title}' (Most meaningful from top 2 whole texts)")
                print(f"Title lower y coordinate: {selected_lower_y:.1f}")
            else:
                # Fall back to largest font size whole text
                selected_title = top_2_texts[0]['text']
                selected_lower_y = top_2_texts[0]['y1']
                print(f"\nFinal title: '{selected_title}' (Largest font size whole text)")
                print(f"Title lower y coordinate: {selected_lower_y:.1f}")

    elif len(top_2_texts) == 1:
        selected_title = top_2_texts[0]['text']
        selected_lower_y = top_2_texts[0]['y1']
        print(f"\nFinal title: '{selected_title}' (Only one whole text available)")
        print(f"Title lower y coordinate: {selected_lower_y:.1f}")
    else:
        print("\nNo title candidates found")
        selected_title = None
        selected_lower_y = None

    # Final result summary
    print("\n" + "="*60)
    print("TITLE EXTRACTION RESULT")
    print("="*60)
    if selected_title:
        print(f"Title: {selected_title}")
        print(f"Lower Y Coordinate: {selected_lower_y:.1f}")
        return selected_title, selected_lower_y
    else:
        print("No title extracted")
        return None, None
    print("="*60)



    
