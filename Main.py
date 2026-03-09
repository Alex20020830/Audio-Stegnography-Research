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

# ================= 實驗配置 (Experiment Config) =================
DIR_EXP_MIDI = "Experience/Experience MIDI"   # 放30個作品資料夾的地方
DIR_EXP_IMG = "Experience/Experience Image"   # 放30張影像的地方
DIR_OUTPUT_ROOT = "Generated Files"
DIR_STEGO_RESULT = os.path.join(DIR_OUTPUT_ROOT, "Stego Result")
DIR_CRYPTO_IMG = os.path.join(DIR_OUTPUT_ROOT, "Crypto Image")
DIR_KEYS = "Keys"

# 確保資料夾存在
for d in [DIR_OUTPUT_ROOT, DIR_STEGO_RESULT, DIR_CRYPTO_IMG, DIR_KEYS]:
    os.makedirs(d, exist_ok=True)

# Google Drive 資料夾 ID (請確認這是有效的)
TARGET_DRIVE_FOLDER_ID = "1SLnfZEpCE6D3n5jEpeaHpzemzt3K3zCI" 

def get_sorted_files(directory, ext_filter=None):
    if not os.path.exists(directory):
        print(f"[Error] 資料夾不存在: {directory}")
        return []
    
    items = os.listdir(directory)
    if ext_filter:
        items = [f for f in items if f.endswith(ext_filter)]
    
    # 定義自然排序的 Key
    def natural_keys(text):
        '''
        alist.sort(key=natural_keys) sorts in human order
        http://nedbatchelder.com/blog/200712/human_sorting.html
        '''
        return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', text)]
    
    items.sort(key=natural_keys) # 使用自然排序
    
    return [os.path.join(directory, item) for item in items]

def run_batch_experiment():
    print("="*60)
    print("   啟動大規模自動化隱寫實驗 (Batch Automation)")
    print("="*60)

    # 1. 載入工具模組
    analyzer = MusicAnalyzer()
    embedder = StegoEmbedder(analyzer)
    encryptor = MedicalEncryptor()
    metrics_logger = StegoMetrics(log_file="experiment_results_batch.csv")
    
    # 2. 準備金鑰 (如果沒有就生成一組共用的，模擬醫生端)
    if not os.path.exists(os.path.join(DIR_KEYS, "doctor_public.pem")):
        print("[System] 生成實驗用 ECC 金鑰對...")
        priv, pub = encryptor.generate_ecc_keys()
        with open(os.path.join(DIR_KEYS, "doctor_private.pem"), "wt") as f:
            f.write(priv.export_key(format='PEM'))
        with open(os.path.join(DIR_KEYS, "doctor_public.pem"), "wt") as f:
            f.write(pub.export_key(format='PEM'))
    
    with open(os.path.join(DIR_KEYS, "doctor_public.pem"), "rt") as f:
        doctor_public_key = ECC.import_key(f.read())

    # 3. 取得實驗素材列表
    midi_work_folders = [f for f in get_sorted_files(DIR_EXP_MIDI) if os.path.isdir(f)]
    image_files = get_sorted_files(DIR_EXP_IMG, ext_filter=".tif") # 假設是 .tif，若是其他格式請修改

    print(f"偵測到 {len(midi_work_folders)} 個作品資料夾")
    print(f"偵測到 {len(image_files)} 張測試影像")
    
    # 確保兩者數量一致，或取最小值以避免 Index Error
    batch_count = min(len(midi_work_folders), len(image_files))
    print(f"預計執行實驗組數: {batch_count}")
    print("-" * 60)

    # 4. 開始迴圈實驗
    for i in range(batch_count):
        work_folder_path = midi_work_folders[i]
        image_path = image_files[i]
        
        work_name = os.path.basename(work_folder_path) # e.g., "Mozart Sonata K545"
        image_name = os.path.basename(image_path)
        
        print(f"\n[Experiment {i+1}/{batch_count}] Processing: {work_name} + {image_name}")
        
        try:
            # === Step A: 影像加密與上傳 ===
            print("   [Step A] 加密與封裝...")
            aes_key = encryptor.get_random_bytes(32)
            
            # 加密影像
            with open(image_path, "rb") as f:
                img_data = f.read()
            nonce, tag, ciphertext = encryptor.encrypt_image_aes(img_data, aes_key)
            
            # 暫存加密檔
            temp_enc_path = os.path.join(DIR_CRYPTO_IMG, f"{image_name}.enc")
            with open(temp_enc_path, "wb") as f:
                for x in (nonce, tag, ciphertext): f.write(x)
            
            # 上傳 Google Drive
            drive = GoogleDriveClient()
            file_id = drive.upload_file(temp_enc_path, folder_id=TARGET_DRIVE_FOLDER_ID)
            if not file_id: raise Exception("Google Drive Upload Failed")
            
            # 建構 Payload
            encrypted_packet = encryptor.encrypt_aes_key_with_ecc(aes_key, doctor_public_key)
            payload_bits = encryptor.construct_payload(file_id, encrypted_packet)
            print(f"   Payload 建構完成。長度: {len(payload_bits)} bits")

            # === Step B: 準備 MIDI 載體 (多樂章處理) ===
            print("   [Step B] 讀取 MIDI 樂章...")
            # 讀取該作品資料夾內的所有 MIDI 檔案
            midi_files = sorted(glob.glob(os.path.join(work_folder_path, "*.mid")))
            if not midi_files: raise Exception("No MIDI files found in folder")
            
            score_list = []
            for m_file in midi_files:
                s = converter.parse(m_file)
                score_list.append(s)
            
            # 建立該作品的專屬輸出資料夾
            work_output_dir = os.path.join(DIR_STEGO_RESULT, work_name)
            os.makedirs(work_output_dir, exist_ok=True)

            # === Step C: 遞迴嵌入 (Recursive Embedding) ===
            print("   [Step C] 執行嵌入...")
            
            current_bit_idx = 0
            total_bits = len(payload_bits)
            stego_scores_buffer = []
            metrics_data_buffer = [] # 暫存各樂章數據，最後統整
            
            # [修正] 初始化總容量變數
            total_work_capacity = 0
            
            # 預備一個完整的 Original Stream 用於最後計算整首曲子的 KLD
            full_original_stream = stream.Score()
            full_stego_stream = stream.Score()

            for idx, score in enumerate(score_list):
                mov_name = os.path.basename(midi_files[idx])
                print(f"      -> Processing Movement: {mov_name}")
                
                # 計算容量 (僅供參考與記錄)
                mov_capacity = embedder.calculate_capacity(score)
                
                # [修正] 累加樂章容量
                total_work_capacity += mov_capacity
                
                # 切割剩餘的 Payload
                remaining_payload = payload_bits[current_bit_idx:]
                
                # 執行嵌入
                stego_score, bits_embedded_count = embedder.embed_message(
                    score, remaining_payload
                )
                
                # 更新進度
                current_bit_idx += bits_embedded_count
                
                # 保存單樂章 Stego 檔案
                stego_path = os.path.join(work_output_dir, f"Stego_{mov_name}")
                stego_score.write('midi', fp=stego_path)
                stego_scores_buffer.append(stego_score)
                
                # 累加到完整樂譜 (用於 Metrics 計算)
                # 注意：這裡簡單合併，不考慮時間軸重疊，主要為了統計 Note 分佈
                full_original_stream.append(copy.deepcopy(score))
                full_stego_stream.append(copy.deepcopy(stego_score))

                # 如果所有數據都嵌完了，剩下的樂章是否還要跑？
                # 為了保持作品完整性，剩下的樂章即使沒數據也要過一遍流程(填補 dummy 或保持原樣)
                # 這裡的邏輯是：embed_message 如果收到空 payload，會直接回傳原曲(或做力度初始化)，這樣最好。
            
            # 儲存嵌入的 bits 供驗證
            bits_log_path = os.path.join(work_output_dir, "embedded_bits.txt")
            with open(bits_log_path, "w") as f:
                f.write("".join(map(str, payload_bits)))

            # === Step D: 實驗數據結算與記錄 ===
            print("   [Step D] 計算指標與存檔...")
            
            # 1. 檢查是否嵌入完成
            is_fully_embedded = (current_bit_idx >= total_bits)
            if not is_fully_embedded:
                print(f"   [Warning] 容量不足！ 僅嵌入 {current_bit_idx}/{total_bits} bits")

            # 2. 合併完整 Stego MIDI
            # 簡單串接所有樂章
            combined_stego = stream.Score()
            for s in stego_scores_buffer:
                combined_stego.append(s)
            
            combined_path = os.path.join(work_output_dir, f"{work_name}_Complete_Stego.mid")
            combined_stego.write('midi', fp=combined_path)

            # 3. 計算 KLD 與其他指標 (使用整首作品計算)
            kld_p, kld_d = metrics_logger.calculate_metrics(full_original_stream, full_stego_stream)
            
            # 統計總音符數與時長
            total_notes = len(full_original_stream.flat.getElementsByClass(['Note', 'Chord']))
            # 估算總時長 (秒) - 需透過 BPM 換算，這裡用 midi file 的 duration 近似或簡單累加
            # music21 的 duration 是 quarterLength，假設 120bpm => 1 ql = 0.5 sec
            # 為了精確，我們讀取 embedder 裡的秒數計算邏輯，或直接用 highestTime
            # 這裡簡化處理：假設 1 beat = 0.5 sec (120 bpm) 作為基準，或是相對比較
            # 更好的方式是讀取 MIDI meta event 的 tempo，在此簡化為 quarterLength 总和
            total_quarter_length = full_original_stream.highestTime
            approx_seconds = total_quarter_length * 0.5 # 粗略估計
            
            bps = total_bits / approx_seconds if approx_seconds > 0 else 0
            bpn = total_bits / total_notes if total_notes > 0 else 0
            
            # 4. 寫入 CSV
            metrics_logger.log_result({
                "Work_Name": work_name,
                "Image_Filename": image_name,
                "Image_Size": os.path.getsize(image_path),
                "Capacity": total_work_capacity, # [修正] 使用累加後的總容量
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
            
            print(f"   [Done] {work_name} 完成。 KLD(P): {kld_p:.5f}")

        except Exception as e:
            print(f"   [Error] 實驗失敗: {e}")
            import traceback
            traceback.print_exc()
            # 記錄失敗到 CSV
            metrics_logger.log_result({
                "Work_Name": work_name,
                "Image_Filename": image_name,
                "Success": False,
                "Error_Log": str(e)
            })

if __name__ == "__main__":
    run_batch_experiment()