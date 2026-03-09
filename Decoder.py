import os
import glob
from music21 import converter
from Modules.analyzer import MusicAnalyzer
from Modules.extractor import StegoExtractor
from Modules.cryptographer import MedicalEncryptor
from Modules.google_drive import GoogleDriveClient
from Crypto.PublicKey import ECC

# ================= Config (批量模式) =================
# 原始 MIDI 庫 (用於 Cover 參照)
DIR_EXP_MIDI = "Experience/Experience MIDI"

# 生成檔案路徑
DIR_OUTPUT_ROOT = "Generated Files"
DIR_STEGO_RESULT = os.path.join(DIR_OUTPUT_ROOT, "Stego Result")
DIR_DECODED_ROOT = os.path.join(DIR_OUTPUT_ROOT, "Decoded Result")
DIR_KEYS = "Keys"

# 確保輸出目錄存在
os.makedirs(DIR_DECODED_ROOT, exist_ok=True)

def calculate_ber(original_bits, extracted_bits):
    """計算誤碼率 (Bit Error Rate)"""
    if not original_bits or not extracted_bits: return 1.0, 0
    
    # 取最小長度進行比較
    min_len = min(len(original_bits), len(extracted_bits))
    errors = 0
    for i in range(min_len):
        if original_bits[i] != extracted_bits[i]:
            errors += 1
            
    # 長度差異也算作錯誤
    len_diff = abs(len(original_bits) - len(extracted_bits))
    total_errors = errors + len_diff
    ber = total_errors / max(len(original_bits), len(extracted_bits))
    
    return ber, total_errors

def run_batch_decoder():
    print("="*60)
    print("   啟動大規模自動化解碼 (Batch Decoder)")
    print("="*60)

    # 1. 載入工具與金鑰
    analyzer = MusicAnalyzer()
    extractor = StegoExtractor(analyzer)
    encryptor = MedicalEncryptor()
    
    # 讀取醫生私鑰 (用於解密 Session Key)
    try:
        with open(os.path.join(DIR_KEYS, "doctor_private.pem"), "rt") as f:
            doctor_private_key = ECC.import_key(f.read())
    except FileNotFoundError:
        print("[Error] 找不到醫生私鑰 (doctor_private.pem)，無法進行解密！")
        return

    # 2. 掃描 Stego Result 資料夾
    # 這裡假設 Stego Result 下面是 "作品名稱" 的子資料夾
    stego_work_folders = [f for f in glob.glob(os.path.join(DIR_STEGO_RESULT, "*")) if os.path.isdir(f)]
    
    print(f"偵測到 {len(stego_work_folders)} 組實驗結果待解碼...")
    print("-" * 60)

    success_count = 0
    fail_count = 0

    for i, work_folder in enumerate(stego_work_folders):
        work_name = os.path.basename(work_folder)
        print(f"\n[Decoder {i+1}/{len(stego_work_folders)}] Processing: {work_name}")
        
        try:
            # === Step A: 尋找對應的原始 MIDI (Cover) ===
            # 假設 Experience MIDI 下也有同名的作品資料夾
            original_work_dir = os.path.join(DIR_EXP_MIDI, work_name)
            if not os.path.exists(original_work_dir):
                print(f"   [Skip] 找不到原始 MIDI 資料夾: {original_work_dir}")
                fail_count += 1
                continue
                
            # 讀取該作品所有樂章 (排序很重要，必須跟 Main.py 順序一致)
            orig_midi_files = sorted(glob.glob(os.path.join(original_work_dir, "*.mid")))
            stego_midi_files = sorted(glob.glob(os.path.join(work_folder, "Stego_*.mid"))) # 找 Stego_ 開頭的單樂章檔
            
            if len(orig_midi_files) != len(stego_midi_files):
                print(f"   [Warning] 樂章數量不匹配 (Orig: {len(orig_midi_files)}, Stego: {len(stego_midi_files)})")
                # 仍嘗試解碼，但可能會錯位
            
            # === Step B: 逐樂章提取 Bits ===
            print("   [Step B] 提取隱藏訊息...")
            all_extracted_bits = []
            
            # 使用 zip 配對 (確保檔名對應)
            # 這裡假設 sorted 後順序是一樣的 (通常是 Movement 1, 2, 3...)
            for orig_path, stego_path in zip(orig_midi_files, stego_midi_files):
                # print(f"      Comparing: {os.path.basename(orig_path)} vs {os.path.basename(stego_path)}")
                
                score_orig = converter.parse(orig_path)
                score_stego = converter.parse(stego_path)
                
                bits = extractor.extract_message(score_orig, score_stego)
                all_extracted_bits.extend(bits)
                
            print(f"   提取完成。總長度: {len(all_extracted_bits)} bits")

            # === Step C: 驗證 BER (如果有 embedded_bits.txt) ===
            bits_log_path = os.path.join(work_folder, "embedded_bits.txt")
            if os.path.exists(bits_log_path):
                with open(bits_log_path, "r") as f:
                    content = f.read().strip()
                    original_bits = [int(b) for b in content]
                
                ber, err_count = calculate_ber(original_bits, all_extracted_bits)
                print(f"   [BER Check] 誤碼率: {ber:.5%} (Errors: {err_count})")
                
                if ber > 0.1: # 如果錯誤率太高 (>10%)，後續解密肯定失敗，提早警示
                    print("   [Warning] BER 過高，解密極可能失敗！")
            else:
                print("   [Info] 無法找到 embedded_bits.txt 進行比對")

            # === Step D: 解密與還原 ===
            print("   [Step D] 解密 Payload...")
            
            # 1. 解析 Payload 結構
            file_id, encrypted_packet = encryptor.unpack_payload(all_extracted_bits)
            
            if not file_id:
                raise Exception("Payload 解析失敗 (可能是分隔符遺失或數據損毀)")
            
            print(f"      -> Target File ID: {file_id}")
            
            # 2. 下載雲端加密檔
            drive = GoogleDriveClient()
            temp_enc_path = os.path.join(DIR_DECODED_ROOT, f"{work_name}_downloaded.enc")
            
            # 如果之前下載過，可以跳過 (選用)
            if not os.path.exists(temp_enc_path):
                drive.download_file(file_id, temp_enc_path)
            
            # 3. 解密 AES Key
            aes_key = encryptor.decrypt_aes_key_with_ecc(encrypted_packet, doctor_private_key)
            if not aes_key:
                raise Exception("ECC 解密失敗 (私鑰不匹配或數據損毀)")
            
            # 4. 解密影像
            with open(temp_enc_path, "rb") as f:
                nonce, tag, ciphertext = [f.read(x) for x in (16, 16, -1)]
                
            decrypted_data = encryptor.decrypt_image_aes(nonce, tag, ciphertext, aes_key)
            if not decrypted_data:
                raise Exception("AES 解密/驗證失敗 (Tag Mismatch)")
            
            # 5. 存檔
            output_img_path = os.path.join(DIR_DECODED_ROOT, f"{work_name}_RESTORED.tif")
            with open(output_img_path, "wb") as f:
                f.write(decrypted_data)
                
            print(f"   [Success] 影像還原成功: {output_img_path}")
            success_count += 1
            
            # 清理暫存加密檔
            if os.path.exists(temp_enc_path): os.remove(temp_enc_path)

        except Exception as e:
            print(f"   [Fail] 解碼失敗: {e}")
            fail_count += 1
            # traceback.print_exc()

    print("\n" + "="*60)
    print(f"批量解碼結束。 成功: {success_count} | 失敗: {fail_count}")
    print("="*60)

if __name__ == "__main__":
    run_batch_decoder()