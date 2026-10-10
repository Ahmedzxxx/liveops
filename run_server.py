import uvicorn
import os
import sys

if __name__ == "__main__":
    # Force UTF-8 for console output on Windows
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

    # Ensure current directory is in sys.path
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    if cur_dir not in sys.path:
        sys.path.insert(0, cur_dir)

    port = int(os.environ.get("PORT", 8050))
    print("=" * 60)
    print(f">> Starting LiveOps Management Server on http://0.0.0.0:{port}")
    print("=" * 60)
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
