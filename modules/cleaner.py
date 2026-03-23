import re

def clean_text(text):
    """
    Cleans text by removing common novel scraper artifacts.
     - URLs
     - Brackets/Parentheses containing 'source', 'translator', etc.
     - Discord/Patreon links
     - Excessive whitespace
    """
    if not text:
        return ""

    # 1. Remove URLs
    text = re.sub(r'http\S+', '', text, flags=re.MULTILINE)
    text = re.sub(r'www\.\S+', '', text, flags=re.MULTILINE)

    # 2. Remove common noisy patterns
    # Things like [Translator Note: ...] or (Source: ...)
    # balancing precision vs recall is key here. 
    # We target specific keywords inside brackets to avoid deleting story content.
    keywords = r"translator|source|edited by|proofread by|patreon|discord|ko-fi|donate"
    
    # Remove [...] containing keywords
    text = re.sub(r'\[[^]]*?(?:' + keywords + r')[^]]*?\]', '', text, flags=re.IGNORECASE)
    
    # Remove (...) containing keywords
    text = re.sub(r'\([^)]*?(?:' + keywords + r')[^)]*?\)', '', text, flags=re.IGNORECASE)

    # 3. Specific patterns
    text = re.sub(r'discord\.gg\/\w+', '', text, flags=re.IGNORECASE)
    
    # 4. Fix formatting
    # Collapse multiple newlines/spaces
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    
    # 5. Remove consecutive duplicate lines (e.g. repeated chapter titles)
    lines = text.split('\n')
    deduped_lines = []
    last_content_line = ""
    
    for line in lines:
        clean_line = line.strip()
        if not clean_line:
            deduped_lines.append(line)
            continue
            
        if clean_line != last_content_line:
            deduped_lines.append(line)
            last_content_line = clean_line
    
    return '\n'.join(deduped_lines).strip()
