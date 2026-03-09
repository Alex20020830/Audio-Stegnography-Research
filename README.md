# Audio Steganography Project

這是一個關於音訊隱寫術的研究專案，主要專注於在音訊媒體（如 MIDI）中嵌入與提取隱藏資訊。

## 📁 專案結構簡介

* `Main.py`: 訊息嵌入（Embedding）的主程式。
* `Decoder.py`: 訊息提取（Extraction）的核心邏輯。
* `Modules/`: 存放專案所需的自定義功能模組。
* `check_logic.mid`: 用於測試隱寫邏輯的基礎 MIDI 檔案。
* `Academic_Histogram_Proof.png`: 隱寫分析後的統計分佈證明圖。

### 1. 環境設定
建議使用 Python 3.x，並安裝相關依賴套件：
```bash
# 建立虛擬環境
python -m venv .venv
# 啟動虛擬環境 (Windows)
.\venv\Scripts\activate

# 執行 Main.py 來進行資料隱藏：
python Main.py

# 使用 Decoder.py 或 DecoderTest.py 來驗證隱藏資訊是否能正確還原：
python Decoder.py
