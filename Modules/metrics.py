import csv
import os
import numpy as np
from scipy.stats import entropy
from music21 import pitch, note, chord

class StegoMetrics:
    def __init__(self, log_file="experiment_results.csv"):
        self.log_file = log_file
        self._init_csv()

    def _init_csv(self):
        """初始化 CSV 表頭"""
        # 如果檔案不存在，才寫入表頭；如果存在，則直接附加數據
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Work_Name", "Image_Filename",          # 識別資訊
                    "Image_Size(bytes)", "Capacity(bits)",  # 容量資訊
                    "Embedded(bits)", "Utilization(%)",     # 嵌入資訊
                    "Total_Notes", "Duration(sec)",         # 載體資訊
                    "bps", "bpn",                           # 效率指標
                    "KLD_Pitch", "KLD_Duration",            # 隱蔽性指標 (無感性)
                    "Success", "Error_Log"                  # 狀態
                ])

    def _get_pitch_distribution(self, score):
        """計算音高機率分佈 (Pitch Probability Distribution)"""
        # 建立一個 0-127 的 MIDI 音高直方圖
        counts = np.zeros(128)
        total_notes = 0
        
        flat_notes = score.flat.getElementsByClass(['Note', 'Chord'])
        for elem in flat_notes:
            if isinstance(elem, note.Note):
                counts[elem.pitch.midi] += 1
                total_notes += 1
            elif isinstance(elem, chord.Chord):
                for p in elem.pitches:
                    counts[p.midi] += 1
                    total_notes += 1
        
        # 正規化為機率分佈 (加上 epsilon 避免除以零)
        if total_notes == 0:
            return counts # 全零
        
        prob_dist = counts / total_notes
        return prob_dist

    def _get_duration_distribution(self, score):
        """計算時值機率分佈 (Duration Probability Distribution)"""
        # 時值是連續的，我們將其離散化為常見的單位
        # 建立一個映射字典來統計
        duration_map = {}
        total_notes = 0
        
        flat_notes = score.flat.getElementsByClass(['Note', 'Chord'])
        for elem in flat_notes:
            d = round(elem.duration.quarterLength, 3) # 取小數點後三位避免浮點誤差
            duration_map[d] = duration_map.get(d, 0) + 1
            total_notes += 1
            
        return duration_map, total_notes

    def _calculate_kld(self, p_dist, q_dist):
        """
        計算 Kullback-Leibler Divergence
        P: 原始分佈 (Target)
        Q: 隱寫分佈 (Approximation)
        """
        # 加上極小值 epsilon 避免 log(0) 錯誤
        epsilon = 1e-10
        p_dist = p_dist + epsilon
        q_dist = q_dist + epsilon
        
        # 再次正規化以確保總和為 1
        p_dist /= np.sum(p_dist)
        q_dist /= np.sum(q_dist)
        
        return entropy(p_dist, q_dist)

    def calculate_metrics(self, score_orig, score_stego):
        """計算所有指標的主入口"""
        
        # 1. Pitch KLD
        p_dist_orig = self._get_pitch_distribution(score_orig)
        p_dist_stego = self._get_pitch_distribution(score_stego)
        kld_p = self._calculate_kld(p_dist_orig, p_dist_stego)

        # 2. Duration KLD
        # 時值比較麻煩，因為兩個樂譜可能包含不同的時值種類
        # 我們需要取兩者的聯集 (Union) 來對齊向量
        d_map_orig, total_orig = self._get_duration_distribution(score_orig)
        d_map_stego, total_stego = self._get_duration_distribution(score_stego)
        
        all_keys = set(d_map_orig.keys()) | set(d_map_stego.keys())
        sorted_keys = sorted(list(all_keys))
        
        # 建立對齊後的向量
        vec_orig = np.array([d_map_orig.get(k, 0) for k in sorted_keys], dtype=float)
        vec_stego = np.array([d_map_stego.get(k, 0) for k in sorted_keys], dtype=float)
        
        if total_orig > 0: vec_orig /= total_orig
        if total_stego > 0: vec_stego /= total_stego
        
        kld_d = self._calculate_kld(vec_orig, vec_stego)

        return kld_p, kld_d

    def log_result(self, data_dict):
        """將單次實驗結果寫入 CSV (Append模式)"""
        with open(self.log_file, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                data_dict.get("Work_Name", "Unknown"),
                data_dict.get("Image_Filename", "Unknown"),
                data_dict.get("Image_Size", 0),
                data_dict.get("Capacity", 0),
                data_dict.get("Embedded", 0),
                f"{data_dict.get('Utilization', 0):.2f}",
                data_dict.get("Total_Notes", 0),
                f"{data_dict.get('Duration', 0):.2f}",
                f"{data_dict.get('bps', 0):.4f}",
                f"{data_dict.get('bpn', 0):.4f}",
                f"{data_dict.get('KLD_Pitch', 0):.6f}",
                f"{data_dict.get('KLD_Duration', 0):.6f}",
                "TRUE" if data_dict.get("Success", False) else "FALSE",
                data_dict.get("Error_Log", "")
            ])