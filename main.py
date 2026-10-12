"""Punto de entrada: abre la ventana del chatbot.   Uso:  python main.py"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")  # aviso de Tk 8.5 del sistema en macOS
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from gui import main  # noqa: E402

if __name__ == "__main__":
    main()
