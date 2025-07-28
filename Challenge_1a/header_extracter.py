import fitz  # PyMuPDF
from collections import defaultdict
import json

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


def is_meaningful_text(text):
    """Check if text contains at least one alphabet or number."""
    return any(char.isalnum() for char in text)


def detect_tables_in_page(text_spans, page_width, page_height, alignment_threshold=5.0, min_columns=2, min_rows=2):
    """
    Detect table regions in a page based on text alignment patterns.
    
    Args:
        text_spans: List of text span dictionaries with bbox coordinates
        page_width: Width of the page
        page_height: Height of the page
        alignment_threshold: Threshold for considering text aligned (in points)
        min_columns: Minimum number of columns to consider as a table
        min_rows: Minimum number of rows to consider as a table
    
    Returns:
        List of table regions as dictionaries with 'x0', 'y0', 'x1', 'y1' coordinates
    """
    if not text_spans:
        return []
    
    # Group text spans by approximate horizontal positions (columns)
    x_positions = {}
    for span in text_spans:
        x0 = span['x0']
        # Round to nearest alignment threshold to group nearby x positions
        aligned_x = round(x0 / alignment_threshold) * alignment_threshold
        if aligned_x not in x_positions:
            x_positions[aligned_x] = []
        x_positions[aligned_x].append(span)
    
    # Filter out x positions with too few elements (not likely to be columns)
    potential_columns = {x: spans for x, spans in x_positions.items() if len(spans) >= min_rows}
    
    if len(potential_columns) < min_columns:
        return []  # Not enough columns to form a table
    
    # Group spans by approximate vertical positions (rows)
    y_positions = {}
    for span in text_spans:
        y0 = span['y0']
        # Round to nearest alignment threshold to group nearby y positions
        aligned_y = round(y0 / alignment_threshold) * alignment_threshold
        if aligned_y not in y_positions:
            y_positions[aligned_y] = []
        y_positions[aligned_y].append(span)
    
    # Filter out y positions with too few elements (not likely to be rows)
    potential_rows = {y: spans for y, spans in y_positions.items() if len(spans) >= min_columns}
    
    if len(potential_rows) < min_rows:
        return []  # Not enough rows to form a table
    
    # Find grid intersections - areas where multiple columns and rows intersect
    table_regions = []
    
    # Group consecutive columns and rows to identify table regions
    sorted_x_positions = sorted(potential_columns.keys())
    sorted_y_positions = sorted(potential_rows.keys())
    
    # Look for groups of consecutive aligned positions
    x_groups = []
    current_x_group = [sorted_x_positions[0]]
    
    for i in range(1, len(sorted_x_positions)):
        if sorted_x_positions[i] - sorted_x_positions[i-1] <= page_width * 0.3:  # Within 30% of page width
            current_x_group.append(sorted_x_positions[i])
        else:
            if len(current_x_group) >= min_columns:
                x_groups.append(current_x_group)
            current_x_group = [sorted_x_positions[i]]
    
    if len(current_x_group) >= min_columns:
        x_groups.append(current_x_group)
    
    y_groups = []
    current_y_group = [sorted_y_positions[0]]
    
    for i in range(1, len(sorted_y_positions)):
        if sorted_y_positions[i] - sorted_y_positions[i-1] <= 50:  # Within 50 points vertically
            current_y_group.append(sorted_y_positions[i])
        else:
            if len(current_y_group) >= min_rows:
                y_groups.append(current_y_group)
            current_y_group = [sorted_y_positions[i]]
    
    if len(current_y_group) >= min_rows:
        y_groups.append(current_y_group)
    
    # Create table regions from x and y groups
    for x_group in x_groups:
        for y_group in y_groups:
            # Get all spans in this potential table region
            table_spans = []
            for span in text_spans:
                span_x = round(span['x0'] / alignment_threshold) * alignment_threshold
                span_y = round(span['y0'] / alignment_threshold) * alignment_threshold
                if span_x in x_group and span_y in y_group:
                    table_spans.append(span)
            
            # If we have enough spans in a grid pattern, consider it a table
            if len(table_spans) >= min_columns * min_rows:
                # Calculate table bounds
                min_x = min(span['x0'] for span in table_spans)
                max_x = max(span['x1'] for span in table_spans)
                min_y = min(span['y0'] for span in table_spans)
                max_y = max(span['y1'] for span in table_spans)
                
                # Add some padding around the detected table
                padding = 10
                table_region = {
                    'x0': max(0, min_x - padding),
                    'y0': max(0, min_y - padding),
                    'x1': min(page_width, max_x + padding),
                    'y1': min(page_height, max_y + padding),
                    'span_count': len(table_spans)
                }
                table_regions.append(table_region)
    
    # Remove overlapping table regions (keep the one with more spans)
    filtered_regions = []
    for i, region1 in enumerate(table_regions):
        is_overlapped = False
        for j, region2 in enumerate(table_regions):
            if i != j:
                # Check if regions overlap significantly
                overlap_x = max(0, min(region1['x1'], region2['x1']) - max(region1['x0'], region2['x0']))
                overlap_y = max(0, min(region1['y1'], region2['y1']) - max(region1['y0'], region2['y0']))
                overlap_area = overlap_x * overlap_y
                
                region1_area = (region1['x1'] - region1['x0']) * (region1['y1'] - region1['y0'])
                overlap_ratio = overlap_area / region1_area if region1_area > 0 else 0
                
                if overlap_ratio > 0.5:  # 50% overlap
                    if region2['span_count'] > region1['span_count']:
                        is_overlapped = True
                        break
        
        if not is_overlapped:
            filtered_regions.append(region1)
    
    return filtered_regions


def is_text_in_table(text_span, table_regions, overlap_threshold=0.3):
    """
    Check if a text span is within any of the detected table regions.
    Requires substantial overlap (not just touching edges) to avoid false positives.
    
    Args:
        text_span: Dictionary with text span coordinates (x0, y0, x1, y1)
        table_regions: List of table region dictionaries
        overlap_threshold: Minimum overlap ratio required (0.3 = 30% of span must overlap)
    
    Returns:
        Boolean indicating whether the text span is within a table
    """
    span_x0, span_y0, span_x1, span_y1 = text_span['x0'], text_span['y0'], text_span['x1'], text_span['y1']
    span_area = (span_x1 - span_x0) * (span_y1 - span_y0)
    
    for table in table_regions:
        table_x0, table_y0, table_x1, table_y1 = table['x0'], table['y0'], table['x1'], table['y1']
        
        # Calculate overlap area
        overlap_x0 = max(span_x0, table_x0)
        overlap_y0 = max(span_y0, table_y0)
        overlap_x1 = min(span_x1, table_x1)
        overlap_y1 = min(span_y1, table_y1)
        
        # Check if there's actual overlap (not just touching)
        if overlap_x0 < overlap_x1 and overlap_y0 < overlap_y1:
            overlap_area = (overlap_x1 - overlap_x0) * (overlap_y1 - overlap_y0)
            overlap_ratio = overlap_area / span_area if span_area > 0 else 0
            
            # Only consider it "in table" if substantial overlap (e.g., 30% of the text span)
            if overlap_ratio >= overlap_threshold:
                return True
    
    return False


def extract_fitz_data(pdf_path, start_page=1, page1_y_threshold=None):
    """
    Extract text, font, bbox and centered info using pymupdf from start_page to end of document.
    Skip text that is within detected table regions.
    
    Args:
        pdf_path: Path to the PDF file
        start_page: Starting page number (0-indexed)
        page1_y_threshold: Y coordinate threshold for page 1. If provided, only extract text 
                          from below this y coordinate on the first page (page 0)
    """
    doc = fitz.open(pdf_path)
    
    # Check if the document has enough pages
    if len(doc) < start_page + 1:
        print(f"Warning: Document has only {len(doc)} pages, cannot access page {start_page + 1}")
        doc.close()
        return []
    
    results = []
    total_text_spans = 0
    total_table_spans_skipped = 0
    
    # Process from start_page to end of document
    for page_num in range(start_page, len(doc)):
        page = doc[page_num]
        page_width = page.rect.width
        page_height = page.rect.height
        blocks = page.get_text("dict")["blocks"]
        
        # Debug info for page 1
        if page_num == 0 and page1_y_threshold is not None:
            print(f"Page {page_num + 1}: Extracting text below y coordinate {page1_y_threshold}")
        
        # First pass: collect all text spans for table detection
        page_text_spans = []
        for block in blocks:
            if block['type'] != 0:  # skip non-text blocks
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    x0, y0, x1, y1 = span["bbox"]
                    text = span["text"]
                    
                    # Skip text that doesn't contain alphabets or numbers
                    if not is_meaningful_text(text):
                        continue
                    
                    # Special handling for page 1 (page_num == 0): only extract text below y_threshold
                    if page_num == 0 and page1_y_threshold is not None:
                        if y0 < page1_y_threshold:
                            continue  # Skip text above the threshold on page 1
                    
                    page_text_spans.append({
                        'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1, 
                        'text': text, 'span': span
                    })
        
        # Detect tables in this page
        table_regions = detect_tables_in_page(page_text_spans, page_width, page_height)
        
        if table_regions:
            print(f"Page {page_num + 1}: Detected {len(table_regions)} table regions")
            for i, table in enumerate(table_regions):
                print(f"  Table {i+1}: ({table['x0']:.1f}, {table['y0']:.1f}) to ({table['x1']:.1f}, {table['y1']:.1f}) with {table['span_count']} text spans")
        
        # Second pass: extract text spans that are NOT in tables
        page_spans_processed = 0
        page_spans_skipped = 0
        
        for text_span_info in page_text_spans:
            total_text_spans += 1
            page_spans_processed += 1
            
            # Check if this text span is within a table
            if is_text_in_table(text_span_info, table_regions):
                total_table_spans_skipped += 1
                page_spans_skipped += 1
                continue  # Skip text that's inside a table
            
            # Extract information from the span
            span = text_span_info['span']
            x0, y0, x1, y1 = text_span_info['x0'], text_span_info['y0'], text_span_info['x1'], text_span_info['y1']
            text = text_span_info['text']
            
            font = span.get("font", "")
            size = span.get("size", 0.0)
            centered = abs((x0 + x1)/2 - page_width/2) < 10  # margin threshold

            # Determine if font is bold based on font name
            bold = 'Bold' in font or 'bold' in font.lower()

            results.append({
                "text": text,
                "bold": bold,
                "size": size,
                "x0": x0,
                "x1": x1,
                "y0": y0,
                "y1": y1,
                "centered": centered,
                "page": page_num + 1  # Add page number (1-indexed for display)
            })
        
        if page_spans_skipped > 0:
            print(f"Page {page_num + 1}: Processed {page_spans_processed} spans, skipped {page_spans_skipped} table spans")
    
    print(f"\nTable filtering summary:")
    print(f"  Total text spans found: {total_text_spans}")
    print(f"  Text spans skipped (in tables): {total_table_spans_skipped}")
    print(f"  Text spans extracted (outside tables): {len(results)}")
    print(f"  Table filtering rate: {(total_table_spans_skipped/total_text_spans*100):.1f}%" if total_text_spans > 0 else "  Table filtering rate: 0.0%")
    
    doc.close()
    return results


def group_spans_by_line(data, y_threshold=2.0):
    """
    Group text spans that are on the same line (similar y0 and y1 values) within each page.
    """
    # First group by page
    pages = defaultdict(list)
    for item in data:
        pages[item['page']].append(item)
    
    result = []
    
    # Process each page separately
    for page_num in sorted(pages.keys()):
        page_data = pages[page_num]
        grouped_lines = defaultdict(list)
        
        for item in page_data:
            # Create a key based on rounded y0 and y1 values for this page
            y0_key = round(item['y0'] / y_threshold) * y_threshold
            y1_key = round(item['y1'] / y_threshold) * y_threshold
            line_key = (y0_key, y1_key)
            
            grouped_lines[line_key].append(item)
        
        # Sort each line by x0 position and merge text within this page
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
                    'size': spans[0]['size'],
                    'bold': any(span['bold'] for span in spans),
                    'centered': spans[0]['centered'],
                    'page': spans[0]['page'],
                    'span_count': len(spans)
                })
    
    # Sort by page first, then by y position (top to bottom)
    result.sort(key=lambda x: (x['page'], x['y0']))
    return result


def remove_headers_footers(grouped_lines, header_threshold=100, footer_threshold=100):
    """
    Remove repetitive header and footer lines from grouped lines.
    
    Args:
        grouped_lines: List of grouped line dictionaries
        header_threshold: Y-coordinate threshold for header detection (from top)
        footer_threshold: Y-coordinate threshold for footer detection (from bottom)
    """
    if not grouped_lines:
        return grouped_lines
    
    # Group lines by page
    pages = defaultdict(list)
    for line in grouped_lines:
        pages[line['page']].append(line)
    
    # Get page dimensions (assuming all pages have similar dimensions)
    first_page_lines = list(pages.values())[0]
    if not first_page_lines:
        return grouped_lines
    
    # Estimate page height from the range of y-coordinates
    all_y_coords = [line['y0'] for line in grouped_lines]
    page_height = max(all_y_coords) - min(all_y_coords) + 100  # Add some buffer
    
    # Identify potential header and footer lines for each page
    potential_headers = defaultdict(list)  # page -> list of header lines
    potential_footers = defaultdict(list)  # page -> list of footer lines
    
    for page_num, page_lines in pages.items():
        page_lines.sort(key=lambda x: x['y0'])  # Sort by y position
        
        # Find page-specific min and max y coordinates
        page_y_coords = [line['y0'] for line in page_lines]
        page_min_y = min(page_y_coords)
        page_max_y = max(page_y_coords)
        
        for line in page_lines:
            # Check if line is in header area (top of page)
            if line['y0'] - page_min_y <= header_threshold:
                potential_headers[page_num].append(line)
            # Check if line is in footer area (bottom of page)
            elif page_max_y - line['y0'] <= footer_threshold:
                potential_footers[page_num].append(line)
    
    # Find lines that repeat across all pages
    if len(pages) <= 1:
        # If only one page, no repetitive headers/footers to remove
        return grouped_lines
    
    # Check headers: find lines that appear in the same position across all pages
    repetitive_header_texts = set()
    if potential_headers:
        # Get header lines from first page as reference
        first_page_num = min(pages.keys())
        reference_headers = potential_headers[first_page_num]
        
        for ref_line in reference_headers:
            ref_text = ref_line['text'].strip()
            if not ref_text:
                continue
            
            # Check if this text appears in headers of ALL other pages
            appears_in_all_pages = True
            for page_num in pages.keys():
                if page_num == first_page_num:
                    continue
                    
                page_header_texts = [line['text'].strip() for line in potential_headers[page_num]]
                if ref_text not in page_header_texts:
                    appears_in_all_pages = False
                    break
            
            if appears_in_all_pages:
                repetitive_header_texts.add(ref_text)
    
    # Check footers: find lines that appear in the same position across all pages
    repetitive_footer_texts = set()
    if potential_footers:
        # Get footer lines from first page as reference
        first_page_num = min(pages.keys())
        reference_footers = potential_footers[first_page_num]
        
        for ref_line in reference_footers:
            ref_text = ref_line['text'].strip()
            if not ref_text:
                continue
            
            # Check if this text appears in footers of ALL other pages
            appears_in_all_pages = True
            for page_num in pages.keys():
                if page_num == first_page_num:
                    continue
                    
                page_footer_texts = [line['text'].strip() for line in potential_footers[page_num]]
                if ref_text not in page_footer_texts:
                    appears_in_all_pages = False
                    break
            
            if appears_in_all_pages:
                repetitive_footer_texts.add(ref_text)
    
    # Filter out repetitive headers and footers
    filtered_lines = []
    removed_count = 0
    
    for line in grouped_lines:
        line_text = line['text'].strip()
        
        # Check if this line is a repetitive header or footer
        if line_text in repetitive_header_texts or line_text in repetitive_footer_texts:
            removed_count += 1
            continue
        
        filtered_lines.append(line)
    
    print(f"\nRemoved {removed_count} repetitive header/footer lines")
    if repetitive_header_texts:
        print(f"Repetitive headers removed: {list(repetitive_header_texts)}")
    if repetitive_footer_texts:
        print(f"Repetitive footers removed: {list(repetitive_footer_texts)}")
    
    return filtered_lines


def remove_ordinal_suffixes(grouped_lines):
    """
    Remove lines that contain only ordinal suffixes (th, nd, rd, st).
    """
    ordinal_suffixes = {'th', 'nd', 'rd', 'st'}
    
    filtered_lines = []
    removed_count = 0
    removed_texts = []
    
    for line in grouped_lines:
        line_text = line['text'].strip().lower()
        
        # Check if the line contains only ordinal suffixes
        if line_text in ordinal_suffixes:
            removed_count += 1
            removed_texts.append(line['text'].strip())
            continue
        
        filtered_lines.append(line)
    
    print(f"\nRemoved {removed_count} ordinal suffix lines")
    if removed_texts:
        print(f"Ordinal suffixes removed: {removed_texts}")
    
    return filtered_lines


def filter_groups_by_starting_position(consecutive_groups, center_threshold_ratio=0.5):
    """
    Filter out groups that start from center or after center of the page.
    Keep only groups that start from the left side of the page (potential headings).
    
    Args:
        consecutive_groups: List of grouped text dictionaries
        center_threshold_ratio: Ratio of page width to consider as center threshold (0.5 = 50% of page width)
    """
    if not consecutive_groups:
        return consecutive_groups
    
    # Get page width from the first group (assuming all pages have similar width)
    # We'll use the maximum x1 coordinate as an approximation of page width
    all_x1_coords = [group['x1'] for group in consecutive_groups]
    estimated_page_width = max(all_x1_coords)
    center_threshold = estimated_page_width * center_threshold_ratio
    
    filtered_groups = []
    removed_count = 0
    removed_groups = []
    
    for group in consecutive_groups:
        # Check the starting x coordinate of the group
        starting_x = group['x0']
        
        # If the group starts from center or after center, remove it
        if starting_x >= center_threshold:
            removed_count += 1
            removed_groups.append({
                'text': group['text'][:50] + '...' if len(group['text']) > 50 else group['text'],
                'starting_x': starting_x,
                'center_threshold': center_threshold
            })
            continue
        
        filtered_groups.append(group)
    
    print(f"\nRemoved {removed_count} groups that start from center or after center")
    if removed_groups:
        print("Groups removed (showing first 10):")
        for i, removed in enumerate(removed_groups[:10]):
            print(f"  - '{removed['text']}' (starts at x={removed['starting_x']:.1f}, threshold={removed['center_threshold']:.1f})")
    
    return filtered_groups


def filter_groups_by_line_count(consecutive_groups, max_lines=1, large_font_threshold=16.0):
    """
    Filter out groups that contain more than the specified number of lines.
    Keep only groups that are likely to be headings (short, single-line text).
    
    Exception: Groups with font size >= large_font_threshold are preserved regardless of line count,
    as large text is typically headings even if it spans multiple lines.
    
    Args:
        consecutive_groups: List of grouped text dictionaries
        max_lines: Maximum number of lines allowed for a group to be considered a heading
        large_font_threshold: Font size threshold (pt) above which multi-line groups are preserved
    """
    if not consecutive_groups:
        return consecutive_groups
    
    filtered_groups = []
    removed_count = 0
    removed_groups = []
    
    for group in consecutive_groups:
        # Check the line count of the group
        line_count = group.get('line_count', 1)
        font_size = group.get('size', 0)
        
        # If the group has more lines than allowed, check if it should be removed
        if line_count > max_lines:
            # Exception: Keep large font groups regardless of line count
            if font_size >= large_font_threshold:
                filtered_groups.append(group)
                continue
            
            # Remove multi-line groups with smaller fonts
            removed_count += 1
            removed_groups.append({
                'text': group['text'][:50] + '...' if len(group['text']) > 50 else group['text'],
                'line_count': line_count,
                'max_lines': max_lines,
                'font_size': font_size
            })
            continue
        
        filtered_groups.append(group)
    
    print(f"\nRemoved {removed_count} groups that have more than {max_lines} line(s)")
    print(f"Exception: Groups with font size >= {large_font_threshold}pt are preserved regardless of line count")
    if removed_groups:
        print("Groups removed (showing first 10):")
        for i, removed in enumerate(removed_groups[:10]):
            print(f"  - '{removed['text']}' (lines: {removed['line_count']}, font: {removed['font_size']:.1f}pt, max allowed: {removed['max_lines']})")
    
    return filtered_groups


def filter_groups_by_copyright(consecutive_groups):
    """
    Filter out groups that contain copyright symbols or copyright text.
    These are typically part of headers or footers, not document headings.
    
    Args:
        consecutive_groups: List of grouped text dictionaries
    """
    if not consecutive_groups:
        return consecutive_groups
    
    filtered_groups = []
    removed_count = 0
    removed_groups = []
    
    for group in consecutive_groups:
        group_text = group['text'].strip()
        group_text_lower = group_text.lower()
        
        # Check if the group contains copyright symbols or text
        has_copyright = (
            '©' in group_text or
            'copyright' in group_text_lower or
            '(c)' in group_text_lower
        )
        
        if has_copyright:
            removed_count += 1
            removed_groups.append({
                'text': group['text'][:50] + '...' if len(group['text']) > 50 else group['text'],
                'page': group['page']
            })
            continue
        
        filtered_groups.append(group)
    
    print(f"\nRemoved {removed_count} groups containing copyright symbols/text")
    if removed_groups:
        print("Groups removed (showing first 10):")
        for i, removed in enumerate(removed_groups[:10]):
            print(f"  - '{removed['text']}' (Page: {removed['page']})")
    
    return filtered_groups


def filter_duplicate_headings_across_pages(consecutive_groups, position_tolerance=5.0, total_pages=None):
    """
    Filter out groups that appear as duplicates across multiple pages at similar positions.
    If a text appears at similar coordinates with same font size on more than half of total pages,
    it's likely a repetitive header/footer and should be removed.
    
    Args:
        consecutive_groups: List of grouped text dictionaries
        position_tolerance: Tolerance for coordinate matching (default: 5.0 points)
        total_pages: Total number of pages in the document
    """
    if not consecutive_groups or len(consecutive_groups) <= 1:
        return consecutive_groups
    
    # Get total pages from the groups if not provided
    if total_pages is None:
        total_pages = max(group['page'] for group in consecutive_groups)
    
    # Only apply duplicate filtering if there are 2 or more pages
    if total_pages < 2:
        print(f"\nSkipping duplicate filtering - only {total_pages} page(s) found")
        return consecutive_groups
    
    # Group by text content, font size, and approximate position
    text_position_groups = defaultdict(list)
    
    for group in consecutive_groups:
        # Create a key based on text, font size, and rounded position
        text_key = group['text'].strip()
        size_key = round(group['size'], 1)
        x_key = round(group['x0'] / position_tolerance) * position_tolerance
        y_key = round(group['y0'] / position_tolerance) * position_tolerance
        
        composite_key = (text_key, size_key, x_key, y_key)
        text_position_groups[composite_key].append(group)
    
    # Calculate threshold: more than half of total pages
    page_threshold = total_pages * 0.5
    
    filtered_groups = []
    removed_count = 0
    removed_groups = []
    
    print(f"\nAnalyzing duplicate headings across {total_pages} pages (threshold: >{page_threshold:.1f} pages)")
    
    for composite_key, groups in text_position_groups.items():
        text_key, size_key, x_key, y_key = composite_key
        
        # Count unique pages this text appears on
        unique_pages = set(group['page'] for group in groups)
        page_count = len(unique_pages)
        
        # If this text appears on more than half the pages, mark as duplicate
        if page_count > page_threshold:
            # Remove all instances of this duplicate text
            for group in groups:
                removed_count += 1
                removed_groups.append({
                    'text': group['text'][:50] + '...' if len(group['text']) > 50 else group['text'],
                    'page': group['page'],
                    'size': group['size'],
                    'x0': group['x0'],
                    'y0': group['y0'],
                    'page_count': page_count,
                    'threshold': page_threshold
                })
        else:
            # Keep all instances of this non-duplicate text
            filtered_groups.extend(groups)
    
    print(f"Removed {removed_count} duplicate heading groups that appear on >{page_threshold:.1f} pages")
    if removed_groups:
        print("Duplicate headings removed (showing all):")
        # Group removed items by text for cleaner display
        removed_by_text = defaultdict(list)
        for removed in removed_groups:
            removed_by_text[removed['text']].append(removed)
        
        for text, items in removed_by_text.items():
            pages = [str(item['page']) for item in items]
            print(f"  - '{text}' (Size: {items[0]['size']:.1f}pt, X: {items[0]['x0']:.1f}, Pages: {', '.join(pages)}) - appears on {items[0]['page_count']} pages")
    
    return filtered_groups


def filter_page_numbers_dates_toc(consecutive_groups):
    """
    Filter out groups that contain page numbers, table of contents references, or date-only text.
    These are typically not document headings.
    
    Args:
        consecutive_groups: List of grouped text dictionaries
    """
    if not consecutive_groups:
        return consecutive_groups
    
    import re
    
    filtered_groups = []
    removed_count = 0
    removed_groups = []
    
    # Define patterns for page numbers - these will be searched within the text (contains)
    page_patterns = [
        r'page\s+\d+',  # "Page 1", "Page 2", etc.
        r'page\s+\d+\s+of\s+\d+',  # "Page 1 of 5", etc.
        r'\d+\s+of\s+\d+',  # "1 of 5", etc.
        r'\d+\s*/\s*\d+',  # "1/5", etc.
    ]
    
    # Table of contents patterns - these must match exactly (full string)
    toc_exact_patterns = [
        r'^\s*table\s+of\s+contents?\s*$',  # Exact match for "Table of Contents"
        r'^\s*contents?\s*$',  # Exact match for "Contents"
        r'^\s*toc\s*$',  # Exact match for "TOC"
    ]
    
    # Date patterns - these will be searched within the text (contains)
    date_patterns = [
        r'\w+\s+\d{1,2},?\s+\d{4}',  # "January 1, 2024", "Jan 1 2024"
        r'\w+\s+\d{4}',  # "January 2024", "Jan 2024"
        r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # "1/1/2024", "01-01-24"
        r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',  # "2024-01-01", "2024/1/1"
        r'\d{1,2}\s+\w+\s+\d{4}',  # "1 January 2024"
    ]
    
    # Standalone date-related words - these must match exactly (full string)
    date_word_exact_patterns = [
        r'^\s*date\s*$',  # Exact match for "Date"
        r'^\s*time\s*$',  # Exact match for "Time"  
        r'^\s*day\s*$',   # Exact match for "Day"
        r'^\s*month\s*$', # Exact match for "Month"
        r'^\s*year\s*$',  # Exact match for "Year"
    ]
    
    # Compile patterns with their match types
    search_patterns = []  # Patterns to search within text (contains)
    match_patterns = []   # Patterns to match exactly (full string)
    
    search_patterns.extend([(re.compile(pattern, re.IGNORECASE), 'page_number') for pattern in page_patterns])
    search_patterns.extend([(re.compile(pattern, re.IGNORECASE), 'date') for pattern in date_patterns])
    match_patterns.extend([(re.compile(pattern, re.IGNORECASE), 'table_of_contents') for pattern in toc_exact_patterns])
    match_patterns.extend([(re.compile(pattern, re.IGNORECASE), 'date_word') for pattern in date_word_exact_patterns])
    
    for group in consecutive_groups:
        group_text = group['text'].strip()
        should_remove = False
        removal_reason = None
        matched_pattern = None
        
        # Check search patterns (contains matching)
        for compiled_pattern, pattern_type in search_patterns:
            if compiled_pattern.search(group_text):
                should_remove = True
                removal_reason = pattern_type
                matched_pattern = compiled_pattern.pattern
                break
        
        # Check match patterns (exact matching) only if not already marked for removal
        if not should_remove:
            for compiled_pattern, pattern_type in match_patterns:
                if compiled_pattern.match(group_text):
                    should_remove = True
                    removal_reason = pattern_type
                    matched_pattern = compiled_pattern.pattern
                    break
        
        if should_remove:
            removed_count += 1
            removed_groups.append({
                'text': group['text'][:100] + '...' if len(group['text']) > 100 else group['text'],
                'page': group['page'],
                'reason': removal_reason,
                'matched_pattern': matched_pattern
            })
        else:
            filtered_groups.append(group)
    
    print(f"\nRemoved {removed_count} groups containing page numbers, dates, or TOC references")
    if removed_groups:
        print("Groups removed (showing all):")
        # Group by removal reason for cleaner display
        by_reason = {}
        for removed in removed_groups:
            reason = removed['reason']
            if reason not in by_reason:
                by_reason[reason] = []
            by_reason[reason].append(removed)
        
        for reason, items in by_reason.items():
            print(f"  {reason.upper()}:")
            for item in items:
                print(f"    - '{item['text']}' (Page: {item['page']}) [Pattern: {item['matched_pattern']}]")
    
    return filtered_groups


def filter_groups_by_page_position(consecutive_groups, footer_threshold=100, page_height=None):
    """
    Filter out the last group on each page, unless it meets special criteria or is not in the footer region.
    Headings typically don't appear at the very end of pages, but some exceptions apply.
    
    Special criteria for last groups (these will NOT be filtered out):
    1. Contains ':' (colon) at the end
    2. Starts with a number
    3. Is a single word
    4. Not located in the footer region (within footer_threshold points from bottom of page)
    
    Args:
        consecutive_groups: List of grouped text dictionaries
        footer_threshold: Fixed Y-coordinate threshold from the actual bottom of the page (default: 100 points)
        page_height: Actual page height in points (if provided, avoids opening PDF again)
    """
    if not consecutive_groups:
        return consecutive_groups
    
    # Use provided page height or default to standard letter size
    if page_height:
        page_bottom = page_height
        print(f"Using provided page height: {page_bottom:.1f} points")
    else:
        page_bottom = 792  # Default to standard letter size (8.5x11 inches = 612x792 points)
        print(f"No page height provided, using default: {page_bottom:.1f} points")
    
    footer_region_start = page_bottom - footer_threshold  # Fixed threshold from actual page bottom
    
    # Group by page
    pages = defaultdict(list)
    for group in consecutive_groups:
        pages[group['page']].append(group)
    
    filtered_groups = []
    removed_count = 0
    removed_groups = []
    
    for page_num, page_groups in pages.items():
        if not page_groups:
            continue
        
        # Sort groups by y position (top to bottom) to find the last one
        page_groups.sort(key=lambda x: x['y0'])
        
        # Remove only the last group on this page if it doesn't meet special criteria
        if len(page_groups) > 1:
            # Keep all groups except potentially the last one
            for group in page_groups[:-1]:
                filtered_groups.append(group)
            
            # Check if the last group meets any special criteria
            last_group = page_groups[-1]
            last_group_text = last_group['text'].strip()
            
            # Special criteria checks
            ends_with_colon = last_group_text.endswith(':')
            starts_with_number = last_group_text and last_group_text[0].isdigit()
            is_single_word = len(last_group_text.split()) == 1
            not_in_footer_region = last_group['y0'] < footer_region_start
            
            # Keep the last group if it meets any special criteria
            if ends_with_colon or starts_with_number or is_single_word or not_in_footer_region:
                filtered_groups.append(last_group)
            else:
                # Remove the last group if it doesn't meet special criteria and is in footer region
                removed_count += 1
                removed_groups.append({
                    'text': last_group['text'][:50] + '...' if len(last_group['text']) > 50 else last_group['text'],
                    'page': last_group['page'],
                    'y_position': last_group['y0'],
                    'footer_region_start': footer_region_start,
                    'page_bottom': page_bottom
                })
        else:
            # If there's only one group on the page, keep it (don't remove the only content)
            filtered_groups.extend(page_groups)
    
    # Sort back by page and y position
    filtered_groups.sort(key=lambda x: (x['page'], x['y0']))
    
    print(f"\nRemoved {removed_count} groups that are the last group on their page and in footer region")
    print(f"Footer threshold: {footer_threshold} points from bottom of page (Page bottom: {page_bottom:.1f})")
    print(f"Footer region starts at Y-coordinate: {footer_region_start:.1f}")
    if removed_groups:
        print("Groups removed (showing first 10):")
        for i, removed in enumerate(removed_groups[:10]):
            print(f"  - '{removed['text']}' (Page: {removed['page']}, Y: {removed['y_position']:.1f})")
    
    return filtered_groups


def group_consecutive_lines_by_size(grouped_lines, size_threshold=0.1, paragraph_gap_threshold=20):
    """
    Group consecutive lines that have the same font size within each page,
    but also consider paragraph breaks based on vertical spacing.
    """
    # First group by page
    pages = defaultdict(list)
    for line in grouped_lines:
        pages[line['page']].append(line)
    
    result = []
    
    # Process each page separately
    for page_num in sorted(pages.keys()):
        page_lines = pages[page_num]
        # Sort by y position to ensure correct order
        page_lines.sort(key=lambda x: x['y0'])
        
        if not page_lines:
            continue
        
        # Group consecutive lines with same size, considering paragraph breaks
        current_group = [page_lines[0]]
        current_size = round(page_lines[0]['size'], 1)
        
        for i in range(1, len(page_lines)):
            line = page_lines[i]
            line_size = round(line['size'], 1)
            
            # Calculate vertical distance between current line and previous line
            prev_line = page_lines[i-1]
            vertical_gap = abs(line['y0'] - prev_line['y0'])
            
            # Check conditions for grouping:
            # 1. Same font size (within threshold)
            # 2. Small vertical gap (within paragraph threshold)
            # 3. Previous line doesn't end with colon (lines ending with ':' should be in their own group)
            same_size = abs(line_size - current_size) <= size_threshold
            small_gap = vertical_gap <= paragraph_gap_threshold
            prev_line_ends_with_colon = current_group and current_group[-1]['text'].strip().endswith(':')
            
            if same_size and small_gap and not prev_line_ends_with_colon:
                # Same group: same size AND small y difference AND previous line doesn't end with colon
                current_group.append(line)
            else:
                # Different group: different size OR large y difference OR previous line ends with colon
                if prev_line_ends_with_colon:
                    reason = 'colon_separation'
                elif not same_size:
                    reason = 'size_change'
                else:
                    reason = 'paragraph_break'
                
                if current_group:
                    # Combine texts from current group
                    combined_text = ' '.join(line['text'] for line in current_group)
                    result.append({
                        'text': combined_text,
                        'size': current_size,
                        'page': page_num,
                        'bold': any(line['bold'] for line in current_group),
                        'centered': any(line['centered'] for line in current_group),
                        'y0': current_group[0]['y0'],
                        'y1': current_group[-1]['y1'],
                        'x0': min(line['x0'] for line in current_group),
                        'x1': max(line['x1'] for line in current_group),
                        'line_count': len(current_group),
                        'original_lines': [line['text'] for line in current_group],
                        'reason': reason
                    })
                
                # Start new group with current line
                current_group = [line]
                current_size = line_size
        
        # Don't forget the last group
        if current_group:
            combined_text = ' '.join(line['text'] for line in current_group)
            result.append({
                'text': combined_text,
                'size': current_size,
                'page': page_num,
                'bold': any(line['bold'] for line in current_group),
                'centered': any(line['centered'] for line in current_group),
                'y0': current_group[0]['y0'],
                'y1': current_group[-1]['y1'],
                'x0': min(line['x0'] for line in current_group),
                'x1': max(line['x1'] for line in current_group),
                'line_count': len(current_group),
                'original_lines': [line['text'] for line in current_group],
                'reason': 'end_of_page'
            })
    
    # Sort by page first, then by y position
    result.sort(key=lambda x: (x['page'], x['y0']))
    return result


def filter_interrupting_non_numbered_headings(consecutive_groups):
    """
    Remove non-numbered headings that appear between decimal-numbered headings and their valid continuations.
    
    Algorithm:
    1. When encountering a decimal-numbered heading (like 3.1), look for the next valid continuation
    2. Valid continuations are:
       - Same prefix + next number (3.1 → 3.2, 3.1.1, etc.)  
       - Next integer (3.1 → 4)
    3. If valid continuation found: Remove all non-numbered groups between them
    4. If no valid continuation found: Keep all non-numbered groups (structure ended)
    
    Args:
        consecutive_groups: List of grouped text dictionaries
    
    Returns:
        Filtered list with interrupting non-numbered headings removed
    """
    if not consecutive_groups:
        return consecutive_groups
    
    import re
    
    def parse_number_heading(text):
        """Parse a numbered heading and return its components"""
        text = text.strip()
        # Match patterns like "1", "1.", "1)", "2.1", "3.4.2", etc.
        number_pattern = r'^\d+(\.\d*)*[.\)]?\s+'
        match = re.match(number_pattern, text)
        if not match:
            return None
        
        # Extract the number part (remove trailing punctuation and space)
        number_part = match.group().strip()
        # Remove trailing punctuation
        number_part = re.sub(r'[.\)]+$', '', number_part)
        
        # Split into components
        parts = number_part.split('.')
        return [int(p) for p in parts if p.isdigit()]
    
    def is_valid_continuation(current_numbers, next_numbers):
        """Check if next_numbers is a valid continuation of current_numbers"""
        if not current_numbers or not next_numbers:
            return False
        
        # Case 1: Same prefix + next number (3.1 → 3.2, 3.1.1)
        if len(current_numbers) == len(next_numbers):
            # Same level: check if only last number incremented
            if current_numbers[:-1] == next_numbers[:-1] and next_numbers[-1] > current_numbers[-1]:
                return True
        elif len(next_numbers) == len(current_numbers) + 1:
            # Sublevel: 3.1 → 3.1.1
            if current_numbers == next_numbers[:-1]:
                return True
        
        # Case 2: Next integer (3.1 → 4)  
        if len(next_numbers) == 1 and len(current_numbers) >= 1:
            if next_numbers[0] == current_numbers[0] + 1:
                return True
        
        return False
    
    def find_next_continuation(groups, start_idx, current_numbers):
        """Find the next valid continuation after start_idx"""
        for i in range(start_idx + 1, len(groups)):
            next_numbers = parse_number_heading(groups[i]['text'])
            if next_numbers and is_valid_continuation(current_numbers, next_numbers):
                return i
        return None
    
    filtered_groups = []
    removed_count = 0
    removed_groups = []
    
    i = 0
    while i < len(consecutive_groups):
        current_group = consecutive_groups[i]
        current_numbers = parse_number_heading(current_group['text'])
        
        # Always keep the current group initially
        filtered_groups.append(current_group)
        
        # If current group is a decimal-numbered heading, look for continuation
        if current_numbers and len(current_numbers) > 1:  # Decimal heading (e.g., 3.1, 2.3.4)
            continuation_idx = find_next_continuation(consecutive_groups, i, current_numbers)
            
            if continuation_idx is not None:
                # Found valid continuation - remove all non-numbered groups in between
                for j in range(i + 1, continuation_idx):
                    intervening_numbers = parse_number_heading(consecutive_groups[j]['text'])
                    if not intervening_numbers:  # Non-numbered group
                        removed_count += 1
                        removed_groups.append({
                            'text': consecutive_groups[j]['text'][:100] + '...' if len(consecutive_groups[j]['text']) > 100 else consecutive_groups[j]['text'],
                            'page': consecutive_groups[j]['page'],
                            'reason': f'interrupting_between_{".".join(map(str, current_numbers))}_and_{".".join(map(str, parse_number_heading(consecutive_groups[continuation_idx]["text"])))}'
                        })
                    else:
                        # Keep numbered groups even if they're in between
                        filtered_groups.append(consecutive_groups[j])
                
                # Skip to the continuation point
                i = continuation_idx
                continue
        
        i += 1
    
    print(f"\nRemoved {removed_count} non-numbered headings that interrupt decimal-numbered sequences")
    if removed_groups:
        print("Interrupting non-numbered headings removed:")
        for removed in removed_groups:
            print(f"  - '{removed['text']}' (Page: {removed['page']}) [{removed['reason']}]")
    
    return filtered_groups


def apply_heading_filters(filtered_groups):
    """
    Apply custom filtering criteria to identify headings from the final filtered groups.
    
    Criteria:
    1) Groups with the top 2 biggest font sizes are considered headings
    2) Groups containing single words are considered headings  
    3) Groups containing ':' are considered headings
    4) Groups containing a number or roman numeral are considered headings
    
    Args:
        filtered_groups: List of final filtered group dictionaries
    
    Returns:
        List of groups that match any of the heading criteria
    """
    if not filtered_groups:
        return []
    
    heading_groups = []
    
    # Get unique font sizes and find the top 2 biggest
    font_sizes = list(set(group['size'] for group in filtered_groups))
    font_sizes.sort(reverse=True)  # Sort in descending order
    top_2_sizes = font_sizes[:2] if len(font_sizes) >= 2 else font_sizes
    
    print(f"\nApplying heading filters:")
    print(f"Top 2 biggest font sizes: {top_2_sizes}")
    
    criteria_matches = {
        'top_2_sizes': 0,
        'single_word': 0, 
        'contains_colon': 0,
        'contains_number_or_roman': 0,
        'excluded_lowercase': 0,
        'excluded_fullstop_end': 0,
        'excluded_fullstop_between': 0,
        'excluded_following_colon': 0,
        'excluded_transitional_words': 0
    }
    
    # Helper function to check for roman numerals
    def contains_roman_numeral(text):
        """Check if text contains roman numerals (I, II, III, IV, V, VI, VII, VIII, IX, X, etc.)"""
        import re
        # Pattern for common roman numerals (case insensitive)
        roman_pattern = r'\b(?=[MDCLXVI])M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})\b'
        return bool(re.search(roman_pattern, text.upper()))
    
    # Helper function to check if text starts with lowercase
    def starts_with_lowercase(text):
        """Check if text starts with a lowercase letter"""
        return text and text[0].islower()
    
    # Helper function to check if text ends with full stop
    def ends_with_fullstop(text):
        """Check if text ends with a full stop"""
        return text.strip().endswith('.')
    
    # Helper function to check for invalid full stops in between
    def has_invalid_fullstop_between(text):
        """
        Check if text contains full stops in between that are not part of numbers.
        Valid: 1., 1.1, 2.3.4, St. (at end), Dr. (at end)
        Invalid: St., Suite (full stop followed by comma), M5C 1M3. Proposals (full stop in middle)
        """
        import re
        
        # Remove valid number patterns first (like 1., 1.1, 2.3.4, etc.)
        # Pattern for decimal numbers: one or more digits, followed by dot, followed by optional digits
        text_without_numbers = re.sub(r'\b\d+(\.\d*)*\.?', '', text)
        
        # Also remove common abbreviations at the end (like St., Dr., etc.)
        # But only if they're at the very end or followed by whitespace
        text_without_end_abbrev = re.sub(r'\b[A-Z][a-z]*\.\s*$', '', text_without_numbers)
        text_without_abbrev = re.sub(r'\b[A-Z][a-z]*\.\s+', '', text_without_end_abbrev)
        
        # Now check if there are any remaining full stops
        # If there are, they're likely invalid (in the middle of text)
        return '.' in text_without_abbrev.strip()
    
    # Helper function to check for transitional/connector words
    def contains_transitional_words(text):
        """
        Check if text contains transitional or connector words that typically appear in body text, not headings.
        Examples: specifically, however, furthermore, additionally, therefore, etc.
        """
        text_lower = text.lower()
        
        # List of transitional/connector words that are unlikely to appear in headings
        transitional_words = [
            'specifically,', 'however,', 'furthermore,', 'additionally,', 'therefore,',
            'moreover,', 'consequently,', 'nevertheless,', 'nonetheless,', 'meanwhile,',
            'subsequently,', 'similarly,', 'conversely,', 'alternatively,', 'accordingly,',
            'hence,', 'thus,', 'indeed,', 'likewise,', 'otherwise,', 'namely,',
            'for example,', 'for instance,', 'in particular,', 'in addition,', 'in contrast,',
            'on the other hand,', 'as a result,', 'in conclusion,', 'in summary,',
            'specifically ', 'however ', 'furthermore ', 'additionally ', 'therefore ',
            'moreover ', 'consequently ', 'nevertheless ', 'nonetheless ', 'meanwhile ',
            'subsequently ', 'similarly ', 'conversely ', 'alternatively ', 'accordingly ',
            'hence ', 'thus ', 'indeed ', 'likewise ', 'otherwise ', 'namely '
        ]
        
        # Check if any transitional words appear in the text
        for word in transitional_words:
            if word in text_lower:
                return True
        
        return False
    
    # Helper function to check for "following" + ":" combination
    def contains_following_with_colon(text):
        """
        Check if text contains both "following" and ":" which typically indicates 
        introductory text rather than a heading.
        """
        text_lower = text.lower()
        return 'following' in text_lower and ':' in text
    
    for group in filtered_groups:
        group_text = group['text'].strip()
        font_size = group['size']
        is_heading = False
        matched_criteria = []
        
        # Criterion 1: Top 2 biggest font sizes
        if font_size in top_2_sizes:
            is_heading = True
            matched_criteria.append("top_2_sizes")
            criteria_matches['top_2_sizes'] += 1
        
        # Criterion 2: Single words (no spaces after stripping)
        if len(group_text.split()) == 1:
            is_heading = True
            matched_criteria.append("single_word")
            criteria_matches['single_word'] += 1
        
        # Criterion 3: Contains ':'
        if ':' in group_text:
            is_heading = True
            matched_criteria.append("contains_colon")
            criteria_matches['contains_colon'] += 1
        
        # Criterion 4: Contains a number or roman numeral
        has_number = any(char.isdigit() for char in group_text)
        has_roman = contains_roman_numeral(group_text)
        if has_number or has_roman:
            is_heading = True
            matched_criteria.append("contains_number_or_roman")
            criteria_matches['contains_number_or_roman'] += 1
        
        # Apply exclusion criteria - remove groups that match any exclusion rule
        if is_heading:
            excluded = False
            exclusion_reason = None
            
            # Exclusion 1: Starts with lowercase letter
            if starts_with_lowercase(group_text):
                excluded = True
                exclusion_reason = "starts_with_lowercase"
                criteria_matches['excluded_lowercase'] += 1
            
            # Exclusion 2: Ends with full stop
            elif ends_with_fullstop(group_text):
                excluded = True
                exclusion_reason = "ends_with_fullstop"
                criteria_matches['excluded_fullstop_end'] += 1
            
            # Exclusion 3: Contains invalid full stops in between
            elif has_invalid_fullstop_between(group_text):
                excluded = True
                exclusion_reason = "invalid_fullstop_between"
                criteria_matches['excluded_fullstop_between'] += 1
            
            # Exclusion 4: Contains "following" and ":" combination
            elif contains_following_with_colon(group_text):
                excluded = True
                exclusion_reason = "contains_following_with_colon"
                criteria_matches['excluded_following_colon'] += 1
            
            # Exclusion 5: Contains transitional/connector words
            elif contains_transitional_words(group_text):
                excluded = True
                exclusion_reason = "contains_transitional_words"
                criteria_matches['excluded_transitional_words'] += 1
            
            # Only add to heading groups if not excluded
            if not excluded:
                heading_group = {
                    'text': group_text,
                    'page': group['page'],
                    'size': font_size,
                    'matched_criteria': matched_criteria,
                    'x0': group['x0'],
                    'y0': group['y0'],
                    'y1': group['y1']  # Include y1 coordinate for height calculation
                }
                heading_groups.append(heading_group)
    
    # Sort by page first, then by y position
    heading_groups.sort(key=lambda x: (x['page'], x['y0']))
    
    print(f"\nHeading criteria matches:")
    print(f"  - Top 2 sizes: {criteria_matches['top_2_sizes']} groups")
    print(f"  - Single word: {criteria_matches['single_word']} groups") 
    print(f"  - Contains ':': {criteria_matches['contains_colon']} groups")
    print(f"  - Contains number or roman: {criteria_matches['contains_number_or_roman']} groups")
    print(f"\nExclusion criteria (filtered out):")
    print(f"  - Starts with lowercase: {criteria_matches['excluded_lowercase']} groups")
    print(f"  - Ends with full stop: {criteria_matches['excluded_fullstop_end']} groups")
    print(f"  - Invalid full stop between: {criteria_matches['excluded_fullstop_between']} groups")
    print(f"  - Contains 'following' + ':': {criteria_matches['excluded_following_colon']} groups")
    print(f"  - Contains transitional words: {criteria_matches['excluded_transitional_words']} groups")
    print(f"  - Total heading groups (after exclusions): {len(heading_groups)}")
    
    return heading_groups


def create_json_data(heading_groups, title_text=""):
    """
    Create JSON data structure from heading groups and title.
    
    Args:
        heading_groups: List of heading group dictionaries
        title_text: Title of the document
    
    Returns:
        Dictionary containing the JSON structure
    """
    # Calculate heading levels based on font sizes
    if not heading_groups:
        outline_data = {
            "title": title_text,
            "outline": []
        }
    else:
        # Get unique font sizes and sort them in descending order (largest first)
        font_sizes = list(set(group['size'] for group in heading_groups))
        font_sizes.sort(reverse=True)
        
        # Create a mapping from font size to heading level (H1, H2, H3, etc.)
        size_to_level = {}
        for i, size in enumerate(font_sizes):
            size_to_level[size] = f"H{i + 1}"
        
        print(f"\nHeading level mapping:")
        for size in font_sizes:
            print(f"  Font size {size:.1f}pt -> {size_to_level[size]}")
        
        outline_data = {
            "title": title_text,
            "outline": []
        }
        
        for group in heading_groups:
            outline_entry = {
                "level": size_to_level[group['size']],
                "text": group['text'],
                "page": group['page'] - 1
            }
            outline_data["outline"].append(outline_entry)
    
    return outline_data


def save_headings_to_json(heading_groups, title_text="", output_file="headings_outline.json"):
    """
    Save the identified headings to a JSON file in the specified format with heading levels.
    
    Args:
        heading_groups: List of heading group dictionaries
        title_text: Title of the document to include in the JSON
        output_file: Output JSON file path
    """
    # Create JSON data using the helper function
    outline_data = create_json_data(heading_groups, title_text)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(outline_data, f, indent=4, ensure_ascii=False)
    
    print(f"\nSaved {len(heading_groups)} headings to {output_file}")


def create_initial_json_with_title(title_text="", output_file="headings_outline.json"):
    """
    Create an initial JSON file with just the title and empty outline.
    This ensures we always have a JSON file even if no headings are found.
    
    Args:
        title_text: Title of the document to include in the JSON
        output_file: Output JSON file path
    """
    outline_data = {
        "title": title_text,
        "outline": []
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(outline_data, f, indent=4, ensure_ascii=False)
    
    print(f"Created initial JSON with title: '{title_text}' in {output_file}")


def update_json_with_headings(heading_groups, output_file="headings_outline.json"):
    """
    Update existing JSON file with headings. This function reads the existing JSON,
    adds the headings to the outline, and saves it back.
    
    Args:
        heading_groups: List of heading group dictionaries
        output_file: Output JSON file path
    """
    # Read existing JSON
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            outline_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # If file doesn't exist or is corrupted, create new structure
        outline_data = {
            "title": "",
            "outline": []
        }
    
    # Calculate heading levels based on font sizes
    if heading_groups:
        # Get unique font sizes and sort them in descending order (largest first)
        font_sizes = list(set(group['size'] for group in heading_groups))
        font_sizes.sort(reverse=True)
        
        # Create a mapping from font size to heading level (H1, H2, H3, etc.)
        size_to_level = {}
        for i, size in enumerate(font_sizes):
            size_to_level[size] = f"H{i + 1}"
        
        print(f"\nHeading level mapping:")
        for size in font_sizes:
            print(f"  Font size {size:.1f}pt -> {size_to_level[size]}")
        
        # Add headings to outline
        outline_data["outline"] = []
        for group in heading_groups:
            outline_entry = {
                "level": size_to_level[group['size']],
                "text": group['text'],
                "page": group['page'] - 1
            }
            outline_data["outline"].append(outline_entry)
    
    # Save updated JSON
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(outline_data, f, indent=4, ensure_ascii=False)
    
    print(f"\nUpdated JSON with {len(heading_groups)} headings in {output_file}")


# Example usage - extracting text from page 1 (below y threshold) and all text from page 2 to end
# pdf_file = "C:\\python\\adobe\\app\\input\\Nayan_CV2.pdf"
# pdf_file = "C:\\python\\adobe\\app\\input\\E0CCG5S312.pdf"
def heading_extracter_main(pdf_file, y_threshold=0 , title_data=None):

    # Extract title text from title_data if available
    title_text = ""
    if title_data:
        title_text = title_data.strip()
    
    # Set y coordinate threshold for page 1 - only extract text below this y coordinate on page 1
    page1_y_threshold = y_threshold  # Adjust this value as needed (e.g., 200 points from top)

    print(f"Extracting text from page 1 (below y={page1_y_threshold}) and all text from page 2 to end: {pdf_file}")

    # Extract data from page 1 to end (start_page=0 because it's 0-indexed), with y threshold for page 1
    data = extract_fitz_data(pdf_file, start_page=0, page1_y_threshold=page1_y_threshold)

    if data:
        # Get page count info and page dimensions
        doc = fitz.open(pdf_file)
        total_pages = len(doc)
        
        # Get the actual page height from the first page
        if len(doc) > 0:
            first_page = doc[0]
            page_rect = first_page.rect
            page_height = page_rect.height
            print(f"Page dimensions: {page_rect.width:.1f} x {page_height:.1f} points")
        
        doc.close()
        
        print(f"\nFound {len(data)} text spans from page 1 (below y={page1_y_threshold}) and pages 2-{total_pages}")
        
        # Print the metadata table for individual spans (first 50 only)
        print("\n=== ALL EXTRACTED TEXT SPANS (First 50) ===")
        pretty_print_metadata(data[:50])

        # Group spans by line position
        print("\n=== GROUPED BY LINES ===")
        grouped_lines = group_spans_by_line(data)
        print(f"Total grouped lines: {len(grouped_lines)}")
        
        # # Print the grouped lines (first 50 only)
        # print("\nGrouped lines (first 50):")
        # for i, line in enumerate(grouped_lines[:50]):

        # Print ALL the grouped lines
        print(f"\nALL {len(grouped_lines)} grouped lines:")
        for i, line in enumerate(grouped_lines):
            print(f"Line {i+1}: '{line['text']}' (Page: {line['page']}, Size: {line['size']:.1f}pt, Y: {line['y0']:.1f}, Spans: {line['span_count']})")
        
        # Remove repetitive headers and footers
        print("\n=== REMOVING REPETITIVE HEADERS/FOOTERS ===")
        filtered_lines = remove_headers_footers(grouped_lines, header_threshold=100, footer_threshold=100)
        print(f"Lines after removing headers/footers: {len(filtered_lines)}")
        
        # Remove ordinal suffix lines
        print("\n=== REMOVING ORDINAL SUFFIX LINES ===")
        filtered_lines = remove_ordinal_suffixes(filtered_lines)
        print(f"Lines after removing ordinal suffixes: {len(filtered_lines)}")
        
        # Print the filtered lines (first 50 only)
        print("\nFiltered lines (first 50):")
        for i, line in enumerate(filtered_lines[:50]):
            print(f"Line {i+1}: '{line['text']}' (Page: {line['page']}, Size: {line['size']:.1f}pt, Y: {line['y0']:.1f}, Spans: {line['span_count']})")
        
        # Filter groups by starting position (remove center/right-aligned groups)
        print("\n=== FILTERING GROUPS BY STARTING POSITION ===")
        position_filtered_lines = filter_groups_by_starting_position(filtered_lines, center_threshold_ratio=0.5)
        print(f"Lines after position filtering: {len(position_filtered_lines)}")
        
        # Group consecutive lines by font size
        print("\n=== GROUPED BY CONSECUTIVE FONT SIZES (WITH PARAGRAPH BREAKS) ===")
        consecutive_groups = group_consecutive_lines_by_size(position_filtered_lines, paragraph_gap_threshold=20)
        print(f"Total consecutive font size groups: {len(consecutive_groups)}")
        
        # Filter groups by line count (remove multi-line groups)
        print("\n=== FILTERING GROUPS BY LINE COUNT ===")
        line_count_filtered_groups = filter_groups_by_line_count(consecutive_groups, max_lines=1)
        print(f"Groups after line count filtering: {len(line_count_filtered_groups)}")
        
        # Filter groups by page position (remove groups near bottom of page)
        print("\n=== FILTERING GROUPS BY PAGE POSITION ===")
        page_position_filtered_groups = filter_groups_by_page_position(line_count_filtered_groups, page_height=page_height)
        print(f"Groups after page position filtering: {len(page_position_filtered_groups)}")
        
        # Filter groups by copyright content (remove copyright notices)
        print("\n=== FILTERING GROUPS BY COPYRIGHT CONTENT ===")
        copyright_filtered_groups = filter_groups_by_copyright(page_position_filtered_groups)
        print(f"Groups after copyright filtering: {len(copyright_filtered_groups)}")
        
        # Filter duplicate headings across pages (remove repetitive headings that appear on multiple pages)
        print("\n=== FILTERING DUPLICATE HEADINGS ACROSS PAGES ===")
        duplicate_filtered_groups = filter_duplicate_headings_across_pages(copyright_filtered_groups, total_pages=total_pages)
        print(f"Groups after duplicate filtering: {len(duplicate_filtered_groups)}")
        
        # Filter page numbers, dates, and table of contents references
        print("\n=== FILTERING PAGE NUMBERS, DATES, AND TOC REFERENCES ===")
        page_date_filtered_groups = filter_page_numbers_dates_toc(duplicate_filtered_groups)
        print(f"Groups after page/date/TOC filtering: {len(page_date_filtered_groups)}")
        
        # Print all the final filtered groups
        print(f"\nFinal filtered groups (potential headings, showing all {len(page_date_filtered_groups)}):")
        for i, group in enumerate(page_date_filtered_groups):
            reason_info = f" [Reason: {group.get('reason', 'unknown')}]" if group.get('reason') else ""
            print(f"Group {i+1}: (Page: {group['page']}, Size: {group['size']:.1f}pt, Lines: {group['line_count']}, X-start: {group['x0']:.1f}){reason_info}")
            print(f"  Combined text: '{group['text']}'")
            print("-" * 80)
        
        # Apply heading filters and save to JSON
        print("\n" + "="*80)
        print("APPLYING HEADING FILTERS")
        print("="*80)
        
        # First filter out interrupting non-numbered headings
        print("\n=== FILTERING INTERRUPTING NON-NUMBERED HEADINGS ===")
        structure_filtered_groups = filter_interrupting_non_numbered_headings(page_date_filtered_groups)
        print(f"Groups after structure filtering: {len(structure_filtered_groups)}")
        
        heading_groups = apply_heading_filters(structure_filtered_groups)
        
        # Create JSON data structure
        title_text = ""
        if title_data:
            title_text = title_data.strip()
        
        json_data = create_json_data(heading_groups, title_text)
        
        # Print the identified headings with recalculated font sizes and height calculations
        print(f"\nIdentified headings (showing all {len(heading_groups)}):")
        for i, heading in enumerate(heading_groups):
            criteria_str = ", ".join(heading['matched_criteria'])
            
            # Recalculate font size based on the original data
            # Find the original text spans that match this heading
            original_font_size = heading['size']  # Keep original as fallback
            
            
            # Calculate height for this individual heading from its own coordinates
            # The heading group should have y0 and y1 coordinates from the group_consecutive_lines_by_size function
            if 'y1' in heading:
                individual_height = heading['y1'] - heading['y0']
                height_info = f", Height: {individual_height:.5f}pt"
            else:
                height_info = ""
            
            print(f"Heading {i+1}: '{heading['text']}' , Original: {original_font_size:.4f}pt,{height_info}) ")
        
        return json_data

    else:
        print("No text data found from page 2 onwards")
        # Return JSON with title only
        title_text = ""
        if title_data:
            title_text = title_data.strip()
        return create_json_data([], title_text)
