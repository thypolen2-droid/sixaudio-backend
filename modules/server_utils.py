import re
import os
from pathlib import Path

async def clean_story_text_files(story_path):
    """Clean all text files in a story directory"""
    txt_files = sorted(list(story_path.glob("*.txt")))
    
    if not txt_files:
        return
    
    # Patterns to detect Patreon/promotional content
    patreon_patterns = [
        r'patreon',
        r'smashwords',
        r'support me',
        r'buy my book',
        r'author\'?s? words?:',
        r'author\'?s? note:',
        r'https?://[^\s]+',  # URLs
        r'www\.[^\s]+',
        r'chapters? for \$?\d+',
        r'read up to \d+ chapters',
    ]
    
    for txt_file in txt_files:
        try:
            # Read file
            with open(txt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            
            if len(lines) <= 4:
                continue
            
            # Remove first line if it's a duplicate of second line
            if len(lines) >= 2 and lines[0].strip() == lines[1].strip() and lines[0].strip():
                lines = lines[1:]
            
            # Remove Patreon promotional blocks
            cleaned_lines = []
            skip_block = False
            
            for i, line in enumerate(lines):
                line_lower = line.lower()
                is_promo = any(re.search(pattern, line_lower, re.IGNORECASE) for pattern in patreon_patterns)
                
                if is_promo:
                    if not skip_block:
                        skip_block = True
                elif skip_block:
                    if line.strip() == '' or line.strip().startswith('-') or line.strip().startswith('.'):
                        continue
                    else:
                        skip_block = False
                
                if not skip_block and not is_promo:
                    cleaned_lines.append(line)
            
            # Remove last 3 lines if they exist
            if len(cleaned_lines) > 3:
                last_lines_text = ' '.join(cleaned_lines[-3:]).lower()
                if any(pattern in last_lines_text for pattern in ['patreon', 'support', 'smashwords']):
                    cleaned_lines = cleaned_lines[:-3]
            
            # Remove trailing empty lines
            while cleaned_lines and not cleaned_lines[-1].strip():
                cleaned_lines.pop()
            
            # Write back to file
            with open(txt_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(cleaned_lines))
            
        except Exception:
            pass
