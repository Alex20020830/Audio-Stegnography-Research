import os
import re
import glob
import copy
import time
import shutil
from music21 import converter, stream, note, chord
from Modules.analyzer import MusicAnalyzer
from Modules.embedder import StegoEmbedder
from Modules.cryptographer import MedicalEncryptor
from Modules.google_drive import GoogleDriveClient
from Modules.metrics import StegoMetrics
from Crypto.PublicKey import ECC

# ================= 測試配置 (Test Config) =================
# [重要] 修改這裡來決定要測試哪一組資料 (索引從 0 開始)
# 例如：如果 Clementi 是第 12 個資料夾，這裡請填 11
TEST_TARGET_INDEX = 24 

DIR_EXP_MIDI = "Experience/Experience MIDI"   
DIR_EXP_IMG = "Experience/Experience Image"   
DIR_OUTPUT_ROOT = "Generated Files"
DIR_STEGO_RESULT = os.path.join(DIR_OUTPUT_ROOT, "Stego Result")
DIR_CRYPTO_IMG = os.path.join(DIR_OUTPUT_ROOT, "Crypto Image")
DIR_KEYS = "Keys"

# 確保資料夾存在
for d in [DIR_OUTPUT_ROOT, DIR_STEGO_RESULT, DIR_CRYPTO_IMG, DIR_KEYS]:
    os.makedirs(d, exist_ok=True)

TARGET_DRIVE_FOLDER_ID = "1SLnfZEpCE6D3n5jEpeaHpzemzt3K3zCI" 

def get_sorted_files(directory, ext_filter=None):
    if not os.path.exists(directory):
        print(f"[Error] 資料夾不存在: {directory}")
        return []
    
    items = os.listdir(directory)
    if ext_filter:
        items = [f for f in items if f.endswith(ext_filter)]
    
    # 自然排序
    def natural_keys(text):
        return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', text)]
    
    items.sort(key=natural_keys)
    return [os.path.join(directory, item) for item in items]

def run_single_test():
    print("="*60)
    print(f"   啟動單一案例測試 (Target Index: {TEST_TARGET_INDEX})")
    print("="*60)

    # 1. 初始化模組
    analyzer = MusicAnalyzer()
    embedder = StegoEmbedder(analyzer)
    encryptor = MedicalEncryptor()
    # 使用獨立的測試 Log，避免汙染正式數據
    metrics_logger = StegoMetrics(log_file="experiment_results_TEST.csv")
    
    # 2. 載入金鑰
    if not os.path.exists(os.path.join(DIR_KEYS, "doctor_public.pem")):
        print("[System] 生成實驗用 ECC 金鑰對...")
        priv, pub = encryptor.generate_ecc_keys()
        with open(os.path.join(DIR_KEYS, "doctor_private.pem"), "wt") as f:
            f.write(priv.export_key(format='PEM'))
        with open(os.path.join(DIR_KEYS, "doctor_public.pem"), "wt") as f:
            f.write(pub.export_key(format='PEM'))
    
    with open(os.path.join(DIR_KEYS, "doctor_public.pem"), "rt") as f:
        doctor_public_key = ECC.import_key(f.read())

    # 3. 取得檔案列表
    midi_work_folders = [f for f in get_sorted_files(DIR_EXP_MIDI) if os.path.isdir(f)]
    image_files = get_sorted_files(DIR_EXP_IMG, ext_filter=".tif")

    # 4. 驗證索引是否有效
    if TEST_TARGET_INDEX >= len(midi_work_folders) or TEST_TARGET_INDEX >= len(image_files):
        print(f"[Error] 索引 {TEST_TARGET_INDEX} 超出範圍！")
        print(f"   MIDI 資料夾數量: {len(midi_work_folders)}")
        print(f"   影像檔案數量: {len(image_files)}")
        return

    # 5. 鎖定特定測試目標
    work_folder_path = midi_work_folders[TEST_TARGET_INDEX]
    image_path = image_files[TEST_TARGET_INDEX]
    
    work_name = os.path.basename(work_folder_path)
    image_name = os.path.basename(image_path)
    
    print(f"\n[Test Target] {work_name} + {image_name}")
    
    try:
        # Step A: Encrypt
        print("   [Step A] 加密與封裝...")
        aes_key = encryptor.get_random_bytes(32)
        
        with open(image_path, "rb") as f:
            img_data = f.read()
        nonce, tag, ciphertext = encryptor.encrypt_image_aes(img_data, aes_key)
        
        temp_enc_path = os.path.join(DIR_CRYPTO_IMG, f"{image_name}.enc")
        with open(temp_enc_path, "wb") as f:
            for x in (nonce, tag, ciphertext): f.write(x)
        
        drive = GoogleDriveClient()
        file_id = drive.upload_file(temp_enc_path, folder_id=TARGET_DRIVE_FOLDER_ID)
        if not file_id: raise Exception("Google Drive Upload Failed")
        
        encrypted_packet = encryptor.encrypt_aes_key_with_ecc(aes_key, doctor_public_key)
        payload_bits = encryptor.construct_payload(file_id, encrypted_packet)
        print(f"   Payload 建構完成。長度: {len(payload_bits)} bits")

        # Step B: MIDI
        print("   [Step B] 讀取 MIDI 樂章...")
        midi_files = sorted(glob.glob(os.path.join(work_folder_path, "*.mid")))
        score_list = []
        for m_file in midi_files:
            s = converter.parse(m_file)
            score_list.append(s)
        
        work_output_dir = os.path.join(DIR_STEGO_RESULT, work_name)
        os.makedirs(work_output_dir, exist_ok=True)

        # Step C: Embed
        print("   [Step C] 執行嵌入...")
        current_bit_idx = 0
        total_bits = len(payload_bits)
        stego_scores_buffer = []
        full_original_stream = stream.Score()
        full_stego_stream = stream.Score()

        for idx, score in enumerate(score_list):
            mov_name = os.path.basename(midi_files[idx])
            
            # 容量計算 (僅顯示，不影響流程)
            try:
                mov_capacity = embedder.calculate_capacity(score)
            except Exception as e:
                print(f"      [Warning] {mov_name} 容量計算失敗: {e}")
            
            remaining_payload = payload_bits[current_bit_idx:]
            
            # 執行嵌入
            stego_score, bits_embedded_count = embedder.embed_message(
                score, remaining_payload
            )
            
            current_bit_idx += bits_embedded_count
            
            stego_path = os.path.join(work_output_dir, f"Stego_{mov_name}")
            stego_score.write('midi', fp=stego_path)
            stego_scores_buffer.append(stego_score)
            
            full_original_stream.append(copy.deepcopy(score))
            full_stego_stream.append(copy.deepcopy(stego_score))
        
        # 記錄嵌入的 bits
        bits_log_path = os.path.join(work_output_dir, "embedded_bits.txt")
        with open(bits_log_path, "w") as f:
            f.write("".join(map(str, payload_bits)))

        # Step D: Metrics
        print("   [Step D] 計算指標與存檔...")
        is_fully_embedded = (current_bit_idx >= total_bits)
        
        if not is_fully_embedded:
            print(f"   [Warning] Payload 未完全嵌入！ ({current_bit_idx}/{total_bits})")

        kld_p, kld_d = 0.0, 0.0
        try:
            kld_p, kld_d = metrics_logger.calculate_metrics(full_original_stream, full_stego_stream)
        except Exception as e:
            print(f"   [Warning] KLD 計算失敗: {e}")

        total_notes = len(full_original_stream.flat.getElementsByClass(['Note', 'Chord']))
        approx_seconds = full_original_stream.highestTime * 0.5 
        
        bps = total_bits / approx_seconds if approx_seconds > 0 else 0
        bpn = total_bits / total_notes if total_notes > 0 else 0
        
        metrics_logger.log_result({
            "Work_Name": work_name,
            "Image_Filename": image_name,
            "Image_Size": os.path.getsize(image_path),
            "Capacity": "N/A", 
            "Embedded": current_bit_idx,
            "Utilization": 100 if is_fully_embedded else (current_bit_idx/total_bits*100),
            "Total_Notes": total_notes,
            "Duration": approx_seconds,
            "bps": bps,
            "bpn": bpn,
            "KLD_Pitch": kld_p,
            "KLD_Duration": kld_d,
            "Success": is_fully_embedded,
            "Error_Log": "" if is_fully_embedded else "Payload Truncated"
        })
        
        print(f"   [Done] 測試完成。 KLD(P): {kld_p:.5f}")

    except Exception as e:
        print(f"   [Error] 測試失敗: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_single_test()