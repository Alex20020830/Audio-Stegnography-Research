import sys
import music21
import pretty_midi

print("=== 環境驗證報告 ===")
# 檢查是否使用虛擬環境內的 Python
print(f"Python 執行路徑: {sys.executable}")
# 檢查套件版本
print(f"Music21 版本: {music21.__version__}")
print(f"Pretty_midi 版本: {pretty_midi.__version__}")

if ".venv" in sys.executable:
    print("\n[成功] 您正在使用虛擬環境！")
else:
    print("\n[警告] 您使用的是全域 Python，請檢查設定。")