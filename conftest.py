import sys
from pathlib import Path

# A projekt gyökerét tegyük az import útvonalra, hogy a `dealradar`
# csomag a tesztekből is elérhető legyen (pip install nélkül).
sys.path.insert(0, str(Path(__file__).resolve().parent))
