# 🧹 Text File Cleaner Feature

## What It Does

The new **Clean Text Files** feature automatically cleans up your scraped chapters by:

1. **Removing duplicate first lines** - Often a duplicate of the chapter title
2. **Removing Patreon promotional blocks** - Detects and removes author notes, Patreon links, Smashwords promotions, etc.
3. **Removing promotional last lines** - Cleans up any remaining promotional text at the end

### Detected Promotional Content:
- Patreon links and mentions
- Smashwords links
- "Support me" messages
- "Buy my book" messages
- Author's words/notes
- URLs (http/https/www)
- "Read up to X chapters for $Y"
- Lines with dashes (----) or dots (....) surrounding promotional text

---

## How to Use

1. From the main menu, select option **4** - "🧹 Clean Text Files"
2. Choose which story to clean
3. Review the actions and confirm
4. The tool will process all `.txt` files in that story

---

## Example

### Before Cleaning:
```
Chapter 1: The Beginning
Chapter 1: The Beginning

Author's words:
Please support me on Patreon!
-------------------------------------------------------------
you can read up to 133 chapters for 1$ patreonage in patreon:
https://www.patreon.com/Fatenovels
------------------------------------------------------------
Please buy my book at Smashwords to support me.

This is the actual content of the chapter...
More content here...

Support me on Patreon!
Visit patreon.com/author
Thanks for reading!
```

### After Cleaning:
```
Chapter 1: The Beginning

This is the actual content of the chapter...
More content here...
```

**All promotional content removed automatically!** ✨

---

## Features

✅ **Safe Processing**
- Skips files that are too short (≤4 lines)
- Shows confirmation before processing
- Displays progress bar

✅ **Detailed Feedback**
- Shows how many files were cleaned
- Reports any skipped files
- Shows any errors encountered

✅ **Fast & Efficient**
- Processes all chapters in seconds
- Works on entire story at once

---

## When to Use

Use this feature **after scraping** and **before converting to audio**:

1. ✅ Scrape New Story
2. ✅ **Clean Text Files** ← Do this!
3. ✅ Convert to Audio

This ensures your audio files don't have:
- Duplicate chapter titles at the start
- Patreon promotional text at the end

---

## Safety Notes

⚠️ **This modifies your files directly**
- The original files will be changed
- There's no undo (unless you re-scrape)
- Files with ≤4 lines are automatically skipped for safety

💡 **Tip**: If you're unsure, test on one story first before cleaning all your library!

---

## Menu Location

Main Menu → Option **4** → "🧹 Clean Text Files (Remove Duplicates & Patreon)"
