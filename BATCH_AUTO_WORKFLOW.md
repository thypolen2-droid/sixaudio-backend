# Batch Mode Auto-Workflow - Complete Guide

## Overview

**Option 2: Batch Folder Mode** now provides a fully automated workflow from text files to combined audio!

## New Features

### 1. ✅ Audios Subfolder
- Automatically creates `Audios/` folder inside your input folder
- All MP3 files saved there (not in global `output/` folder)
- Keeps each story's audio organized with its text files

### 2. ✅ Auto-Fix Corrupted Files
- Automatically scans for corrupted/empty MP3 files after conversion
- Detects files that are 0 bytes, <1KB, or unreadable
- Automatically regenerates corrupted files from matching text files
- Shows detailed progress and results

### 3. ✅ Auto-Combine
- Automatically combines all audio files using FFmpeg
- No prompts or confirmations needed
- Creates timestamped combined file in the same `Audios/` folder

## How It Works

### Complete Workflow:

```
1. Select Option 2: Batch Folder Mode
   ↓
2. Enter folder path with .txt files
   ↓
3. Confirm batch conversion
   ↓
4. 📂 Creates "Audios/" subfolder
   ↓
5. 🎯 Converts all .txt → .mp3
   ↓
6. 🔍 Checks for corrupted files
   ↓
7. 🔧 Auto-fixes any corrupted files
   ↓
8. 🎵 Auto-combines all audio files
   ↓
9. ✅ Done! Combined file ready in Audios/
```

## Example Session

```
⚡ Select option: 2

╭─────────────────────────────────────────╮
│ 📁 Batch Folder Mode                    │
╰─────────────────────────────────────────╯

Enter folder path: Oh no! After I Reincarnated, My Moms Became Son-cons! #Book 3 Chapter 13

Found 565 files

Proceed with batch conversion? [y/n]: y

📂 Created output folder: Audios/

Overall Progress ████████████████████ 565/565
✅ 0001_Chapter 1.txt → 0001_Chapter 1.mp3
✅ 0002_Chapter 2.txt → 0002_Chapter 2.mp3
... (563 more)

🎉 Batch complete! 565/565 successful

🔍 Checking for corrupted audio files...
Found 12 corrupted files
Auto-fixing...

✅ Fixed: 0024_Reply to.mp3
✅ Fixed: 0025_Reply to.mp3
... (10 more)

✅ Fixed 12/12 corrupted files

🎵 Combining all audio files...
Found 565 audio files
📊 Total size: 850.62 MB

💾 Combining audio with ffmpeg...
✅ Successfully combined 565 files
💾 Saved as: combined_audio_20260122_072714.mp3 (850.62 MB)
📂 Location: .../Audios
ℹ️  Original files preserved
```

## File Structure

### Before:
```
Story Folder/
├── 0001_Chapter 1.txt
├── 0002_Chapter 2.txt
└── ...
```

### After:
```
Story Folder/
├── 0001_Chapter 1.txt
├── 0002_Chapter 2.txt
├── ...
└── Audios/
    ├── 0001_Chapter 1.mp3
    ├── 0002_Chapter 2.mp3
    ├── ...
    └── combined_audio_20260122_072714.mp3  ← Final output!
```

## Benefits

✅ **Fully Automated** - One command does everything  
✅ **Organized** - Audio stays with source text  
✅ **Reliable** - Auto-fixes corrupted files  
✅ **Complete** - Ends with combined audio ready  
✅ **Time-Saving** - No manual steps needed  
✅ **Error-Resistant** - Handles failures gracefully  

## Technical Details

### Auto-Fix Logic:
1. Scans all MP3 files in Audios folder
2. Checks file size (0 bytes or <1KB = corrupted)
3. Optionally checks audio duration if pydub available
4. Finds matching .txt file by filename stem
5. Regenerates audio from text file
6. Reports success/failure for each file

### Auto-Combine Logic:
1. Uses FFmpeg concat demuxer (fast, no re-encoding)
2. Runs in "auto mode" (no prompts)
3. Saves to same Audios folder
4. Preserves original individual MP3 files
5. Creates timestamped combined file

### Error Handling:
- Empty text files → Skipped with warning
- Missing text files → Reported, not fixed
- FFmpeg errors → Detailed error message shown
- Network errors (TTS) → Caught and reported

## Usage Tips

### For Best Results:
1. **Ensure stable internet** - TTS requires connection
2. **Have FFmpeg installed** - Required for combining
3. **Check text encoding** - UTF-8 preferred
4. **Verify folder path** - Use absolute or relative paths

### If Something Goes Wrong:
- **Corrupted files persist**: Check text file content
- **Combine fails**: Ensure FFmpeg is in PATH
- **Out of memory**: Process smaller batches
- **Network timeout**: Retry failed files manually

## Modified Files

- ✅ `modules/tools.py` - Enhanced batch processing logic
- ✅ `modules/tools.py` - Added `auto_mode` to combination logic

## Comparison with Manual Workflow

### Old Way (4 steps):
```
1. Option 2 → Batch process to output/
2. Option 5 → Fix corrupted files
3. Option 4 → Combine files
4. Manually move combined file
⏱️ Time: ~10 minutes of manual work
```

### New Way (1 step):
```
1. Option 2 → Enter folder path → Done!
⏱️ Time: 30 seconds of manual work
```

**Time Saved: ~9.5 minutes per story!**

---

**Now you can convert entire stories with a single command!** 🎉
