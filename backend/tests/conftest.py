import os
import sys

# делаем пакет app импортируемым при запуске pytest из каталога backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
