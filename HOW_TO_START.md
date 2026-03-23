# 🚀 How to Start the Virtual Environment and Run the App

## ✅ Virtual Environment is Already Created!

The virtual environment (venv) has been set up successfully.

## 📋 Step-by-Step Instructions

### **Step 1: Activate the Virtual Environment**

Every time you open a new terminal, you need to activate the virtual environment:

```powershell
.\venv\Scripts\Activate.ps1
```

You'll see `(venv)` appear at the start of your command prompt, like this:
```
(venv) PS E:\python\TTS\TestVoice001>
```

### **Step 2: Add Your API Key**

1. Open the `.env` file in a text editor (Notepad, VS Code, etc.)
2. Find the line: `TYPECAST_API_KEY=your_api_key_here`
3. Replace `your_api_key_here` with your actual Typecast API key
4. Save the file

**Where to get your API key:**
- Go to https://typecast.ai/
- Sign up or log in
- Find your API key in your account settings

### **Step 3: Run the Application**

```powershell
python app.py
```

## 🔄 Quick Reference

### To activate virtual environment:
```powershell
.\venv\Scripts\Activate.ps1
```

### To deactivate virtual environment:
```powershell
deactivate
```

### To install packages (if needed):
```powershell
pip install -r requirements.txt
```

### To run the app:
```powershell
python app.py
```

## ✨ All-in-One Command

If you want to activate and run in one go:

```powershell
.\venv\Scripts\Activate.ps1; python app.py
```

## 📁 Current Status

✅ Virtual environment created: `venv/`
✅ Packages installed:
   - typecast-python
   - python-dotenv
✅ .env file created (needs your API key)

## ⚠️ Important Notes

1. **Always activate the virtual environment** before running the app
2. **Never commit your `.env` file** to version control (it's already in `.gitignore`)
3. **Keep your API key secret** - don't share it publicly

## 🐛 Troubleshooting

### "Execution policy" error when activating venv:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### "Module not found" error:
Make sure you activated the virtual environment first!

### "API key not found" error:
Check that your `.env` file has the correct API key.

## 💡 Example Workflow

```powershell
# 1. Navigate to project folder
cd e:\python\TTS\TestVoice001

# 2. Activate virtual environment
.\venv\Scripts\Activate.ps1

# 3. Run the application
python app.py

# 4. When done, deactivate
deactivate
```

---

**Need help?** Check the README.md for more detailed information!
