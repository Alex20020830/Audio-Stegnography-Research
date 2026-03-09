import os
import glob
import re
from music21 import converter
from Modules.analyzer import MusicAnalyzer
from Modules.extractor import StegoExtractor
from Modules.cryptographer import MedicalEncryptor
from Modules.google_drive import GoogleDriveClient
from Crypto.PublicKey import ECC

# ================= 測試配置 (Test Config) =================
# [重要] 這裡請填寫跟 Main_Test.py 一樣的數字 (例如 Clementi 是 11)
# 程式會自動去對應的資料夾找檔案，不用擔心順序問題
TEST_TARGET_INDEX = 24

# 路徑設定
DIR_EXP_MIDI = "Experience/Experience MIDI"
DIR_OUTPUT_ROOT = "Generated Files"
DIR_STEGO_RESULT = os.path.join(DIR_OUTPUT_ROOT, "Stego Result")
DIR_DECODED_ROOT = os.path.join(DIR_OUTPUT_ROOT, "Decoded Result")
DIR_KEYS = "Keys"

# 確保輸出目錄存在
os.makedirs(DIR_DECODED_ROOT, exist_ok=True)

def get_sorted_files(directory, ext_filter=None):
    if not os.path.exists(directory):
        print(f"[Error] 資料夾不存在: {directory}")
        return []
    
    items = os.listdir(directory)
    # 若有副檔名過濾
    if ext_filter:
        items = [f for f in items if f.endswith(ext_filter)]
    
    # 自然排序
    def natural_keys(text):
        return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', text)]
    
    items.sort(key=natural_keys)
    return [os.path.join(directory, item) for item in items]

def calculate_ber(original_bits, extracted_bits):
    """計算誤碼率 (Bit Error Rate)"""
    if not original_bits or not extracted_bits: return 1.0, 0
    
    min_len = min(len(original_bits), len(extracted_bits))
    errors = 0
    for i in range(min_len):
        if original_bits[i] != extracted_bits[i]:
            errors += 1
            
    len_diff = abs(len(original_bits) - len(extracted_bits))
    total_errors = errors + len_diff
    ber = total_errors / max(len(original_bits), len(extracted_bits))
    
    return ber, total_errors

def run_single_decoder_test():
    print("="*60)
    print(f"   啟動單一解碼測試 (Target Index: {TEST_TARGET_INDEX})")
    print("="*60)

    # 1. 載入工具與金鑰
    analyzer = MusicAnalyzer()
    extractor = StegoExtractor(analyzer)
    encryptor = MedicalEncryptor()
    
    try:
        with open(os.path.join(DIR_KEYS, "doctor_private.pem"), "rt") as f:
            doctor_private_key = ECC.import_key(f.read())
    except FileNotFoundError:
        print("[Error] 找不到醫生私鑰 (doctor_private.pem)，無法進行解密！")
        return

    # 2. [智慧定位] 先去 Experience MIDI 查名字
    midi_work_folders = get_sorted_files(DIR_EXP_MIDI)
    if TEST_TARGET_INDEX >= len(midi_work_folders):
        print(f"[Error] 來源索引 {TEST_TARGET_INDEX} 超出 MIDI 資料庫範圍！")
        return

    # 鎖定目標作品名稱 (例如 "Clementi Piano Sonata...")
    target_work_path = midi_work_folders[TEST_TARGET_INDEX]
    work_name = os.path.basename(target_work_path)
    
    print(f"\n[Test Target] {work_name}")
    print(f"   -> 正在 Generated Files 中搜尋此作品...")

    # 3. 去 Stego Result 找這個名字的資料夾
    target_stego_folder = os.path.join(DIR_STEGO_RESULT, work_name)
    
    if not os.path.exists(target_stego_folder):
        print(f"   [Error] 找不到生成的資料夾: {target_stego_folder}")
        print(f"   提示: 請先執行 Main_Test.py (Index {TEST_TARGET_INDEX}) 生成該作品的 Stego 檔。")
        return

    try:
        # === Step A: 準備路徑 ===
        # 原始 MIDI 資料夾 (Cover)
        original_work_dir = target_work_path # 已經找到了
        
        # 讀取樂章
        # 確保只讀取 .mid 檔案
        orig_midi_files = sorted(glob.glob(os.path.join(original_work_dir, "*.mid")))
        stego_midi_files = sorted(glob.glob(os.path.join(target_stego_folder, "Stego_*.mid")))
        
        if len(orig_midi_files) == 0:
            print("[Error] 原始資料夾中沒有 MIDI 檔案！")
            return
        if len(stego_midi_files) == 0:
            print("[Error] Stego 資料夾中沒有 MIDI 檔案！(可能是 Main_Test 執行失敗)")
            return

        print(f"   偵測到 {len(stego_midi_files)} 個樂章檔案")

        # === Step B: 逐樂章提取 Bits ===
        print("   [Step B] 提取隱藏訊息...")
        all_extracted_bits = []
        
        # 使用 zip 確保配對
        for orig_path, stego_path in zip(orig_midi_files, stego_midi_files):
            print(f"      -> Extracting from: {os.path.basename(stego_path)}")
            score_orig = converter.parse(orig_path)
            score_stego = converter.parse(stego_path)
            
            bits = extractor.extract_message(score_orig, score_stego)
            all_extracted_bits.extend(bits)
            
        print(f"   提取完成。總長度: {len(all_extracted_bits)} bits")

        # === Step C: 驗證 BER ===
        bits_log_path = os.path.join(target_stego_folder, "embedded_bits.txt")
        if os.path.exists(bits_log_path):
            with open(bits_log_path, "r") as f:
                content = f.read().strip()
                original_bits = [int(b) for b in content]
            
            ber, err_count = calculate_ber(original_bits, all_extracted_bits)
            print(f"   [BER Check] 誤碼率: {ber:.5%} (Errors: {err_count})")
            
            if ber > 0:
                print("   [Debug] 前 50 bits 比對 (檢查是否錯位):")
                print(f"      Orig: {original_bits[:50]}")
                print(f"      Extr: {all_extracted_bits[:50]}")
        else:
            print("   [Info] 無法找到 embedded_bits.txt 進行比對")

        # === Step D: 解密與還原 ===
        print("   [Step D] 解密 Payload...")
        
        file_id, encrypted_packet = encryptor.unpack_payload(all_extracted_bits)
        
        if not file_id:
            print(f"   [Fail] Payload 解析失敗 (可能是分隔符遺失或數據損毀)")
            return
        
        print(f"      -> Target File ID: {file_id}")
        
        # 下載
        drive = GoogleDriveClient()
        temp_enc_path = os.path.join(DIR_DECODED_ROOT, f"{work_name}_downloaded.enc")
        
        if not os.path.exists(temp_enc_path):
            drive.download_file(file_id, temp_enc_path)
        else:
            print("      -> 使用已存在的下載檔案")

        # 解密 AES Key
        aes_key = encryptor.decrypt_aes_key_with_ecc(encrypted_packet, doctor_private_key)
        if not aes_key:
            raise Exception("ECC 解密失敗 (私鑰不匹配或數據損毀)")
        
        # 解密影像
        with open(temp_enc_path, "rb") as f:
            nonce, tag, ciphertext = [f.read(x) for x in (16, 16, -1)]
            
        decrypted_data = encryptor.decrypt_image_aes(nonce, tag, ciphertext, aes_key)
        if not decrypted_data:
            raise Exception("AES 解密/驗證失敗 (Tag Mismatch)")
        
        output_img_path = os.path.join(DIR_DECODED_ROOT, f"{work_name}_RESTORED.tif")
        with open(output_img_path, "wb") as f:
            f.write(decrypted_data)
            
        print(f"   [Success] 影像還原成功: {output_img_path}")
        
        # 清理
        if os.path.exists(temp_enc_path): os.remove(temp_enc_path)

    except Exception as e:
        print(f"   [Fail] 測試失敗: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_single_decoder_test()